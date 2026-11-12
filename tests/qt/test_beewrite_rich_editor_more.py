"""GUI 覆盖率批次：RichTextEditor 转换/粘贴/表格。"""
import pandas as pd
import pytest
from PySide6.QtCore import QMimeData, QPoint, Qt
from PySide6.QtGui import QTextCursor

from beeoffice.plugins.beewrite_rich_editor import RichTextEditor


@pytest.fixture
def editor(qtbot):
    e = RichTextEditor()
    qtbot.addWidget(e)
    return e


def test_empty_cursor_and_breaks(editor):
    assert editor._is_empty_doc() is True
    assert isinstance(editor._cursor_at_end(), QTextCursor)
    assert editor._current_block_is_empty(editor.textCursor()) is True
    editor.insertPlainText("hello")
    assert editor._is_empty_doc() is False
    editor.insert_horizontal_line()
    editor.insert_page_break()
    editor.insert_section_break()
    editor.insert_current_date()


def test_markdown_roundtrip(editor):
    md = "# 标题\n\n**粗体** *斜体* `code`\n\n- a\n- b\n\n| A | B |\n|---|---|\n| 1 | 2 |\n"
    editor.set_markdown(md)
    out = editor.to_markdown()
    assert "标题" in out
    assert "粗体" in out
    assert "|" in out


def test_tsv_paste_and_helpers(editor):
    mime = QMimeData()
    mime.setText("A\tB\n1\t2\n3\t4")
    assert editor._looks_like_tsv_table("A\tB\n1\t2") is True
    assert editor._looks_like_tsv_table("plain text") is False
    assert editor._parse_tsv("A\tB\n1\t2") == [["A", "B"], ["1", "2"]]
    assert editor._split_md_row("| A | B |") == ["A", "B"]
    editor.insertFromMimeData(mime)
    assert editor.to_markdown()


def test_dataframe_table(editor):
    editor.insert_dataframe_table(pd.DataFrame({"A": [1, 2], "B": ["x", "y"]}))
    assert "| A | B |" in editor.to_markdown() or "A" in editor.toPlainText()


def test_heading_lists_quote(editor):
    editor._insert_heading("标题", 2)
    editor._insert_code_block('print(1)')
    editor._insert_quote('引用')
    editor._insert_list_item("item")
    editor._insert_block()
    assert editor.toPlainText() != ""
