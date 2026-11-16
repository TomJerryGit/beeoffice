"""Wave 4：BeeSheet 视图/网格/打印/XLSX 往返测试。"""
import pandas as pd
from PySide6.QtWidgets import QDialog, QFileDialog
from PySide6.QtPrintSupport import QPrintPreviewDialog

from beeoffice.plugins.beesheet import BeeSheetView


def make_sheet(qtbot, df=None):
    v = BeeSheetView()
    qtbot.addWidget(v)
    v.model.set_full_dataframe(
        df if df is not None else pd.DataFrame({"A": [1, 2], "B": ["x", "y"]})
    )
    v.table_view.setModel(v.model)
    return v


def test_grid_expands_lazily(qtbot):
    sheet = make_sheet(qtbot)
    before = sheet.model.rowCount()
    sheet.model.ensure_display_rows(8000)
    assert sheet.model.rowCount() >= 8000
    assert before >= 5000
    # 不实际分配 8000 行数据
    assert len(sheet.model.df) <= before


def test_view_toggles_and_zoom(qtbot):
    sheet = make_sheet(qtbot)
    assert sheet.table_view.showGrid() is True
    sheet._toggle_grid_lines()
    assert sheet.table_view.showGrid() is False
    sheet._toggle_grid_lines()
    assert sheet.table_view.showGrid() is True

    assert sheet.table_view.horizontalHeader().isHidden() is False
    sheet._toggle_headers()
    assert sheet.table_view.horizontalHeader().isHidden() is True
    sheet._toggle_headers()
    assert sheet.table_view.horizontalHeader().isHidden() is False

    sheet._apply_zoom(150)
    assert sheet._zoom_percent == 150
    sheet._apply_zoom(100)


def test_page_layout_mode(qtbot):
    sheet = make_sheet(qtbot)
    sheet._show_page_layout()
    assert sheet._page_layout_mode is True
    sheet._show_page_layout()
    assert sheet._page_layout_mode is False


def test_page_break_preview_mock(qtbot, monkeypatch):
    sheet = make_sheet(qtbot)
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)
    monkeypatch.setattr(QPrintPreviewDialog, "exec", lambda self: 0)
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    sheet._show_page_break_preview()


def test_xlsx_data_roundtrip(qtbot, tmp_path, monkeypatch):
    src = tmp_path / "in.xlsx"
    df = pd.DataFrame({"名称": ["甲", "乙"], "数量": [1, 2]})
    df.to_excel(src, index=False)
    sheet = make_sheet(qtbot)
    loaded = sheet._read_sheet_file(str(src))
    assert list(loaded["名称"]) == ["甲", "乙"]
    sheet.model.set_full_dataframe(loaded)

    out = tmp_path / "out.xlsx"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (str(out), "Excel (*.xlsx)")),
    )
    monkeypatch.setattr(sheet, "_set_status", lambda *a, **k: None)
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    sheet._export_xlsx()
    assert out.exists()
    back = pd.read_excel(out)
    assert list(back["名称"]) == ["甲", "乙"]


def test_print_scale_and_footer_settings(qtbot):
    sheet = make_sheet(qtbot)
    sheet._print_settings["scale"] = 80
    sheet._print_settings["footer"] = "第 {page} 页"
    html = sheet._build_print_html()
    assert "第 1 页" in html
    assert sheet._print_settings["scale"] == 80
