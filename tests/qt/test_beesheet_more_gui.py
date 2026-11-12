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


def test_sort_and_dialogs(sheet, monkeypatch):
    sheet.model.set_full_dataframe(pd.DataFrame({"A": [3, 1, 2]}))
    sheet.sort_by_column(0, ascending=True)
    assert list(sheet.model._loaded_df["A"]) == [1, 2, 3]
    sheet.sort_by_column(0, ascending=False)
    assert list(sheet.model._loaded_df["A"]) == [3, 2, 1]
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)
    sheet._show_sort_dialog()
    sheet._show_find_replace()
    sheet._update_info_panel()
    sheet._on_cell_selected(sheet.model.index(0, 0), None)


def test_nl_filter(sheet, monkeypatch):
    sheet.model.set_full_dataframe(pd.DataFrame({"A": [1, 2, 3]}))
    sheet.table_view.setModel(sheet.model)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    sheet._apply_nl_filter(">", "1")
    assert len(sheet.model.df) >= 2
    sheet._apply_nl_filter("", "")


def test_auto_save(sheet, monkeypatch, tmp_path):
    import beeoffice.plugins.beesheet as m
    monkeypatch.setattr(m.Path, "home", staticmethod(lambda: tmp_path))
    sheet._dirty = True
    sheet._auto_save()
    backups = list((tmp_path / ".beeoffice_backups").glob("backup_*.json"))
    assert backups


def test_close_event(sheet):
    class Ev:
        def __init__(self): self.accepted = False
        def accept(self): self.accepted = True
        def ignore(self): pass
    ev = Ev()
    sheet.closeEvent(ev)


def test_selection_stats_dialog(sheet, monkeypatch):
    from PySide6.QtWidgets import QDialog, QMessageBox
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    sheet.model.set_full_dataframe(pd.DataFrame({
        "A": [1, 2, None], "B": ["x", "", "y"]
    }))
    sheet.table_view.setModel(sheet.model)
    sheet.table_view.selectAll()
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)
    sheet._show_selection_stats()
    # 无选区直接返回
    sheet.table_view.clearSelection()
    sheet._show_selection_stats()


class FakeAction:
    def __init__(self):
        class Sig:
            def connect(self, fn): pass
        self.triggered = Sig()

class FakeMenu:
    def __init__(self, *a, **k): pass
    def addAction(self, text=None, *a): return FakeAction()
    def addSeparator(self): pass
    def addMenu(self, text): return FakeMenu()
    def addSection(self, text): pass
    def exec(self, *a, **k): pass

def test_filter_and_conditional_menus(sheet, monkeypatch):
    import beeoffice.plugins.beesheet_data_mixin as m
    from PySide6.QtWidgets import QDialog
    monkeypatch.setattr(m, "QMenu", FakeMenu)
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)
    sheet._show_filter_popup(0)
    sheet._show_filter_dialog()
    from PySide6.QtCore import QPoint
    sheet._show_header_context_menu(QPoint(0, 0))
    sheet._show_row_header_menu(QPoint(0, 0))
