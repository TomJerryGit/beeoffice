# beeoffice/cloud_sync/engine.py
"""
**双向同步引擎**（可配置同步目录 + 上传 + 下载 + 如实计数）。

## 为什么重写这一块（审计报告 §1.6）
原先「立即同步」上传的是 `~/.beeoffice_data` —— 这个目录**全仓只有一处引用、
没有任何写入方**，所以永远是空的：用户配好网盘、点"立即同步"，
只会看到"同步目录为空，没有文件需要上传"。
同时三个适配器的 `download()` **一个调用者都没有**（纯单向、也从不下载）。

## 本模块做什么
1. **可配置的同步目录**（默认 `~/BeeOffice云同步`）：用户往里放文件，
   或点「把当前文档加入同步目录」——从此"同步"有实际内容；
2. **上传**：按策略白名单（`policy.should_upload`）过滤，**如实计数**；
3. **下载**：云端有、本地没有的文件拉下来（首次补上 `download()` 的调用者）；
4. **冲突**：两边都有时按"修改时间新者胜"，并把冲突**单独计数**；
   分不出先后（时间相同但大小不同）时**保留本地**，只报告、不静默覆盖；
5. 全程**不删**任何文件（同步不该变成删除器）；跳过项要能说出原因。

设计上把网络层（`storage`）注入进来，因此可以用假 storage 完整测试，
不需要真的连网盘。
"""
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from beeoffice.cloud_sync.policy import should_upload

#: 默认同步目录名（放在用户主目录下，写清楚是干什么的）
DEFAULT_SYNC_DIRNAME = "BeeOffice云同步"


def default_sync_dir() -> Path:
    """默认同步目录（`~/BeeOffice云同步`）。"""
    return Path.home() / DEFAULT_SYNC_DIRNAME


def _remote_mtime(storage, remote_path: str) -> Optional[float]:
    """
    取云端文件的修改时间（拿不到就返回 None）。

    `get_file_info` 的返回约定各适配器略有差异（有的是 (size, mtime)），
    所以这里**容错解析**：只在能明确取到数字时使用，取不到就退化为"按大小比"。
    """
    try:
        info = storage.get_file_info(remote_path)
    except Exception as e:  # noqa: BLE001
        logging.debug(f"云同步：读取远端信息失败 {remote_path}: {e}")
        return None
    if not info:
        return None
    for value in info:
        if isinstance(value, (int, float)) and value > 1_000_000_000:
            return float(value)          # 看起来像时间戳（秒）
    return None


def _local_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def list_remote(storage, remote_dir: str) -> List[str]:
    """列出云端目录下的文件名（拿不到就返回空列表 —— 不假装成功）。"""
    try:
        names = storage.list_files(remote_dir)
    except Exception as e:  # noqa: BLE001
        logging.warning(f"云同步：列出远端目录失败 {remote_dir}: {e}")
        return []
    return [str(name) for name in (names or [])]


def _remote_size(storage, remote_path: str) -> Optional[int]:
    """取云端文件大小（拿不到返回 None）。"""
    try:
        info = storage.get_file_info(remote_path)
    except Exception as e:  # noqa: BLE001
        logging.debug(f"云同步：读取远端信息失败 {remote_path}: {e}")
        return None
    if not info:
        return None
    for value in info:
        if isinstance(value, int) and 0 <= value < 1_000_000_000:
            return value          # 看起来像字节数
    return None


def _remote_exists(storage, remote_path: str) -> bool:
    """云端是否存在该文件（适配器没实现 exists 时返回 False，交由上传兜底）。"""
    exists = getattr(storage, "exists", None)
    if not callable(exists):
        return False
    try:
        return bool(exists(remote_path))
    except Exception:  # noqa: BLE001
        return False


def _needs_upload(storage, remote_path: str, local_file: Path) -> bool:
    """
    本地这份要不要上传？

    **增量判断**（重要）：如果远端已存在、且大小一致、且远端不更旧，
    就认为"已是最新"，跳过 —— 否则每次同步都会把整个目录重传一遍
    （WebDAV/网盘上这是很慢的）。
    """
    if not _remote_exists(storage, remote_path):
        return True
    remote_size = _remote_size(storage, remote_path)
    if remote_size is None:
        return True                       # 拿不到信息 → 保守地上传
    try:
        local_size = local_file.stat().st_size
    except OSError:
        return True
    if remote_size != local_size:
        return True
    remote_mtime = _remote_mtime(storage, remote_path)
    if remote_mtime is None:
        return False                      # 大小一致且无时间信息 → 视为已同步
    return remote_mtime < _local_mtime(local_file) - 1


