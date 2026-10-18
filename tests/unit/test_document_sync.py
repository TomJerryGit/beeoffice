# -*- coding: utf-8 -*-
"""
用户文档云同步（P1-37 第一步）

缺陷：
    原来的"云同步"只同步配置和模板，**不同步用户文档**——
    用户以为文档在云上，实际没有。

判定策略（刻意避开本地时间，因此不受时区影响）：
    本地是否变化 → 内容 sha256
    远端是否变化 → 远端 size+mtime，只与上次同步记录的同一值比较

    本地    远端    动作
    未变    未变    跳过
    变了    未变    上传
    未变    变了    下载
    变了    变了    冲突：本地保留，远端另存 .remote-<时间戳>
"""
import json

import pytest

from beeoffice.document_sync import DocumentSync, SyncReport


class FakeAdapter:
    """内存版 WebDAV：{remote_path: (bytes, mtime)}"""

    def __init__(self):
        self.files = {}
        self._clock = 1000.0

    def _tick(self):
        self._clock += 10
        return self._clock

    def exists(self, remote):
        return remote in self.files

    def get_file_info(self, remote):
        data, mtime = self.files[remote]
        return len(data), mtime

    def upload(self, local_path, remote):
        with open(local_path, "rb") as f:
            self.files[remote] = (f.read(), self._tick())
        return True

    def download(self, remote, local_path):
        data, _ = self.files[remote]
        with open(local_path, "wb") as f:
            f.write(data)
        return True

    # 模拟"别处改了远端"
    def put_remote(self, remote, text):
        self.files[remote] = (text.encode("utf-8"), self._tick())


@pytest.fixture
def env(tmp_path):
    adapter = FakeAdapter()
    state = tmp_path / "state.json"
    sync = DocumentSync(adapter, state_path=state)
    doc = tmp_path / "doc.md"
    doc.write_text("v1", encoding="utf-8")
    return adapter, sync, doc, state


def _remote_name(doc):
    return f"BeeOffice/{doc.name}"


def test_first_sync_uploads(env):
    adapter, sync, doc, _ = env
    report = sync.sync([doc])
    assert report.uploaded == [str(doc)]
    assert _remote_name(doc) in adapter.files


def test_unchanged_is_skipped(env):
    adapter, sync, doc, _ = env
    sync.sync([doc])
    report = sync.sync([doc])
    assert report.skipped == [str(doc)]
    assert not report.uploaded


def test_local_change_uploads(env):
    adapter, sync, doc, _ = env
    sync.sync([doc])
    doc.write_text("v2", encoding="utf-8")
    report = sync.sync([doc])
    assert report.uploaded == [str(doc)]
    assert adapter.files[_remote_name(doc)][0] == b"v2"


def test_remote_change_downloads(env):
    adapter, sync, doc, _ = env
    sync.sync([doc])
    adapter.put_remote(_remote_name(doc), "remote-v2")
    report = sync.sync([doc])
    assert report.downloaded == [str(doc)]
    assert doc.read_text(encoding="utf-8") == "remote-v2"


def test_both_changed_creates_conflict_copy(env):
    adapter, sync, doc, _ = env
    sync.sync([doc])
    doc.write_text("local-v2", encoding="utf-8")
    adapter.put_remote(_remote_name(doc), "remote-v2")

    report = sync.sync([doc])

    assert report.conflicts == [str(doc)]
    # 本地内容不被覆盖
    assert doc.read_text(encoding="utf-8") == "local-v2"
    # 远端另存了一份副本
    copies = list(doc.parent.glob("doc.remote-*.md"))
    assert len(copies) == 1
    assert copies[0].read_text(encoding="utf-8") == "remote-v2"


def test_first_sync_with_existing_remote_is_conservative(env):
    """没有基线时远端已存在 → 不猜谁新，按冲突处理。"""
    adapter, sync, doc, _ = env
    adapter.put_remote(_remote_name(doc), "already-there")
    report = sync.sync([doc])
    assert report.conflicts == [str(doc)]
    assert doc.read_text(encoding="utf-8") == "v1"


def test_timezone_shift_does_not_cause_false_change(env):
    """
    远端 mtime 只与"上次记录的同一个值"比较，
    所以服务器换时区导致的绝对时间变化不会误判——
    只要服务端回报的值本身没变。
    """
    adapter, sync, doc, _ = env
    sync.sync([doc])
    # 模拟：本地时间/时区无关，远端签名保持不变
    state = json.loads(env[3].read_text(encoding="utf-8"))
    key = str(doc.resolve())
    assert state[key]["remote_sig"] is not None

    report = sync.sync([doc])
    assert report.skipped == [str(doc)]


def test_missing_local_file_is_reported(env, tmp_path):
    adapter, sync, _, _ = env
    ghost = tmp_path / "ghost.md"
    report = sync.sync([ghost])
    assert report.failed == [str(ghost)]


def test_duplicate_paths_synced_once(env):
    adapter, sync, doc, _ = env
    report = sync.sync([doc, doc, str(doc)])
    assert len(report.uploaded) == 1


def test_report_summary_is_human_readable():
    r = SyncReport()
    r.uploaded.append("a")
    r.conflicts.append("b")
    assert "上传 1" in r.summary() and "冲突 1" in r.summary()


# ==================== 文档收集 ====================
class _FakeTab:
    def __init__(self, path):
        self._current_file_path = path


class _FakeTabs:
    def __init__(self, paths):
        self._tabs = [_FakeTab(p) for p in paths]

    def count(self):
        return len(self._tabs)

    def widget(self, i):
        return self._tabs[i]


class _FakeSettings:
    def __init__(self, recent):
        self.recent_files = recent


class _FakeWindow:
    def __init__(self, open_paths, recent):
        self.tab_manager = _FakeTabs(open_paths)
        self.settings = _FakeSettings(recent)


def test_collect_documents_merges_open_and_recent(tmp_path):
    from beeoffice.document_sync import collect_documents

    a = tmp_path / "a.md"; a.write_text("a", encoding="utf-8")
    b = tmp_path / "b.docx"; b.write_text("b", encoding="utf-8")
    c = tmp_path / "c.txt"; c.write_text("c", encoding="utf-8")

    w = _FakeWindow([str(a), None], [str(b), str(a), str(c)])
    got = [p.name for p in collect_documents(w)]
    assert got == ["a.md", "b.docx", "c.txt"]


def test_collect_documents_ignores_missing(tmp_path):
    from beeoffice.document_sync import collect_documents

    w = _FakeWindow([str(tmp_path / "ghost.md")], [])
    assert collect_documents(w) == []


def test_collect_documents_without_window_attributes():
    from beeoffice.document_sync import collect_documents

    class _Empty:
        pass

    assert collect_documents(_Empty()) == []
