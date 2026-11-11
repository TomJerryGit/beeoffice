"""GUI 覆盖率批次：BeeSheet 主视图零散交互。"""
import pandas as pd
import pytest
from PySide6.QtWidgets import QDialog, QInputDialog, QMessageBox

from beeoffice.plugins.beesheet import BeeSheetView


@pytest.fixture
def sheet(qtbot):
    v = BeeSheetView()
    qtbot.addWidget(v)
    v.model.set_full_dataframe(pd.DataFrame({"A": [1, 2], "B": ["x", "y"]}))
    v.table_view.setModel(v.model)
    return v


def test_toggle_toolbars_and_status(sheet):
    class Btn:
        def setText(self, text): self.text = text
    sheet._toggle_toolbars(Btn())
    sheet._set_status("ok", 1000)
    sheet._update_status()


def test_insert_date_time(sheet):
    sheet.table_view.setCurrentIndex(sheet.model.index(0, 0))
    sheet._insert_date_time('date')
    sheet._insert_date_time('time')


def test_auto_resize_and_names(sheet):
    sheet._auto_resize_columns()
    names = sheet._get_sheet_names()
    assert isinstance(names, list)


def test_goto_cell(sheet, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("B2", True))
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)
    sheet._show_goto_dialog()
    sheet._goto_cell("A2")
    assert sheet.table_view.currentIndex().row() == 1


def test_nl_formula(sheet, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    sheet.table_view.setCurrentIndex(sheet.model.index(0, 0))
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("求和A1到A2", True))
    sheet._nl_to_formula()


def test_comment(sheet, monkeypatch):
    sheet.table_view.setCurrentIndex(sheet.model.index(0, 0))
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("备注", True))
    monkeypatch.setattr(QInputDialog, "getMultiLineText", lambda *a, **k: ("批注", True))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    sheet._add_comment()
