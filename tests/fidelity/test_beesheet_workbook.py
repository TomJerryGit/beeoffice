# tests/fidelity/test_beesheet_workbook.py
"""
保真度阶段 A 第一刀：蜜算的「多工作表 + 公式」读写。

背景
----
蜜算原先是 `pd.read_excel(...)`（只读首张表）+ `df.to_excel(...)`，
实测 **9 项特征丢 8 项**：第二张工作表直接消失、公式全丢。
本模块把"工作簿"作为显式对象承载全部工作表与每格公式。

重点测什么
----------
1. **公式坐标换算**（最容易错的地方）：openpyxl 坐标 1 起、且第 1 行是表头，
   DataFrame 位置 0 起 —— 差一格的错位会让公式写到错误的单元格上。
2. **往返**：读进来再写出去，工作表数与公式数不变。
3. 边界：空表、无公式、工作表名需要净化、NaN 不能变成 "nan" 字符串。
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from beeoffice.plugins.beesheet_workbook import (   # noqa: E402
    SheetData,
    WorkbookData,
    read_workbook,
    sync_active_sheet,
    write_workbook,
)


def _make_xlsx(path: Path, sheets: dict = None) -> Path:
    """用 openpyxl 直接构造工作簿（含公式），作为测试输入。"""
    from openpyxl import Workbook

    wb = Workbook()
    wb.remove(wb.active)
    sheets = sheets or {
        "明细": [
            ["产品", "数量", "单价", "金额"],
            ["甲", 10, 12.5, "=B2*C2"],
            ["乙", 80, 3.2, "=B3*C3"],
        ],
        "汇总": [
            ["项目", "值"],
            ["合计", "=SUM(明细!D2:D3)"],
        ],
    }
    for name, rows in sheets.items():
        ws = wb.create_sheet(title=name)
        for r, row in enumerate(rows, start=1):
            for c, value in enumerate(row, start=1):
                ws.cell(row=r, column=c, value=value)
    wb.save(str(path))
    return path


# ==================== 1. 公式坐标换算 ====================

def test_formula_coordinates_are_df_based(tmp_path):
    """
    核心：工作表 (R,C) → df (R-2, C-1)。

    "明细" 表：
      工作表 D2 = "=B2*C2"  →  df (0, 3)
      工作表 D3 = "=B3*C3"  →  df (1, 3)
    """
    src = _make_xlsx(tmp_path / "in.xlsx")

    wb = read_workbook(src)

    detail = wb.get("明细")
    assert detail is not None
    assert detail.formulas == {(0, 3): "=B2*C2", (1, 3): "=B3*C3"}, (
        f"公式坐标换算错误: {detail.formulas}"
    )


def test_header_row_is_not_treated_as_data(tmp_path):
    """第 1 行是表头，不应产生 df 行号 -1 的公式。"""
    src = _make_xlsx(tmp_path / "in.xlsx", {
        "表": [["A", "B"], ["=A2", 2]],
    })

    formulas = read_workbook(src).get("表").formulas

    assert all(r >= 0 for r, _ in formulas), f"出现负行号: {formulas}"
    assert (0, 0) in formulas, formulas


# ==================== 2. 读：多工作表 + 公式 ====================

def test_reads_all_sheets(tmp_path):
    """修复「第二张工作表消失」。"""
    src = _make_xlsx(tmp_path / "in.xlsx")

    wb = read_workbook(src)

    assert wb.sheet_names == ["明细", "汇总"], wb.sheet_names
    assert wb.formula_count == 3
    assert len(wb.get("汇总").df) == 1


def test_first_sheet_is_active(tmp_path):
    src = _make_xlsx(tmp_path / "in.xlsx")
    assert read_workbook(src).active == "明细"


def test_sheet_without_formulas(tmp_path):
    src = _make_xlsx(tmp_path / "in.xlsx", {"纯数据": [["A"], [1], [2]]})
    wb = read_workbook(src)
    assert wb.get("纯数据").formulas == {}
    assert len(wb.get("纯数据").df) == 2


def test_empty_sheet_does_not_crash(tmp_path):
    src = _make_xlsx(tmp_path / "in.xlsx", {"空": [], "有": [["A"], [1]]})
    wb = read_workbook(src)
    assert "空" in wb.sheet_names
    assert wb.get("空").formulas == {}


# ==================== 3. 写：全部工作表 + 公式 ====================

def test_write_preserves_all_sheets_and_formulas(tmp_path):
    """往返：表数与公式数都不变。"""
    src = _make_xlsx(tmp_path / "in.xlsx")
    wb = read_workbook(src)

    out = tmp_path / "out.xlsx"
    write_workbook(wb, out)

    again = read_workbook(out)
    assert again.sheet_names == ["明细", "汇总"], again.sheet_names
    assert again.formula_count == 3, again.formula_count
    assert again.get("明细").formulas == wb.get("明细").formulas


def test_written_formulas_are_real_formulas(tmp_path):
    """写出去的必须是**公式字符串**，不是 pandas 算出来的值。"""
    src = _make_xlsx(tmp_path / "in.xlsx")
    write_workbook(read_workbook(src), tmp_path / "out.xlsx")

    from openpyxl import load_workbook

    ws = load_workbook(tmp_path / "out.xlsx")["明细"]
    assert ws["D2"].value == "=B2*C2", (
        f"D2 应是公式，实际 {ws['D2'].value!r}"
    )


def test_values_are_preserved(tmp_path):
    src = _make_xlsx(tmp_path / "in.xlsx")
    out = tmp_path / "out.xlsx"
    write_workbook(read_workbook(src), out)

    df = pd.read_excel(out, sheet_name="明细", engine="openpyxl")
    assert list(df.columns) == ["产品", "数量", "单价", "金额"]
    assert df.loc[0, "产品"] == "甲"
    assert df.loc[1, "数量"] == 80


def test_no_extra_default_sheet(tmp_path):
    """不应多出一张空白的 "Sheet"。"""
    src = _make_xlsx(tmp_path / "in.xlsx")
    out = tmp_path / "out.xlsx"
    write_workbook(read_workbook(src), out)

    from openpyxl import load_workbook

    assert load_workbook(out).sheetnames == ["明细", "汇总"]


def test_nan_is_written_as_empty_not_string(tmp_path):
    """空单元格必须留空，不能写成长度 4 的 "nan" 字符串。"""
    src = _make_xlsx(tmp_path / "in.xlsx", {
        "表": [["A", "B"], [1, None], [None, 2]],
    })
    out = tmp_path / "out.xlsx"
    write_workbook(read_workbook(src), out)

    import openpyxl

    ws = openpyxl.load_workbook(out)["表"]
    assert ws["B2"].value is None, f"应是 None，实际 {ws['B2'].value!r}"
    assert ws["A3"].value is None, f"应是 None，实际 {ws['A3'].value!r}"


def test_long_sheet_name_is_trimmed(tmp_path):
    """Excel 工作表名 ≤31 字符。"""
    long_name = "很长的表名" * 10
    wb = WorkbookData(sheets=[
        SheetData(name=long_name, df=pd.DataFrame({"A": [1]}))
    ])
    out = tmp_path / "out.xlsx"
    write_workbook(wb, out)

    import openpyxl

    names = openpyxl.load_workbook(out).sheetnames
    assert len(names[0]) <= 31, names


def test_illegal_characters_in_sheet_name(tmp_path):
    wb = WorkbookData(sheets=[
        SheetData(name="a/b:c", df=pd.DataFrame({"A": [1]}))
    ])
    out = tmp_path / "out.xlsx"
    write_workbook(wb, out)

    import openpyxl

    assert "/" not in openpyxl.load_workbook(out).sheetnames[0]


# ==================== 4. sync_active_sheet：编辑后写回 ====================

def test_sync_active_sheet_updates_values_keeps_formulas(tmp_path):
    """用户在蜜算里改了单元格内容，导出时必须保存改动，同时公式不能丢。"""
    src = _make_xlsx(tmp_path / "in.xlsx")
    wb = read_workbook(src)

    edited = wb.get("明细").df.copy()
    edited.loc[0, "产品"] = "甲（已改）"
    sync_active_sheet(wb, "明细", edited)

    out = tmp_path / "out.xlsx"
    write_workbook(wb, out)
    again = read_workbook(out)

    assert again.get("明细").df.loc[0, "产品"] == "甲（已改）"
    assert again.get("明细").formulas == {(0, 3): "=B2*C2", (1, 3): "=B3*C3"}, (
        "改内容不应丢公式"
    )


def test_sync_active_sheet_adds_new_sheet():
    wb = WorkbookData(sheets=[SheetData(name="a", df=pd.DataFrame({"A": [1]}))])
    sync_active_sheet(wb, "b", pd.DataFrame({"B": [2]}))
    assert wb.sheet_names == ["a", "b"]


# ==================== 5. 已知约束：首行被当作表头 ====================

def test_headerless_sheet_loses_its_first_row(tmp_path):
    """
    **已知约束（特性化）**：pandas 固定把工作表第 1 行当表头。

    因此"没有表头行"的表，首行会变成列名、并从数据里消失；
    若首行恰好是公式，该公式也会随之丢失（实测：4 → 3）。

    这不是本模块引入的问题，而是蜜算一直使用的 pandas 约定。这里把它**显式
    钉住**，避免将来"公式怎么会少一个"这种问题又变成难查的谜题。
    若要支持无表头的表，需要导入时让用户选择，或改用 openpyxl 逐格读。

    附带发现（同样钉住）：**公式单元格的值读出来是 NaN** —— 因为 openpyxl
    写出的 xlsx 不含"缓存计算值"，而 pandas 读的正是缓存值。真实 Excel 保存的
    文件里有缓存值，因此这条只影响"由程序生成的文件"。公式字符串本身由本模块
    从 `data_only=False` 那一遍取回，不受影响。
    """
    src = _make_xlsx(tmp_path / "in.xlsx", {
        "无表头": [["合计", "=SUM(A1:A1)"], [1, 2]],
    })

    wb = read_workbook(src)
    sheet = wb.get("无表头")

    # 第 1 行成了列名；公式格没有缓存值 → pandas 起了 "Unnamed: 1"
    assert list(sheet.df.columns) == ["合计", "Unnamed: 1"], (
        f"实际列名 {list(sheet.df.columns)}；若约定改了请更新本测试"
    )
    # 于是它不再是"数据里的公式"
    assert sheet.formulas == {}, (
        "首行的公式被当作表头；若此处变为非空，说明约定改了，请更新本测试"
    )


def test_formula_value_is_nan_without_cached_result(tmp_path):
    """公式格的**值**在无缓存时读为 NaN，但**公式字符串**必须取回。"""
    src = _make_xlsx(tmp_path / "in.xlsx", {
        "表": [["A", "B"], [1, 2], [3, "=A3*2"]],
    })

    sheet = read_workbook(src).get("表")

    assert pd.isna(sheet.df.loc[1, "B"]), (
        "openpyxl 写的文件没有缓存值，pandas 应读到 NaN"
    )
    assert sheet.formulas == {(1, 1): "=A3*2"}, "但公式字符串必须保留下来"


# ==================== 6. 与保真度探针联动 ====================

def test_workbook_roundtrip_keeps_probe_features(tmp_path):
    """
    用**探针**验证：sheets 与 formulas 两项特征在往返后不再归零。

    这是 docs/fidelity.md 里 `sheets 2→1`、`formulas 4→0` 两条的直接对照。
    """
    from tools.fidelity_roundtrip import build_xlsx_fixture
    from tools.ooxml_probe import compare, probe

    src = tmp_path / "fixture.xlsx"
    build_xlsx_fixture(src)
    before = probe(src)

    out = tmp_path / "roundtrip.xlsx"
    write_workbook(read_workbook(src), out)
    after = probe(out)

    rows = {r["feature"]: r for r in compare(before, after)}
    assert rows["sheets"]["status"] == "same", rows["sheets"]
    assert rows["sheets"]["after"] == before["features"]["sheets"]
    assert rows["formulas"]["after"] == before["features"]["formulas"], (
        f"公式仍丢失: {rows['formulas']}"
    )
