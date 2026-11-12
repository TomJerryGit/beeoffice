"""GUI 覆盖率批次：RichTextEditor 表格/快捷键/右键菜单。"""
import pytest
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QColor, QKeyEvent, QTextCursor
from PySide6.QtWidgets import QColorDialog

from beeoffice.plugins.beewrite_rich_editor import RichTextEditor


@pytest.fixture
def editor(qtbot):
    e = RichTextEditor()
    qtbot.addWidget(e)
    return e


def make_table(editor, rows=2, cols=2):
    cursor = editor.textCursor()
    table = cursor.insertTable(rows, cols)
    for r in range(rows):
        for c in range(cols):
            table.cellAt(r, c).firstCursorPosition().insertText(f"{r}{c}")
    editor.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
    return table


def test_tab_and_backtab(editor):
    table = make_table(editor)
    ev = QKeyEvent(QEvent.KeyPress, Qt.Key_Tab, Qt.NoModifier)
    editor.keyPressEvent(ev)
    cell = table.cellAt(editor.textCursor())
    assert (cell.row(), cell.column()) == (0, 1)
    ev2 = QKeyEvent(QEvent.KeyPress, Qt.Key_Backtab, Qt.ShiftModifier)
    editor.keyPressEvent(ev2)
    cell = table.cellAt(editor.textCursor())
    assert (cell.row(), cell.column()) == (0, 0)
    # 最后一格 Tab 自动加行
    table = make_table(editor, 1, 1)
    editor.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
    editor.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Tab, Qt.NoModifier))
    assert table.rows() == 2


def test_table_row_col_ops(editor):
    table = make_table(editor)
    editor._insert_row(table, 1)
    assert table.rows() == 3
    editor._insert_col(table, 1)
    assert table.columns() == 3
    assert table.rows() == 3 and table.columns() == 3


def test_table_merge_split(editor):
    table = make_table(editor)
    cursor = editor.textCursor()
    cursor.setPosition(table.cellAt(0, 0).firstCursorPosition().position())
    cursor.setPosition(
        table.cellAt(1, 1).firstCursorPosition().position(),
        QTextCursor.KeepAnchor,
    )
    editor.setTextCursor(cursor)
    editor._merge_cells(table)
    assert table.cellAt(0, 0).rowSpan() == 2
    editor.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
    editor._split_cell(table)
    assert table.rows() >= 2


class FakeAction:
    def __init__(self):
        class Sig:
            def connect(self, fn): pass
        self.triggered = Sig()


class FakeMenu:
    def addSeparator(self): pass
    def addAction(self, *a, **k): return FakeAction()
    def exec(self, *a, **k): pass


def test_context_menu(editor, monkeypatch):
    make_table(editor)
    monkeypatch.setattr(editor, "createStandardContextMenu", lambda: FakeMenu())
    class Ev:
        def globalPos(self): return QPoint(0, 0)
    editor.contextMenuEvent(Ev())


def test_cell_colors(editor, monkeypatch):
    make_table(editor)
    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor("red")))
    editor._cell_bg()
    editor._cell_fg()
