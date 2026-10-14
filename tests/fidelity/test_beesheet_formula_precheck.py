# tests/fidelity/test_beesheet_formula_precheck.py
"""
P0-B：蜜算**公式扫描的字节级预检**（`_sheets_possibly_having_formulas`）。

问题（实测，5000×50 = 25 万格）
-------------------------------
`_read_formulas()` 用 openpyxl 逐格遍历找公式，要 **2634.9 ms**。
而绝大多数数值型表格**一个公式都没有**（基准文件实测 0 个）。

修法：先把每张表的 worksheet XML 当字节读进来找 `<f`，实测 **29.9 ms**
（约 90× 快）；找不到就整张表跳过，公式字典留空 —— 写回路径据此按普通值处理。
实测 `read_workbook` 合计 **6795.8 → 2721.7 ms**。

**为什么只判"有没有"、不解析公式内容**：真正的解析仍交给 openpyxl，
这样能完整保留**共享公式**（`t="shared"`，只有主格带文本、其余格靠 `si` 引用）
等复杂情形的既有正确性。自己解析 XML 就得上共享公式翻译，风险不值当。

**本文件的测试重点**（都是容易出错的点）：
  1. 映射必须**按关系（rels）**精确对应（表名 → 部件），
     不能假设"sheet1.xml 就是第一张表"；
  2. 预检失败时必须**退回全表扫描**（宁可慢，不能漏公式）；
  3. 有公式的表必须**仍然**读到公式（不能因为优化把公式弄丢）。
"""
import sys
from pathlib import Path

import openpyxl
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from beeoffice.plugins import beesheet_workbook as bw          # noqa: E402


def _make_workbook(path: Path, sheets):
    """
    sheets: [(表名, 二维值列表)]；值以 "=" 开头的会被 openpyxl 当公式写。
    """
    book = openpyxl.Workbook()
    book.remove(book.active)
    for name, rows in sheets:
        sheet = book.create_sheet(name)
        for r, row in enumerate(rows, start=1):
            for c, value in enumerate(row, start=1):
                sheet.cell(r, c, value=value)
    book.save(str(path))
    return path


# ==================== 1. 预检两个方向都要对 ====================

def test_precheck_detects_formula_sheet(tmp_path):
    path = _make_workbook(tmp_path / "f.xlsx", [
        ("有公式", [["a", "b"], [1, "=A2*2"]]),
    ])

    presence = bw._sheets_possibly_having_formulas(path)

    assert presence.get("有公式") is True


def test_precheck_reports_pure_values_sheet_as_false(tmp_path):
    path = _make_workbook(tmp_path / "v.xlsx", [
        ("纯数值", [["a", "b"], [1, 2], [3, 4]]),
    ])

    presence = bw._sheets_possibly_having_formulas(path)

    assert presence.get("纯数值") is False


def test_precheck_maps_by_relationship_not_by_order(tmp_path):
    """
    **关键**：表名 → 部件的映射必须走 rels。

    造一个"**第二张**表才有公式"的工作簿：若实现偷懒按 sheet1/sheet2 顺序对应，
    或把整簿当成一个布尔值，这里就会错。
    """
    path = _make_workbook(tmp_path / "two.xlsx", [
        ("第一张", [["a"], [1], [2]]),
        ("第二张", [["a"], ["=1+1"]]),
    ])

    presence = bw._sheets_possibly_having_formulas(path)

    assert presence.get("第一张") is False, presence
    assert presence.get("第二张") is True, presence


def test_precheck_returns_empty_dict_on_broken_file(tmp_path):
    """非 xlsx（或损坏）时应返回空 dict，让调用方退回全表扫描。"""
    broken = tmp_path / "broken.xlsx"
    broken.write_bytes(b"not a zip at all")

    assert bw._sheets_possibly_having_formulas(broken) == {}


# ==================== 2. 端到端：有公式的必须照旧读到 ====================

def test_read_workbook_still_reads_formulas(tmp_path):
    """优化不能把公式弄丢（表格 (R,C)[R>=2] → df (R-2,C-1)）。"""
    path = _make_workbook(tmp_path / "f.xlsx", [
        ("表", [["数量", "单价", "小计"], [3, 5, "=A2*B2"], [4, 6, "=A3*B3"]]),
    ])

    data = bw.read_workbook(str(path))

    formulas = data.sheets[0].formulas
    assert formulas == {(0, 2): "=A2*B2", (1, 2): "=A3*B3"}, formulas


def test_read_workbook_skips_scan_for_pure_values(tmp_path, monkeypatch):
    """
    纯数值表应**跳过逐格扫描**（这是性能收益所在）。

    注意：不能直接 monkeypatch `ReadOnlyWorksheet.iter_rows` 来计数 ——
    `pd.read_excel` 内部也走 openpyxl 的只读迭代，会把它的调用一起数进去
    （我第一版就是这么错的）。这里改成给 **`_read_formulas` 专用的
    `load_workbook`** 打桩：一旦它去取工作表就记下来。
    """
    path = _make_workbook(tmp_path / "v.xlsx", [
        ("纯数值", [["a", "b"], [1, 2], [3, 4], [5, 6]]),
    ])

    touched = {"sheet": False}

    class _FakeSheet:
        def iter_rows(self, *a, **kw):
            touched["sheet"] = True
            return iter(())

    class _FakeWorkbook:
        sheetnames = ["纯数值"]

        def __getitem__(self, name):
            return _FakeSheet()

        def close(self):
            pass

    monkeypatch.setattr(bw, "load_workbook", lambda *a, **kw: _FakeWorkbook())

    data = bw.read_workbook(str(path))

    assert data.sheets[0].formulas == {}
    assert touched["sheet"] is False, (
        "纯数值表仍去扫描了单元格 —— 预检没生效"
    )


def test_read_workbook_scans_when_precheck_fails(tmp_path, monkeypatch):
    """
    **安全性兜底**：预检失败时必须仍然扫描，公式不能丢。
    """
    path = _make_workbook(tmp_path / "f.xlsx", [
        ("表", [["a"], ["=1+1"]]),
    ])

    # 模拟预检失效（返回空 = "不知道"）
    monkeypatch.setattr(
        bw, "_sheets_possibly_having_formulas", lambda p: {}
    )

    data = bw.read_workbook(str(path))

    assert data.sheets[0].formulas == {(0, 0): "=1+1"}, (
        "预检失败时没有退回全表扫描，公式丢了"
    )


def test_multi_sheet_values_and_formulas_both_preserved(tmp_path):
    """多表：值来自 pandas、公式来自扫描，两者都要在。"""
    path = _make_workbook(tmp_path / "multi.xlsx", [
        ("甲", [["x"], [1], [2]]),
        ("乙", [["y"], ["=1+2"]]),
    ])

    data = bw.read_workbook(str(path))

    assert [s.name for s in data.sheets] == ["甲", "乙"]
    assert data.sheets[0].formulas == {}
    assert data.sheets[1].formulas == {(0, 0): "=1+2"}
    assert data.sheets[0].df.iloc[0, 0] == 1
