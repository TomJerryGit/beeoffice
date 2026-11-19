"""复杂 Excel 样本：公式/条件格式/数据验证/图表/打印区域/多工作表。"""
from pathlib import Path
import pandas as pd
from openpyxl import load_workbook
from beeoffice.plugins.beesheet_xlsx_export import export_xlsx_preserving_styles, read_xlsx_formulas


def test_complex_sample_roundtrip(tmp_path):
    src = Path(__file__).resolve().parents[1] / "corpus" / "complex" / "复杂销售分析-2026-11-19.xlsx"
    assert src.is_file()
    df = pd.read_excel(src)
    out = tmp_path / "out.xlsx"
    assert export_xlsx_preserving_styles(str(src), df, str(out), read_xlsx_formulas(str(src)))
    wb = load_workbook(out, data_only=False)
    assert len(wb.sheetnames) >= 3
    ws = wb["销售明细"]
    assert ws["F2"].value == "=D2*E2"
    assert ws.freeze_panes == "A2"
    assert "$A$1:$G$6" in str(ws.print_area)
    assert len(list(ws.conditional_formatting)) >= 1
    ws2 = wb["月度汇总"]
    assert len(ws2._charts) == 1
    assert len(list(ws2.conditional_formatting)) >= 1
