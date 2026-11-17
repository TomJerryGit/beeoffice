"""P0/P1：XLSX 公式往返。"""
from openpyxl import Workbook, load_workbook
from beeoffice.plugins.beesheet import BeeSheetView


def test_formula_preserved_on_export(qtbot, tmp_path, monkeypatch):
    src = tmp_path / "formula.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["A", "B", "合计"])
    ws.append([10, 20, "=A2+B2"])
    wb.save(src)

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
    ws2 = load_workbook(out, data_only=False).active
    assert ws2["C2"].value == "=A2+B2"
