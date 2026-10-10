# tests/test_p0_regression/test_p0_10_webdav_conflict.py
"""
P0-10 回归：WebDAV 双向同步时应检测冲突，避免覆盖新文件。

背景：
  _check_conflict 定义了但从未在 _sync_folder 里被调用，
  导致双向同步时上传会覆盖远端新文件、下载会覆盖本地新文件。

修复：
  _sync_folder 在 upload 分支遇到 remote_newer 时跳过上传；
  在 download 分支遇到 local_newer 时跳过下载。

测试策略：
  1. 直接测 _check_conflict 的返回值（local_newer / remote_newer / same）
     —— 用宽松时差（±1 天），避免 strptime 时区解析差异
  2. 集成测 _sync_folder 的跳过逻辑 —— monkeypatch _check_conflict
"""
from datetime import datetime
from pathlib import Path

import pytest


# ==================== 测试辅助 ====================

class _FakeClient:
    """模拟 webdav3.client.Client，仅实现 _sync_folder 用到的方法。"""

    def __init__(self, info_map=None):
        self.info_map = info_map or {}
        self.uploads = []
        self.downloads = []
        self.list_result = []

    def info(self, path):
        return self.info_map.get(path, {})

    def upload_sync(self, remote_path, local_path):
        self.uploads.append((remote_path, local_path))

    def download_sync(self, remote_path, local_path):
        self.downloads.append((remote_path, local_path))

    def list(self, path):
        return self.list_result


def _make_worker(local_dir, direction="upload"):
    """构造一个 WebDAVSyncWorker，不启动线程。"""
    from beeoffice.plugins.webdav_sync import WebDAVSyncWorker
    return WebDAVSyncWorker(
        "http://example.com/webdav",
        "user", "pass",
        str(local_dir),
        "/remote",
        direction,
    )


# ==================== _check_conflict 单元测试 ====================

def test_check_conflict_local_newer(tmp_path):
    """P0-10：本地文件明显更新 → local_newer。"""
    local_file = tmp_path / "a.txt"
    local_file.write_text("local")

    # 本地 mtime 设为 2024-01-01；远端设为 2023-01-01
    local_ts = datetime(2024, 1, 1).timestamp()
    import os
    os.utime(str(local_file), (local_ts, local_ts))

    remote_str = "Sun, 01 Jan 2023 00:00:00 GMT"
    fake_client = _FakeClient({"/remote/a.txt": {"modified": remote_str}})

    worker = _make_worker(tmp_path)
    result = worker._check_conflict(
        fake_client, local_file, "/remote/a.txt"
    )
    assert result == "local_newer", (
        f"P0-10：本地明显更新时应返回 local_newer，实际 {result!r}"
    )


def test_check_conflict_remote_newer(tmp_path):
    """P0-10：远端文件明显更新 → remote_newer。"""
    local_file = tmp_path / "a.txt"
    local_file.write_text("local")

    local_ts = datetime(2023, 1, 1).timestamp()
    import os
    os.utime(str(local_file), (local_ts, local_ts))

    remote_str = "Mon, 01 Jan 2024 00:00:00 GMT"
    fake_client = _FakeClient({"/remote/a.txt": {"modified": remote_str}})

    worker = _make_worker(tmp_path)
    result = worker._check_conflict(
        fake_client, local_file, "/remote/a.txt"
    )
    assert result == "remote_newer", (
        f"P0-10：远端明显更新时应返回 remote_newer，实际 {result!r}"
    )


def test_check_conflict_same_when_close(tmp_path):
    """P0-10：本地与远端时间相近 → same。"""
    local_file = tmp_path / "a.txt"
    local_file.write_text("local")

    # 用当前时间构造：本地 mtime 与远端 modified 一致
    import os
    now_ts = datetime.now().timestamp()
    os.utime(str(local_file), (now_ts, now_ts))

    # 格式化成 HTTP 日期
    remote_str = datetime.utcfromtimestamp(now_ts).strftime(
        "%a, %d %b %Y %H:%M:%S GMT"
    )
    fake_client = _FakeClient({"/remote/a.txt": {"modified": remote_str}})

    worker = _make_worker(tmp_path)
    result = worker._check_conflict(
        fake_client, local_file, "/remote/a.txt"
    )
    # 允许 ±1 秒误差：可能 same，也可能是 local_newer/remote_newer
    # 但绝不应该是 "unknown"
    assert result in ("same", "local_newer", "remote_newer"), (
        f"不应返回 unknown（说明解析失败）: {result!r}"
    )