def sync_folder(storage, local_dir, remote_dir: str,
                on_progress=None) -> Dict[str, Any]:
    """
    双向同步一个目录。

    :param storage: 需实现 `upload` / `download` / `list_files`
                    （可选 `exists` / `get_file_info`，用于增量判断）
    :param local_dir: 本地同步目录（不存在会自动创建）
    :param remote_dir: 云端目录（如 "/beeoffice"）
    :return: 计数与明细：{"uploaded", "downloaded", "up_to_date", "skipped",
             "failed", "conflicts", "reasons", "total_local", "total_remote",
             "uploaded_names", "downloaded_names"}
    """
    local = Path(local_dir)
    result: Dict[str, Any] = {
        "uploaded": 0, "downloaded": 0, "up_to_date": 0,
        "skipped": 0, "failed": 0,
        "conflicts": 0, "reasons": {},
        "total_local": 0, "total_remote": 0,
        "uploaded_names": [], "downloaded_names": [],
    }
    try:
        local.mkdir(parents=True, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        logging.error(f"云同步：无法创建同步目录 {local}: {e}")
        result["failed"] += 1
        result["reasons"]["同步目录不可创建"] = 1
        return result

    files = [f for f in local.rglob("*") if f.is_file()]
    result["total_local"] = len(files)
    local_names = {f.relative_to(local).as_posix(): f for f in files}

    # ---------- 1. 上传：本地有、且通过策略 ----------
    done = 0
    for rel, file in local_names.items():
        ok, reason = should_upload(file)
        if not ok:
            result["skipped"] += 1
            result["reasons"][reason] = result["reasons"].get(reason, 0) + 1
            done += 1
            if on_progress:
                on_progress(done, result["total_local"])
            continue
        remote_path = f"{remote_dir}/{rel}"
        try:
            if not _needs_upload(storage, remote_path, file):
                result["up_to_date"] += 1
            elif storage.upload(str(file), remote_path):
                result["uploaded"] += 1
                result["uploaded_names"].append(rel)
            else:
                result["failed"] += 1
        except Exception as e:  # noqa: BLE001
            result["failed"] += 1
            logging.warning(f"云同步：上传失败 {rel}: {e}")
        done += 1
        if on_progress:
            on_progress(done, result["total_local"])

    # ---------- 2. 下载：云端有、本地没有（或云端更新） ----------
    remote_names = list_remote(storage, remote_dir)
    result["total_remote"] = len(remote_names)
    for name in remote_names:
        rel = str(name).lstrip("/")
        if not rel or rel.endswith("/"):
            continue                       # 目录项跳过
        remote_path = f"{remote_dir}/{rel}"
        local_file = local / rel
        try:
            if not local_file.exists():
                local_file.parent.mkdir(parents=True, exist_ok=True)
                if storage.download(remote_path, str(local_file)):
                    result["downloaded"] += 1
                    result["downloaded_names"].append(rel)
                else:
                    result["failed"] += 1
                continue

            # 两边都有 → 比时间/大小
            # （把"已同步"报成"冲突"会吓到用户，所以只有**真分不清**时才算冲突）
            remote_mtime = _remote_mtime(storage, remote_path)
            if remote_mtime is None:
                remote_size = _remote_size(storage, remote_path)
                try:
                    local_size = local_file.stat().st_size
                except OSError:
                    local_size = None
                if remote_size is not None and remote_size == local_size:
                    result["up_to_date"] += 1
                else:
                    result["conflicts"] += 1      # 保留本地、只报告
                continue
            if remote_mtime > _local_mtime(local_file) + 1:
                if storage.download(remote_path, str(local_file)):
                    result["downloaded"] += 1
                    result["downloaded_names"].append(rel)
                else:
                    result["failed"] += 1
            else:
                result["up_to_date"] += 1
        except Exception as e:  # noqa: BLE001
            result["failed"] += 1
            logging.warning(f"云同步：处理远端文件失败 {rel}: {e}")

    return result


def describe_sync(result: Dict[str, Any]) -> str:
    """把结果说成人话（**不掩饰"什么都没做"**）。"""
    uploaded = result.get("uploaded", 0)
    downloaded = result.get("downloaded", 0)
    failed = result.get("failed", 0)
    conflicts = result.get("conflicts", 0)
    skipped = result.get("skipped", 0)
    up_to_date = result.get("up_to_date", 0)
    parts = [f"上传 {uploaded} 个", f"下载 {downloaded} 个"]
    if up_to_date:
        parts.append(f"已是最新 {up_to_date} 个")
    if conflicts:
        parts.append(f"两边都有、保留本地 {conflicts} 个")
    if skipped:
        reasons = result.get("reasons") or {}
        detail = "、".join(f"{k}×{v}" for k, v in list(reasons.items())[:3])
        parts.append(f"按策略跳过 {skipped} 个" + (f"（{detail}）" if detail else ""))
    if failed:
        parts.append(f"失败 {failed} 个")
    summary = "；".join(parts)
    if not uploaded and not downloaded and not failed:
        return (
            f"同步目录里没有需要同步的变化（{summary}）。\n\n"
            "提示：把要同步的文件放进同步目录，或用「☁️ 云存储设置」里的"
            "「选择同步目录」换一个目录。"
        )
    return f"同步完成：{summary}。"
