"""Wave 2：BeeSheet 审阅/公式/打印页眉页脚测试。"""
import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QInputDialog, QMessageBox

from beeoffice.plugins.beesheet import BeeSheetView


def make_sheet(qtbot):
    v = BeeSheetView()
    qtbot.addWidget(v)
    v.model.set_full_dataframe(pd.DataFrame({"A": [1, 2], "B": ["teh", "ok"]}))
    v.table_view.setModel(v.model)
    return v


def test_sheet_protection(qtbot, monkeypatch):
    sheet = make_sheet(qtbot)
    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: ("pw", True))
    )
    sheet._toggle_sheet_protection()
    assert sheet._sheet_protected is True
    assert sheet.table_view.editTriggers() == QAbstractItemView.NoEditTriggers
    sheet._toggle_sheet_protection()
    assert sheet._sheet_protected is False
    # 取消保护后恢复可编辑
    assert sheet.table_view.editTriggers() != QAbstractItemView.NoEditTriggers


def test_workbook_protection_and_comments(qtbot, monkeypatch):
    sheet = make_sheet(qtbot)
    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: ("pw", True))
    )
    sheet._toggle_workbook_protection()
    assert sheet._workbook_protected is True
    sheet._cell_comments[(0, 0)] = "检查"
    captured = []
    monkeypatch.setattr(
        QMessageBox, "information",
        staticmethod(lambda *a, **k: captured.append(a)),
    )
    sheet._show_comments_list()
    assert captured and "检查" in str(captured[0])


def test_spell_check(qtbot, monkeypatch):
    sheet = make_sheet(qtbot)
    sheet.table_view.selectAll()
    captured = []
    monkeypatch.setattr(
        QMessageBox, "information",
        staticmethod(lambda *a, **k: captured.append(a)),
    )
    sheet._spell_check()
    assert captured
    assert "teh" in str(captured[0])


def test_show_formulas(qtbot):
    sheet = make_sheet(qtbot)
    sheet._formula_cells[(0, 0)] = "=1+1"
    sheet._toggle_show_formulas()
    assert sheet.model._show_formulas is True
    idx = sheet.model.index(0, 0)
    assert sheet.model.data(idx, Qt.DisplayRole) == "=1+1"
    sheet._toggle_show_formulas()
    assert sheet.model._show_formulas is False


def test_calc_mode_and_error_check(qtbot, monkeypatch):
    sheet = make_sheet(qtbot)
    sheet._set_calc_mode(False)
    assert sheet._auto_calc is False
    sheet._set_calc_mode(True)
    assert sheet._auto_calc is True
    captured = []
    monkeypatch.setattr(
        QMessageBox, "warning",
        staticmethod(lambda *a, **k: captured.append(a)),
    )
    sheet._formula_cells[(0, 0)] = "=1/0"
    sheet._check_formula_errors()
    assert captured


def test_print_header_footer(qtbot):
    sheet = make_sheet(qtbot)
    sheet._print_settings["header"] = "页眉 A"
    sheet._print_settings["footer"] = "第 {page} 页"
    html = sheet._build_print_html()
    assert "页眉 A" in html
    assert "第 1 页" in html
