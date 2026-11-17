"""P0 硬化：XLSX 样式/打印设置导出保留。"""
from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Font, PatternFill

from beeoffice.plugins.beesheet import BeeSheetView


def make_workbook(path):
    wb = Workbook()
    ws = wb.active
    ws["A1"] = "名称"
    ws["B1"] = "数量"
    ws["A1"].font = Font(bold=True)
    ws["A1"].fill = PatternFill("solid", fgColor="FFE0B2")
    ws["A2"] = "甲"
    ws["B2"] = 1
    ws["A3"] = "乙"
    ws["B3"] = 2
    ws.print_area = "A1:B3"
    ws.freeze_panes = "A2"
    ws.conditional_formatting.add("B2:B3", CellIsRule(operator="greaterThan", formula=["0"], fill=PatternFill("solid", fgColor="E8F5E9")))
    wb.save(path)


def test_xlsx_preserves_styles_and_print_area(qtbot, tmp_path, monkeypatch):
    src = tmp_path / "src.xlsx"
    make_workbook(src)
    sheet = BeeSheetView()
    qtbot.addWidget(sheet)
    df = sheet._read_sheet_file(str(src))
    sheet._apply_imported_dataframe(df, str(src))
    out = tmp_path / "out.xlsx"
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out), "Excel (*.xlsx)")))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    sheet._export_xlsx()
    assert out.exists()
    wb = load_workbook(out)
    ws = wb.active
    assert ws.print_area.endswith("$A$1:$B$3")
    assert ws.freeze_panes == "A2"
    assert ws["A1"].font.bold is True
    assert ws["A1"].fill.fgColor.rgb.endswith("FFE0B2")
    assert len(list(ws.conditional_formatting)) >= 1
