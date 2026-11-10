"""BeeShow 表格编辑器补测。"""
import pytest
from PySide6.QtWidgets import QDialog, QMessageBox

from beeoffice.plugins.beeshow_table_mixin import TableEditorDialog


@pytest.fixture
def dlg(qtbot, monkeypatch):
    d = TableEditorDialog(initial_rows=[["a", "b"], ["1", "2"]])
    qtbot.addWidget(d)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    return d


def test_grid_and_markdown(dlg):
    assert dlg._get_grid() == [["a", "b"], ["1", "2"]]
    md = dlg.get_markdown_table()
    assert "| a | b |" in md
    assert "| 1 | 2 |" in md


def test_new_and_clear(dlg):
    dlg._row_spin.setValue(2)
    dlg._col_spin.setValue(3)
    dlg._on_new_table()
    assert dlg._table.rowCount() == 2
    assert dlg._table.columnCount() == 3
    dlg._load_rows([["x", "y"]])
    assert dlg.get_rows() == [["x", "y"]]
    dlg._on_clear()
    assert dlg.get_rows() == [["", ""]]


def test_insert_delete_rows_cols(dlg):
    dlg._table.setCurrentCell(0, 0)
    dlg._insert_row(1)
    assert dlg._table.rowCount() == 3
    dlg._delete_row()
    assert dlg._table.rowCount() == 2
    dlg._table.setCurrentCell(0, 0)
    dlg._insert_col(1)
    assert dlg._table.columnCount() == 3
    dlg._delete_col()
    assert dlg._table.columnCount() == 2


def test_move_row(dlg):
    dlg._table.setCurrentCell(0, 0)
    dlg._move_row(1)
    rows = dlg.get_rows()
    assert rows[0][0] == "1"


def test_header_toggle_and_accept(dlg):
    dlg._header_check.setChecked(False)
    dlg._on_header_changed()
    assert dlg.has_header() is False
    dlg._on_accept()
    assert dlg.result() == QDialog.Accepted


def test_accept_empty(monkeypatch):
    calls = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: calls.append(a))
    d = TableEditorDialog(initial_rows=[["", ""]])
    d._on_accept()
    assert calls
