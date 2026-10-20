# tools/verify_release.py
"""
**发布包一致性校验器**：把每次发版手工做的核对固化成一条命令。

## 为什么
v5.0.12–v5.0.16 每次发版都要人工核对：SHA-256、包内时间戳晚于提交、
`BeeOffice.exe` 存在、locale key 数、`tech_words.txt`、归档。手工核对容易漏，
也不可复跑。本工具把这些检查变成可执行断言 + JSON 证据。

## 用法
    python tools/verify_release.py BeeOffice-v5.0.16-windows.zip --commit v5.0.16 \
        --json _ptmp/analysis/release_v5.0.16.json

退出码：0 = 全部检查通过；1 = 有失败项。
"""
import argparse
import datetime as _dt
import hashlib
import json
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: 包内必须存在的文件（后缀匹配，兼容不同 PyInstaller 布局）
REQUIRED_SUFFIXES = (
    "BeeOffice/BeeOffice.exe",
    "data/tech_words.txt",
    "locales/zh_CN.json",
    "locales/en_US.json",
)

#: 期望 locale key 数（v5.0.13 起为 223；变化时在发版说明里解释）
EXPECTED_LOCALE_KEYS = 223


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit_time(commit: str) -> int:
    """提交的 Unix 时间戳（秒）。找不到时抛 ValueError。"""
    completed = subprocess.run(
        ["git", "log", "-1", "--format=%ct", commit],
        cwd=str(ROOT), capture_output=True, text=True, timeout=15,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        raise ValueError(f"找不到提交: {commit}")
    return int(completed.stdout.strip())


def _zip_entry_time(info: zipfile.ZipInfo) -> float:
    """zip 条目时间 → Unix 时间戳（zip 存的是本地时间，按本地解释）。"""
    return time.mktime(_dt.datetime(*info.date_time).timetuple())


def _read_sha_file(zip_path: Path) -> str:
    sha_file = zip_path.with_name(zip_path.name + ".sha256")
    if not sha_file.is_file():
        return ""
    parts = sha_file.read_text(encoding="utf-8").strip().split()
    return parts[0] if parts else ""


def verify_zip(zip_path, commit: str = "HEAD", commit_time=None,
               expected_locale_keys: int = EXPECTED_LOCALE_KEYS) -> dict:
    """
    校验发布包；返回 dict（`ok` 为总判定，`checks` 逐项）。

    :param commit_time: 可选，直接给提交时间戳（测试用）；为 None 时用
        `commit` 去 `git log` 查。
    """
    zip_path = Path(zip_path)
    checks = []
    result = {"zip": str(zip_path), "sha256": "", "checks": checks}

    if not zip_path.is_file():
        checks.append({"name": "文件存在", "ok": False, "detail": "zip 不存在"})
        result["ok"] = False
        return result

    actual_sha = sha256(zip_path)
    result["sha256"] = actual_sha
    expected_sha = _read_sha_file(zip_path)
    checks.append({
        "name": "SHA-256 与 .sha256 一致",
        "ok": bool(expected_sha) and actual_sha == expected_sha,
        "detail": f"zip={actual_sha[:16]}… sha_file={expected_sha[:16]}…",
    })

    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        infos = archive.infolist()
        checks.append({
            "name": "包内文件数 ≥ 3000",
            "ok": len(names) >= 3000,
            "detail": str(len(names)),
        })
        missing = [
            suffix for suffix in REQUIRED_SUFFIXES
            if not any(name.endswith(suffix) for name in names)
        ]
        checks.append({
            "name": "必需文件存在",
            "ok": not missing,
            "detail": f"缺: {missing}" if missing else "全在",
        })

        locale_counts = {}
        locale_ok = True
        for name in names:
            if not name.endswith("locales/zh_CN.json") and \
                    not name.endswith("locales/en_US.json"):
                continue
            try:
                data = json.loads(archive.read(name).decode("utf-8"))
            except Exception as e:  # noqa: BLE001
                locale_ok = False
                locale_counts[name] = f"解析失败: {e}"
                continue
            locale_counts[name.rsplit("/", 1)[-1]] = len(data)
            if len(data) != expected_locale_keys:
                locale_ok = False
        checks.append({
            "name": f"locale key 数 = {expected_locale_keys}",
            "ok": locale_ok and len(locale_counts) == 2,
            "detail": json.dumps(locale_counts, ensure_ascii=False),
        })

        latest = max(infos, key=_zip_entry_time) if infos else None
        latest_ts = _zip_entry_time(latest) if latest else 0
        if commit_time is None:
            try:
                commit_time = _git_commit_time(commit)
            except ValueError as e:
                checks.append({"name": "提交时间", "ok": False, "detail": str(e)})
                commit_time = 0
        timeline_ok = latest is not None and commit_time and latest_ts > commit_time
        checks.append({
            "name": "包内最新条目晚于提交",
            "ok": bool(timeline_ok),
            "detail": (
                f"latest={_dt.datetime.fromtimestamp(latest_ts).strftime('%Y-%m-%d %H:%M:%S')}"
                f" commit={_dt.datetime.fromtimestamp(commit_time).strftime('%Y-%m-%d %H:%M:%S')}"
                if commit_time else "无提交时间"
            ),
        })
        result["entries"] = len(names)
        result["latest_entry"] = (
            _dt.datetime.fromtimestamp(latest_ts).strftime("%Y-%m-%d %H:%M:%S")
            if latest else ""
        )

    result["ok"] = all(item["ok"] for item in checks)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="发布包一致性校验")
    parser.add_argument("zip", help="发行包路径")
    parser.add_argument("--commit", default="HEAD",
                        help="用于时间戳比对的提交（默认 HEAD）")
    parser.add_argument("--json", help="把结果写入 JSON")
    args = parser.parse_args(argv)

    result = verify_zip(args.zip, commit=args.commit)
    for item in result["checks"]:
        mark = "✓" if item["ok"] else "✗"
        print(f"  {mark} {item['name']}: {item['detail']}")
    if args.json:
        Path(args.json).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"结果已写入 {args.json}")
    print("✅ 发布包校验通过" if result["ok"] else "❌ 发布包校验失败")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
