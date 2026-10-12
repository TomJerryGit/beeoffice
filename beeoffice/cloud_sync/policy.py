# beeoffice/cloud_sync/policy.py
"""
云同步的上传策略与执行（优化规划 §4.5）

背景（分析报告 §4.6 实测）
--------------------------
`app._sync_now()` 的 `sync_files()` 只有一个 `for file in local_dir.rglob("*"):
storage.upload(...)` 循环：
  - **没有过滤** → `~/.beeoffice_data` 里任何内容都会**明文**上传到用户的
    WebDAV / OneDrive / Google Drive（含各类凭据文件的可能）；
  - **没有计量** → 无论上传了多少、跳过多少、失败多少，UI 一律显示
    "同步完成"，名副其实的成功假象。

本模块把"该不该上传"与"上传并计数"抽成不依赖 Qt 的纯逻辑，
因此可以直接用临时目录 + 假 storage 测试（不必构造 GUI）。

注意：本模块**不**实现双向同步与冲突策略 —— 那是更大的改动，
见规划 §4.5 的验收清单。
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

#: 单文件上限（超过不上传，避免把大文件偶然传上去）
MAX_UPLOAD_BYTES = 100 * 1024 * 1024        # 100 MB

#: 绝不外传的扩展名（私钥 / 证书 / 密钥库）
BLOCKED_EXTENSIONS = {
    ".key", ".pem", ".p12", ".pfx", ".cer", ".crt", ".der",
    ".keystore", ".jks", ".ppk", ".kdbx", ".asc", ".gpg",
}

#: 绝不外传的文件名（小写比较）
BLOCKED_FILENAMES = {
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
    "credentials", "credentials.json", ".env", ".netrc",
    ".git-credentials", "known_hosts",
}

#: 临时 / 中间文件（不该同步）
SKIPPED_EXTENSIONS = {".tmp", ".temp", ".part", ".crdownload", ".swp", ".lock"}

#: settings JSON 里一旦出现这些键，就认为该文件含凭据、不上传
SENSITIVE_SETTINGS_KEYS = (
    "ai_api_key", "api_key", "password", "passwd", "webdav_pass",
    "token", "access_token", "refresh_token", "secret", "client_secret",
    "private_key",
)


def is_sensitive_settings(path: Path) -> bool:
    """
    判断一个 JSON 文件是否含凭据类字段。

    只对 `.json` 且可解析的文件做检查；解析失败按**不安全**处理
    （宁可不传，也不要冒险外传）。

    :return: True 表示含敏感键（不应上传）
    """
    try:
        if path.suffix.lower() != ".json":
            return False
        if path.stat().st_size > 5 * 1024 * 1024:
            return False
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            data = json.load(fh)
    except Exception:
        return False        # 不是合法 JSON 就按普通文件处理

    def _has_key(obj: Any, depth: int = 0) -> bool:
        if depth > 4:
            return False
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(key, str) and \
                        key.strip().lower() in SENSITIVE_SETTINGS_KEYS:
                    # 只有"确实有值"才算敏感（空串不算）
                    if value not in ("", None, [], {}):
                        return True
                if _has_key(value, depth + 1):
                    return True
        elif isinstance(obj, list):
            for item in obj:
                if _has_key(item, depth + 1):
                    return True
        return False

    return _has_key(data)


def should_upload(path: Path) -> "tuple[bool, str]":
    """
    判断某个文件是否应上传。

    :return: (是否上传, 原因)。不上传时原因用于日志/计数展示。
    """
    p = Path(path)
    name = p.name.lower()
    ext = p.suffix.lower()

    if ext in BLOCKED_EXTENSIONS:
        return False, f"密钥/证书类文件（{ext}）"
    if name in BLOCKED_FILENAMES:
        return False, "凭据文件"
    if ext in SKIPPED_EXTENSIONS:
        return False, "临时文件"
    if name.startswith("~$"):
        return False, "Office 临时文件"

    try:
        size = p.stat().st_size
    except OSError as e:
        return False, f"无法读取（{e.__class__.__name__}）"

    if size == 0:
        return False, "空文件"
    if size > MAX_UPLOAD_BYTES:
        return False, f"超过上限（{size // (1024 * 1024)} MB）"

    if is_sensitive_settings(p):
        return False, "含凭据字段的配置文件"

    return True, ""


def upload_tree(
    storage,
    local_dir,
    remote_dir: str,
    *,
    on_progress=None,
) -> Dict[str, Any]:
    """
    把一个本地目录按策略上传到云端，并**如实计数**。

    :param storage: 实现了 `upload(local_path, remote_path) -> bool` 的对象
    :param local_dir: 本地目录（不存在时视为空）
    :param remote_dir: 云端根目录（如 "/beeoffice"）
    :param on_progress: 可选回调 (done, total)
    :return: {"uploaded": int, "skipped": int, "failed": int,
              "reasons": {原因: 次数}, "total": int}
    """
    local = Path(local_dir)
    result: Dict[str, Any] = {
        "uploaded": 0,
        "skipped": 0,
        "failed": 0,
        "reasons": {},
        "total": 0,
    }
    if not local.is_dir():
        logging.info(f"云同步：本地目录不存在，视为空：{local}")
        return result

    files = [f for f in local.rglob("*") if f.is_file()]
    result["total"] = len(files)

    for i, file in enumerate(files):
        ok, reason = should_upload(file)
        if not ok:
            result["skipped"] += 1
            result["reasons"][reason] = result["reasons"].get(reason, 0) + 1
            logging.info(f"云同步：跳过 {file.name}（{reason}）")
            if on_progress:
                on_progress(i + 1, result["total"])
            continue

        try:
            rel = file.relative_to(local)
            remote_path = f"{remote_dir}/{rel.as_posix()}"
            if storage.upload(str(file), remote_path):
                result["uploaded"] += 1
            else:
                result["failed"] += 1
                logging.warning(f"云同步：上传失败 {file}")
        except Exception as e:
            result["failed"] += 1
            logging.error(f"云同步：上传异常 {file}: {e}")

        if on_progress:
            on_progress(i + 1, result["total"])

    return result


def describe_result(result: Dict[str, Any]) -> str:
    """
    把计数变成一句**如实**的提示，替代原先无条件的"同步完成"。

    例：`已上传 3 个文件，跳过 2 个（密钥/证书类文件 1、空文件 1），失败 0 个`
    一个都没上传时也要说清楚，而不是报"完成"。
    """
    uploaded = result.get("uploaded", 0)
    skipped = result.get("skipped", 0)
    failed = result.get("failed", 0)
    total = result.get("total", 0)

    if total == 0:
        return "同步目录为空，没有文件需要上传"

    parts = [f"已上传 {uploaded} 个文件"]
    if skipped:
        detail = "、".join(
            f"{k} {v}" for k, v in sorted(result.get("reasons", {}).items())
        )
        parts.append(f"跳过 {skipped} 个（{detail}）")
    else:
        parts.append("跳过 0 个")
    parts.append(f"失败 {failed} 个")
    return "，".join(parts)
