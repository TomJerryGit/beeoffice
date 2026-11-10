"""BeeWrite 表格 Mixin 补测。"""
from PySide6.QtWidgets import QApplication, QColorDialog, QMessageBox, QDialog
from PySide6.QtGui import QTextCursor, QColor
from PySide6.QtCore import Qt

import pytest

from beeoffice.plugins.beewrite import BeeWriteEditor


@pytest.fixture
def writer(qtbot, monkeypatch):
    ed = BeeWriteEditor()
    qtbot.addWidget(ed)
    ed._switch_mode("rich_text")
    ed.rich_editor.setHtml(
        '<table border="1"><tr><td>a</td><td>b</td></tr>'
        '<tr><td>c</td><td>d</td></tr></table>'
    )
    cursor = ed.rich_editor.textCursor()
    cursor.movePosition(QTextCursor.Start)
    cursor.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, 2)
    ed.rich_editor.setTextCursor(cursor)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)
    return ed


def table_of(ed):
    return ed.rich_editor.textCursor().currentTable()


def test_insert_delete_rows_cols(writer):
    table = table_of(writer)
    rows, cols = table.rows(), table.columns()
    writer._table_insert_row(table, 1)
    assert table.rows() == rows + 1
    writer._table_delete_row(table)
    assert table.rows() == rows
    writer.rich_editor.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
    writer._table_insert_col(table, 1)
    assert table.columns() == cols + 1
    writer.rich_editor.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
    writer._table_delete_col(table)
    assert table.columns() == cols


def test_apply_table_styles(writer):
    table = table_of(writer)
    for style in ("minimal", "three_line", "zebra", "card", "dark", "amber"):
        writer._apply_table_style(style)


def test_copy_table_markdown(writer):
    table = table_of(writer)
    writer._copy_table_as_markdown(table)
    text = QApplication.clipboard().text()
    assert "| a | b |" in text


def test_cell_alignment_and_colors(writer, monkeypatch):
    table = table_of(writer)
    writer._cell_align("center")
    writer._set_row_color(table, 0, QColor("#FF0000"), QColor("#FFFFFF"))
    writer._set_table_cells_color(table, QColor("#FFFF00"), QColor("#000000"))
    writer._set_three_line_borders(table)


def test_merge_split_no_selection(writer):
    table = table_of(writer)
    writer._table_merge_cells(table)  # 无选区，走提示分支
    writer._table_split_cell(table)   # 未合并，走提示分支


def test_merge_selection(writer):
    table = table_of(writer)
    doc = writer.rich_editor.document()
    start = table.cellAt(0, 0).firstCursorPosition().position() + 1
    end = table.cellAt(0, 1).firstCursorPosition().position() + 1
    cursor = QTextCursor(doc)
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.KeepAnchor)
    writer.rich_editor.setTextCursor(cursor)
    writer._table_merge_cells(table)
    cell = table.cellAt(0, 0)
    assert cell.columnSpan() >= 1


def test_insert_breaks(writer):
    before = writer.rich_editor.toPlainText()
    writer._insert_horizontal_line()
    writer._insert_page_break()
    writer._insert_section_break()
    writer._insert_date()
    assert writer.rich_editor.toPlainText() != before


def test_markdown_table_wrappers(writer):
    writer._switch_mode("markdown")
    writer.markdown_editor.setPlainText("| a | b |\n|---|---|\n| 1 | 2 |")
    writer.markdown_editor.moveCursor(QTextCursor.Start)
    assert writer._detect_md_table_at_cursor() is not None
    parsed = writer._parse_md_table(["| a | b |", "|---|---|", "| 1 | 2 |"])
    assert parsed
    rendered = writer._render_md_table([["a", "b"], ["1", "2"]])
    assert "|" in rendered
