"""GUI 覆盖率批次：Beewrite 模式/格式 Mixin。"""
import pytest
from PySide6.QtGui import QColor, QTextCursor
from PySide6.QtWidgets import QColorDialog

from beeoffice.plugins.beewrite import BeeWriteEditor


@pytest.fixture
def editor(qtbot):
    ed = BeeWriteEditor()
    qtbot.addWidget(ed)
    ed._switch_mode("rich_text")
    ed.rich_editor.setPlainText("hello world\nsecond")
    cursor = ed.rich_editor.textCursor()
    cursor.movePosition(QTextCursor.Start)
    cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, 5)
    ed.rich_editor.setTextCursor(cursor)
    return ed


def test_inline_format_toggles(editor):
    editor._toggle_bold()
    editor._toggle_bold()
    editor._toggle_italic()
    editor._toggle_italic()
    editor._toggle_underline()
    editor._toggle_underline()
    editor._toggle_strikethrough()
    editor._toggle_strikethrough()


def test_colors_and_align(editor, monkeypatch):
    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor("red")))
    editor._set_text_color()
    editor._set_bg_color()
    editor._align_left()
    editor._align_center()
    editor._align_right()


def test_font_handlers(editor):
    editor._on_font_family("Arial")
    editor._on_font_size("14")
    editor._update_format_state()


def test_heading_and_lists(editor):
    editor._on_heading("标题 1")
    editor._on_heading("正文")
    editor._insert_list()
    editor._insert_ordered_list()


def test_mode_switch_and_docs(editor, qtbot):
    assert editor._document_has_images() is False
    assert list(editor._iter_all_tables(editor.rich_editor.document().rootFrame())) == []
    editor._switch_mode("markdown")
    assert editor._edit_mode == "markdown"
    editor._switch_mode("rich_text")
    assert editor._edit_mode == "rich_text"
    editor._toggle_toolbars()


def test_format_painter(editor):
    editor._toggle_format_painter(True)
    editor._toggle_format_painter(False)
