"""BeeWrite 批注/书签/修订交互补测。"""
from pathlib import Path

import pytest
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QDialog, QInputDialog, QMessageBox

from beeoffice.plugins.beewrite import BeeWriteEditor


@pytest.fixture
def writer(qtbot, monkeypatch):
    ed = BeeWriteEditor()
    qtbot.addWidget(ed)
    ed._switch_mode("rich_text")
    ed.rich_editor.setPlainText("这是一段用于批注的测试文字")
    cursor = ed.rich_editor.textCursor()
    cursor.movePosition(QTextCursor.Start)
    cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, 4)
    ed.rich_editor.setTextCursor(cursor)
    class Panel:
        def setVisible(self, v): self.visible = v
        def refresh(self, *a): pass
    ed._comment_panel = Panel()
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    return ed


def test_annotation_paths(writer):
    c, b = writer._annotation_paths("C:/docs/a.md")
    assert c.name == "a.comments.json"
    assert b.name == "a.bookmarks.json"


def test_load_annotations_missing(writer, tmp_path):
    assert writer.load_annotations(None) == {"comments": False, "bookmarks": False}
    result = writer.load_annotations(str(tmp_path / "a.md"))
    assert result == {"comments": False, "bookmarks": False}


def test_add_comment(writer, monkeypatch):
    import beeoffice.plugins.beewrite_comment_mixin as m
    class FakeDlg:
        def __init__(self, *a, **k): pass
        def exec(self): return QDialog.Accepted
        def get_text(self): return "批注内容"
    monkeypatch.setattr(m, "CommentEditDialog", FakeDlg)
    writer._refresh_comment_panel = lambda: None
    writer._add_comment()
    assert writer._comment_manager.count() == 1


def test_add_comment_cancel(writer, monkeypatch):
    import beeoffice.plugins.beewrite_comment_mixin as m
    class FakeDlg:
        def __init__(self, *a, **k): pass
        def exec(self): return QDialog.Rejected
    monkeypatch.setattr(m, "CommentEditDialog", FakeDlg)
    writer._add_comment()
    assert writer._comment_manager.count() == 0


def test_add_bookmark(writer, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("我的书签", True))
    writer._add_bookmark()
    assert writer._bookmark_manager.count() == 1
    # 同名覆盖
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("我的书签", True))
    writer._add_bookmark()
    assert writer._bookmark_manager.count() == 1


def test_show_bookmark_list(writer, monkeypatch):
    calls = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: calls.append(a))
    writer._show_bookmark_list()
    assert calls
    writer._bookmark_manager.add("b1", 0, 1)
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)
    writer._show_bookmark_list()


def test_toggle_revision(writer, monkeypatch):
    writer._show_revision_diff = lambda: None
    writer._toggle_revision()
    assert writer._revision_manager.active is True
    writer._toggle_revision()
    assert writer._revision_manager.active is False
