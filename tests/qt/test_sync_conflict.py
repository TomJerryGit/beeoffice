# -*- coding: utf-8 -*-
"""
同步冲突处理（阶段三 #7）

背景：
    冲突时只留一个 `.remote-<时间戳>` 副本，用户得自己去文件管理器比对，
    对普通用户等于"没处理"。

最小可用版：
    冲突列表 + 三个动作（保留本地 / 采用远端 / 两个都留），
    处理后把基线更新成当前值，下一次同步不会再判成冲突。
"""
import pytest

pytest.importorskip("PySide6.QtWidgets")

from beeoffice.document_sync import DocumentSync  # noqa: E402


class FakeAdapter:
    def __init__(self):
        self.files = {}
        self._clock = 1000.0

    def _tick(self):
        self._clock += 10
        return self._clock

    def exists(self, r):
        return r in self.files

    def get_file_info(self, r):
        data, mtime = self.files[r]
        return len(data), mtime

    def upload(self, lp, r):
        with open(lp, "rb") as f:
            self.files[r] = (f.read(), self._tick())
        return True

    def download(self, r, lp):
        Path = __import__("pathlib").Path
        Path(lp).write_bytes(self.files[r][0])
        return True

    def put_remote(self, r, text):
        self.files[r] = (text.encode("utf-8"), self._tick())


@pytest.fixture
def conflicted(tmp_path):
    """制造一个"两边都改过"的冲突，返回 (sync, adapter, doc, detail)。"""
    adapter = FakeAdapter()
    sync = DocumentSync(adapter, state_path=tmp_path / "state.json")
    doc = tmp_path / "doc.md"
    doc.write_text("v1", encoding="utf-8")

    sync.sync([doc])                                  # 建立基线
    doc.write_text("local-v2", encoding="utf-8")      # 本地改
    adapter.put_remote(sync.remote_path_for(doc), "remote-v2")   # 远端改（不同长度）

    report = sync.sync([doc])
    assert report.conflicts == [str(doc)]
    detail = report.conflict_details[0]
    return sync, adapter, doc, detail


def test_conflict_detail_has_both_sides(conflicted):
    _, _, doc, detail = conflicted
    assert detail["local"] == str(doc)
    assert detail["remote_copy"]
    assert detail["remote"].startswith("BeeOffice/")


def test_resolve_keep_local_uploads_local(conflicted):
    sync, adapter, doc, detail = conflicted
    assert sync.resolve_conflict(detail, "local") is True
    assert adapter.files[detail["remote"]][0] == b"local-v2"
    assert doc.read_text(encoding="utf-8") == "local-v2"


def test_resolve_take_remote_overwrites_local(conflicted):
    sync, adapter, doc, detail = conflicted
    assert sync.resolve_conflict(detail, "remote") is True
    assert doc.read_text(encoding="utf-8") == "remote-v2"
    import os
    assert not os.path.exists(detail["remote_copy"]), "采用远端后副本应清理"


def test_resolve_keep_both_leaves_files(conflicted):
    sync, adapter, doc, detail = conflicted
    assert sync.resolve_conflict(detail, "both") is True
    assert doc.read_text(encoding="utf-8") == "local-v2"
    import os
    assert os.path.exists(detail["remote_copy"]), "两个都留时副本必须保留"


def test_after_resolution_next_sync_is_clean(conflicted):
    """处理完冲突后，下一次同步不应再报冲突。"""
    sync, adapter, doc, detail = conflicted
    sync.resolve_conflict(detail, "local")
    report = sync.sync([doc])
    assert report.conflicts == []
    assert report.skipped == [str(doc)] or report.uploaded == [str(doc)]


def test_unknown_action_is_rejected(conflicted):
    sync, adapter, doc, detail = conflicted
    assert sync.resolve_conflict(detail, "nonsense") is False


# ==================== 对话框 ====================
def test_dialog_lists_conflicts_and_removes_on_action(qtbot, conflicted):
    from beeoffice.plugins.sync_conflict_dialog import SyncConflictDialog

    sync, adapter, doc, detail = conflicted
    dlg = SyncConflictDialog(sync, [detail])
    qtbot.addWidget(dlg)

    assert dlg._list.count() == 1
    dlg._list.setCurrentRow(0)
    dlg._apply("both")

    assert dlg._list.count() == 0
    assert dlg._resolved == 1
    assert "已处理" in dlg._status.text()


def test_dialog_without_selection_prompts(qtbot, conflicted):
    from beeoffice.plugins.sync_conflict_dialog import SyncConflictDialog

    sync, adapter, doc, detail = conflicted
    dlg = SyncConflictDialog(sync, [detail])
    qtbot.addWidget(dlg)

    dlg._apply("local")          # 未选中任何项
    assert "请先" in dlg._status.text()
    assert dlg._list.count() == 1
