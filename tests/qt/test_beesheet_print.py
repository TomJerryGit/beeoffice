"""BeeSheet 页面/打印 P0 测试。"""
import pandas as pd
from PySide6.QtCore import QItemSelection, QItemSelectionModel
from PySide6.QtWidgets import QDialog

from beeoffice.plugins.beesheet import BeeSheetView


def make_sheet(qtbot):
    v = BeeSheetView()
    qtbot.addWidget(v)
    v.model.set_full_dataframe(
        pd.DataFrame({"商品": ["苹果", "香蕉"], "数量": [10, 20]})
    )
    v.table_view.setModel(v.model)
    return v


def test_print_html_contains_data(qtbot):
    sheet = make_sheet(qtbot)
    html = sheet._build_print_html()
    assert "商品" in html
    assert "苹果" in html
    assert "数量" in html
    assert "<table" in html


def test_print_area_limits_data(qtbot):
    sheet = make_sheet(qtbot)
    sel = QItemSelection(
        sheet.model.index(0, 0), sheet.model.index(1, 1)
    )
    sheet.table_view.selectionModel().select(
        sel, QItemSelectionModel.ClearAndSelect
    )
    sheet._set_print_area()
    html = sheet._build_print_html()
    assert "苹果" in html and "香蕉" in html
    assert sheet._print_settings["area"] == (0, 0, 1, 1)
    sheet._clear_print_area()
    assert sheet._print_settings["area"] is None


def test_print_preview_does_not_block(qtbot, monkeypatch):
    sheet = make_sheet(qtbot)
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)
    # QPrintPreviewDialog 的 exec 也走 QDialog.exec
    sheet._show_print_preview()


def test_print_settings_defaults(qtbot):
    sheet = make_sheet(qtbot)
    s = sheet._print_settings
    assert s["paper"] == "A4"
    assert s["orientation"] == "portrait"
    assert s["gridlines"] is True
