"""Wave5 W2：Excel 组合图/页面背景/水印。"""
import pandas as pd
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QDialog, QInputDialog

from beeoffice.plugins.beesheet import BeeSheetView


def make_sheet(qtbot):
    s = BeeSheetView()
    qtbot.addWidget(s)
    s.model.set_full_dataframe(pd.DataFrame({"月份": ["1月", "2月"], "收入": [10, 20], "成本": [5, 8]}))
    s.table_view.setModel(s.model)
    s.table_view.selectAll()
    return s


def test_chart_combo_does_not_crash(qtbot, monkeypatch):
    s = make_sheet(qtbot)
    monkeypatch.setattr(QDialog, "show", lambda self: None)
    s._generate_chart("combo")
    assert hasattr(s, "_open_page_manager") is False


def test_sheet_background_and_watermark(qtbot, monkeypatch):
    s = make_sheet(qtbot)
    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor("#FFF3E0")))
    s._set_sheet_background()
    assert "fff3e0" in s.table_view.styleSheet().lower()
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("内部资料", True)))
    s._set_sheet_watermark()
    assert s._watermark_label is not None
    assert s._watermark_label.text() == "内部资料"
