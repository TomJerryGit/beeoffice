"""GUI 覆盖率批次：Beewrite 视图/阅读/分屏/缩放。"""
import pytest
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox

from beeoffice.plugins.beewrite import BeeWriteEditor


@pytest.fixture
def editor(qtbot, monkeypatch):
    ed = BeeWriteEditor()
    qtbot.addWidget(ed)
    ed._switch_mode("rich_text")
    ed.rich_editor.setPlainText("hello world\nline two")
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    return ed


def test_reading_mode(editor):
    editor._enter_reading_mode()
    assert editor._reading_mode is True
    editor._exit_reading_mode()
    assert editor._reading_mode is False
    editor._toggle_reading_mode()
    editor._toggle_reading_mode()


def test_outline_and_find(editor):
    editor._toggle_outline()
    editor._toggle_outline()
    editor._find_current()
    editor._close_find_bar()


def test_zoom(editor):
    editor._zoom_in()
    editor._zoom_out()
    editor._zoom_reset()
    editor._set_zoom(150)
    assert editor._zoom_percent == 150


def test_status_and_page_count(editor):
    editor._update_status_bar()
    assert editor._estimate_page_count() >= 1
    editor._update_page_count()
    editor._update_cursor_position()


def test_paste_undo_redo(editor):
    QApplication.clipboard().setText("pasted")
    editor.rich_editor.moveCursor(QTextCursor.End)
    editor._paste_plain()
    assert "pasted" in editor.rich_editor.toPlainText()
    editor._undo()
    editor._redo()


def test_split_view_cancel_and_open(editor, monkeypatch, tmp_path):
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    editor._enter_split_view()  # 取消
    f = tmp_path / "compare.md"
    f.write_text("other", encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(f), ""))
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)
    editor._enter_split_view()
    editor._toggle_split_view()
    editor._exit_split_view()
