# tests/fidelity/test_close_unsaved_guard.py
"""
P0 止血回归（审计 §4.3 G1/G3）：关闭主窗口的未保存检查。

## 为什么必须存在
审计实测：新建标签写入内容后直接 `window.close()`，**没有任何弹窗**，
关闭后草稿目录为空 —— 用户点 X/Alt+F4 会静默丢失最近一次自动保存之后的修改。
本文件把"关闭前必须问、取消必须不关、不保存必须留草稿"固化成回归。

同时覆盖 G3：自动保存必须遍历**所有**脏标签，而不只是当前标签。
"""
import pytest
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox, QWidget

from beeoffice import drafts as drafts_mod
from beeoffice.app import BeeApp

@pytest.fixture
def draft_dir(tmp_path, monkeypatch):
    """把草稿目录隔离到 tmp，避免写真实 ~/.beeoffice_drafts。"""
    d = tmp_path / "drafts"
    monkeypatch.setenv("BEEOFFICE_DRAFT_DIR", str(d))
    return d


def _new_dirty_editor(app):
    """新建一个蜜写标签并写入"未保存"内容。"""
    editor = app._new_beewrite()
    editor.set_content("# 标题\n\n这段内容没有保存")
    return editor


# ==================== 关闭检查 ====================

def test_clean_app_needs_no_prompt(app, monkeypatch):
    """没有脏标签时不应弹任何对话框。"""
    asked = []
    monkeypatch.setattr(
        app, "_ask_close_tab",
        lambda widget, title, has_path: asked.append(title) or "cancel",
    )
    assert app._dirty_tabs() == []
    assert app._confirm_close_all_tabs() is True
    assert asked == [], "没有未保存内容却弹了关闭确认框"


def test_cancel_aborts_close(app, draft_dir, monkeypatch):
    """用户选「取消」→ closeEvent 必须 ignore，且不写草稿垃圾。"""
    _new_dirty_editor(app)
    assert len(app._dirty_tabs()) == 1

    monkeypatch.setattr(
        app, "_ask_close_tab", lambda widget, title, has_path: "cancel"
    )
    # app fixture 默认把关闭检查短路成 True（避免 teardown 弹框）；
    # 这里显式换回真实实现来验证 closeEvent 行为。
    monkeypatch.setattr(
        app, "_confirm_close_all_tabs",
        lambda: BeeApp._confirm_close_all_tabs(app),
    )
    event = QCloseEvent()
    app.closeEvent(event)

    assert event.isAccepted() is False, "用户取消后窗口不应被关闭"
    assert drafts_mod.list_drafts() == [], "取消关闭时不应留下草稿"


def test_discard_unsaved_new_doc_writes_draft(app, draft_dir, monkeypatch):
    """对"从未保存到文件"的文档选「不保存」→ 关闭前写草稿兜底。"""
    _new_dirty_editor(app)
    monkeypatch.setattr(
        app, "_ask_close_tab", lambda widget, title, has_path: "discard"
    )

    assert BeeApp._confirm_close_all_tabs(app) is True

    entries = drafts_mod.list_drafts()
    assert len(entries) == 1, "选择了不保存也没有留下草稿，内容永久丢失"
    restored = entries[0].path.read_text(encoding="utf-8")
    assert "这段内容没有保存" in restored
    assert entries[0].kind == "doc"


def test_save_failure_aborts_close(app, draft_dir, monkeypatch):
    """选「保存」但保存失败（含另存为取消）→ 必须中止关闭，不能丢数据。"""
    _new_dirty_editor(app)
    monkeypatch.setattr(
        app, "_ask_close_tab", lambda widget, title, has_path: "save"
    )
    monkeypatch.setattr(app, "_save_widget", lambda widget: False)
    monkeypatch.setattr(
        QMessageBox, "warning",
        staticmethod(lambda *a, **k: QMessageBox.Ok),
    )

    assert BeeApp._confirm_close_all_tabs(app) is False


def test_save_success_allows_close(app, draft_dir, monkeypatch):
    """选「保存」且保存成功 → 允许关闭，并清掉草稿。"""
    editor = _new_dirty_editor(app)
    monkeypatch.setattr(
        app, "_ask_close_tab", lambda widget, title, has_path: "save"
    )
    monkeypatch.setattr(app, "_backup_before_save", lambda *a, **k: True)
    monkeypatch.setattr(editor, "save", lambda: True)

    assert BeeApp._confirm_close_all_tabs(app) is True


def test_close_event_ignored_when_confirm_raises(app, draft_dir, monkeypatch):
    """检查逻辑自身异常时也必须中止关闭（宁可关不掉，也不能丢数据）。"""
    _new_dirty_editor(app)
    monkeypatch.setattr(
        app, "_confirm_close_all_tabs",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    event = QCloseEvent()
    app.closeEvent(event)
    assert event.isAccepted() is False


# ==================== 自动保存覆盖所有标签（G3） ====================

def test_autosave_covers_background_tabs(app, tmp_path, monkeypatch):
    """当前标签是 A，脏标签是后台的 B —— B 也必须被自动保存。"""
    monkeypatch.setattr(app, "_backup_before_save", lambda *a, **k: True)

    class _FakeWidget(QWidget):
        def __init__(self, path):
            super().__init__()
            self._current_file_path = str(path)
            self._text = "初始"
            self.saved = []

        def content(self):
            return self._text

        def save(self):
            self.saved.append(self._text)
            return True

    first = _FakeWidget(tmp_path / "first.md")
    second = _FakeWidget(tmp_path / "second.md")
    for widget, title in ((first, "第一个"), (second, "第二个")):
        app.tab_manager.addTab(widget, title)

    # 两个都改，但当前页停在 first —— 原实现只会保存 first
    first._text = "first 改过"
    second._text = "second 改过"
    app.tab_manager.setCurrentWidget(first)

    app._autosave()

    assert first.saved, "当前标签没有自动保存"
    assert second.saved, "后台标签没有自动保存（G3 未修）"
    first.close()
    second.close()


def test_autosave_does_not_call_save_without_path(app, tmp_path, monkeypatch):
    """没有当前文件的标签不能调 save()（会退化成另存为、每 5 分钟弹框）。"""
    monkeypatch.setattr(app, "_backup_before_save", lambda *a, **k: True)

    class _FakeWidget(QWidget):
        def __init__(self):
            super().__init__()
            self._text = "初始"
            self.saved = []

        def content(self):
            return self._text

        def save(self):
            self.saved.append(1)
            return True

    widget = _FakeWidget()
    app.tab_manager.addTab(widget, "无路径")
    widget._text = "改过"

    app._autosave()

    assert not widget.saved, "无路径标签被自动保存（会弹另存对话框）"
    assert app._has_unsaved_changes(widget)
    widget.close()
