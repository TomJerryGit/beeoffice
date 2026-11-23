"""动态数组导出：只写顶部公式，不写过期溢出值。"""
import pandas as pd
from openpyxl import load_workbook
from beeoffice.plugins.beesheet_xlsx_export import export_new_xlsx


def test_spill_values_not_written(tmp_path):
    df = pd.DataFrame([[1, 2], [3, 4]])
    out = tmp_path / "spill.xlsx"
    formulas = {(0, 0): "=SEQUENCE(2,2)"}
    spill = {(0, 1), (1, 0), (1, 1)}
    assert export_new_xlsx(df, str(out), formulas, spill)
    wb = load_workbook(out, data_only=False)
    ws = wb.active
    assert ws["A2"].value == "=SEQUENCE(2,2)"
    assert ws["B2"].value is None
    assert ws["A3"].value is None
    assert ws["B3"].value is None


def test_data_validations_export(tmp_path):
    import pandas as pd
    from openpyxl import load_workbook
    from beeoffice.plugins.beesheet_xlsx_export import export_new_xlsx
    out = tmp_path / "dv.xlsx"
    df = pd.DataFrame({"A": ["北京", 5]})
    validations = [
        {"row": 0, "col": 0, "type": "list", "options": ["北京", "上海"]},
        {"row": 1, "col": 0, "type": "range", "min": 0, "max": 10},
    ]
    assert export_new_xlsx(df, str(out), None, None, validations)
    wb = load_workbook(out)
    dvs = wb.active.data_validations.dataValidation
    assert len(dvs) == 2
    assert any("北京" in (dv.formula1 or "") for dv in dvs)