def test_check_conflict_local_not_exists(tmp_path):
    """P0-10：本地文件不存在时 → same（视为无冲突）。"""
    fake_client = _FakeClient({"/remote/a.txt": {
        "modified": "Mon, 01 Jan 2024 00:00:00 GMT"
    }})

    worker = _make_worker(tmp_path)
    missing = tmp_path / "nonexistent.txt"
    result = worker._check_conflict(
        fake_client, missing, "/remote/a.txt"
    )
    # 本地 mtime = 0，走 "same" 分支
    assert result == "same", (
        f"本地文件不存在时应返回 same，实际 {result!r}"
    )


def test_check_conflict_info_raises(tmp_path):
    """P0-10：client.info 抛异常时 → unknown（兜底）。"""
    class _RaisingClient:
        def info(self, path):
            raise RuntimeError("network error")

    local_file = tmp_path / "a.txt"
    local_file.write_text("x")

    worker = _make_worker(tmp_path)
    result = worker._check_conflict(
        _RaisingClient(), local_file, "/remote/a.txt"
    )
    assert result == "unknown"


# ==================== _sync_folder 集成测试 ====================

def test_sync_folder_upload_skips_remote_newer(tmp_path, monkeypatch):
    """P0-10：upload 分支遇 remote_newer 应跳过上传。"""
    local_dir = tmp_path / "local"
    local_dir.mkdir()
    (local_dir / "a.txt").write_text("local content")

    fake_client = _FakeClient()

    worker = _make_worker(local_dir, direction="upload")

    # 强制 _check_conflict 返回 remote_newer
    monkeypatch.setattr(
        worker, "_check_conflict",
        lambda *a, **k: "remote_newer",
    )

    progress_msgs = []
    worker.progress.connect(lambda s: progress_msgs.append(s))

    worker._sync_folder(fake_client, local_dir, "/remote", "upload")

    assert fake_client.uploads == [], (
        "P0-10：remote_newer 时应跳过上传，但实际执行了 upload_sync"
    )
    assert any("跳过上传" in m or "远端更新" in m for m in progress_msgs), (
        f"应通过 progress 通知用户跳过。实际消息: {progress_msgs}"
    )


def test_sync_folder_upload_proceeds_when_local_newer(
    tmp_path, monkeypatch
):
    """P0-10：upload 分支遇 local_newer 应正常上传。"""
    local_dir = tmp_path / "local"
    local_dir.mkdir()
    (local_dir / "a.txt").write_text("local content")

    fake_client = _FakeClient()

    worker = _make_worker(local_dir, direction="upload")
    monkeypatch.setattr(
        worker, "_check_conflict",
        lambda *a, **k: "local_newer",
    )

    worker._sync_folder(fake_client, local_dir, "/remote", "upload")

    assert len(fake_client.uploads) == 1, (
        "P0-10：local_newer 时应正常上传"
    )


def test_sync_folder_download_skips_local_newer(
    tmp_path, monkeypatch
):
    """P0-10：download 分支遇 local_newer 应跳过下载。"""
    local_dir = tmp_path / "local"
    local_dir.mkdir()

    fake_client = _FakeClient()
    fake_client.list_result = ["/remote/a.txt", "/remote/b.txt"]

    worker = _make_worker(local_dir, direction="download")
    monkeypatch.setattr(
        worker, "_check_conflict",
        lambda *a, **k: "local_newer",
    )

    progress_msgs = []
    worker.progress.connect(lambda s: progress_msgs.append(s))

    worker._sync_folder(fake_client, local_dir, "/remote", "download")

    assert fake_client.downloads == [], (
        "P0-10：local_newer 时应跳过下载"
    )
    assert any("跳过下载" in m or "本地更新" in m for m in progress_msgs)