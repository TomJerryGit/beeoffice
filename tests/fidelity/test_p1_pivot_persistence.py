# tests/fidelity/test_p1_pivot_persistence.py
"""
第七批：数据透视表**落盘（可刷新）**。

## 修前
`_show_pivot_table` 只把**结果值**塞进一个新标签页，`config`（行/列/值/聚合/小计）
**当场丢弃** → 关掉标签页就重算不了；存成文件后只剩一堆死数字，
既看不出怎么汇总的，也没法刷新。

## 为什么**没有**写 Excel 原生透视表（先试过，如实记录）
我先试了 `openpyxl.pivot`（`TableDefinition` + `CacheDefinition`），
两次分别被拒：

    TypeError: TableDefinition.dataCaption should be <class 'str'> ...
    TypeError: PivotField.items ... expected <class 'FieldItem'>

它的 pivot 对象图又深又缺文档，而**半填的 pivot 会让 Excel 弹"修复文件"**
—— 那比"没有原生透视表"糟得多（产出坏文件是本项目最不能接受的）。
所以本批做的是**规格 + 可刷新**：
* 隐藏表 `beeoffice_pivot`：版本标记、透视表所在工作表、字段配置 JSON、来源表名；
* 隐藏表 `beeoffice_pivot_data`：**数据快照**（即使来源文件不在了也自洽可重算）；
* 「刷新透视表」：按"当前表格 → 文件内快照"取数据，重算并写回透视表工作表。

## 顺带修掉一个继承来的真 bug
`build_pivot` 原先只对 `MultiIndex` 调 `reset_index()` →
**只有一个行字段时**（最常见！）`reset_index(drop=True)` 会把行标签**整个丢掉**：
修前列是 `['销量_1月','销量_2月']`（产品 A/B 没了），修后是
`['产品','销量_1月','销量_2月']`。落盘端到端测试把它暴露了出来。

## 另一个我自己的 bug
刷新时只把单元格值置 None 就 `append` → `append` 会写到原区域**之后**
（透视表第一行空着、数据跑到下面去了）。现在改成**删行**再写。
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA = pd.DataFrame({
    "产品": ["A", "A", "B", "B"],
    "月份": ["1月", "2月", "1月", "2月"],
    "销量": [10, 20, 5, 8],
})
SPEC = {"rows": ["产品"], "cols": ["月份"], "values": ["销量"],
        "aggfunc": "sum", "margins": False}


def _load(path):
    from openpyxl import load_workbook

    workbook = load_workbook(path)
    return workbook, workbook[workbook.sheetnames[0]]


def _make_pivot_file(tmp_path, name="透视.xlsx"):
    """造一个"应用生成透视标签页并保存"的文件。"""
    from beeoffice.plugins.beesheet_pivot import (
        build_pivot, write_pivot_package,
    )

    pivot, error = build_pivot(DATA, SPEC)
    assert error is None
    path = tmp_path / name
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pivot.to_excel(writer, index=False, sheet_name="透视")
    write_pivot_package(path, pivot_sheet="透视", spec=SPEC, source_df=DATA)
    return path, pivot


# ==================== 1. 计算语义（含继承 bug 的回归）====================

def test_single_row_field_keeps_labels():
    """
    **回归**：只有一个行字段时行标签必须保留。

    修前 `reset_index(drop=True)` 把索引直接丢掉 → 透视表只有数字、没有"是谁"。
    """
    from beeoffice.plugins.beesheet_pivot import build_pivot

    pivot, error = build_pivot(DATA, SPEC)

    assert error is None
    assert "产品" in list(pivot.columns), f"行标签丢了：{list(pivot.columns)}"
    assert pivot["产品"].tolist() == ["A", "B"]
    assert pivot.iloc[0]["销量_1月"] == 10


def test_multiple_row_fields_and_column_only():
    from beeoffice.plugins.beesheet_pivot import build_pivot

    multi, error = build_pivot(
        DATA, {"rows": ["产品", "月份"], "cols": [], "values": ["销量"],
               "aggfunc": "sum", "margins": False}
    )
    assert error is None
    assert list(multi.columns)[:2] == ["产品", "月份"]

    col_only, error = build_pivot(
        DATA, {"rows": [], "cols": ["月份"], "values": ["销量"],
               "aggfunc": "sum", "margins": False}
    )
    assert error is None
    assert len(col_only) == 1


def test_pivot_requires_fields():
    from beeoffice.plugins.beesheet_pivot import build_pivot

    pivot, error = build_pivot(DATA, {"rows": [], "cols": [], "values": ["销量"]})
    assert pivot is None and error

    pivot, error = build_pivot(DATA, {"rows": ["产品"], "cols": [], "values": []})
    assert pivot is None and error


# ==================== 2. 落盘：隐藏表 + 读回 ====================

def test_package_is_written_to_hidden_sheets(tmp_path):
    from beeoffice.plugins.beesheet_pivot import (
        META_SHEET, SNAPSHOT_SHEET,
    )

    path, _ = _make_pivot_file(tmp_path)
    workbook, _ = _load(path)

    assert META_SHEET in workbook.sheetnames
    assert SNAPSHOT_SHEET in workbook.sheetnames
    assert workbook[META_SHEET].sheet_state == "hidden"
    assert workbook[SNAPSHOT_SHEET].sheet_state == "hidden"


def test_package_roundtrip(tmp_path):
    from beeoffice.plugins.beesheet_pivot import read_pivot_package

    path, _ = _make_pivot_file(tmp_path)
    package = read_pivot_package(path)

    assert package is not None
    assert package["spec"] == SPEC
    assert package["pivot_sheet"] == "透视"
    assert package["snapshot"] is not None
    # 快照要与当初汇总的数据一致（否则刷新会算错）
    assert list(package["snapshot"].columns) == ["产品", "月份", "销量"]
    assert len(package["snapshot"]) == 4


def test_read_returns_none_for_foreign_file(tmp_path):
    """不是本应用写的文件 → 返回 None，**不猜**。"""
    from beeoffice.plugins.beesheet_pivot import read_pivot_package

    path = tmp_path / "普通.xlsx"
    DATA.to_excel(path, index=False)

    assert read_pivot_package(path) is None


def test_rewriting_package_does_not_duplicate(tmp_path):
    from beeoffice.plugins.beesheet_pivot import (
        META_SHEET, SNAPSHOT_SHEET, read_pivot_package, write_pivot_package,
    )

    path, _ = _make_pivot_file(tmp_path)
    write_pivot_package(path, pivot_sheet="透视", spec=SPEC, source_df=DATA)

    workbook, _ = _load(path)
    # 元数据表只有两行内容（标记 + pivot_sheet + spec 用 A1..B3）
    assert workbook[META_SHEET].max_row <= 3
    snapshot = read_pivot_package(path)["snapshot"]
    assert len(snapshot) == 4, "快照被重复写入（行数变多了）"


# ==================== 3. 刷新 ====================

def test_refresh_recomputes_and_rewrites_sheet(tmp_path):
    """刷新要按新数据重算，且**表头在第 1 行、数据从第 2 行开始**。"""
    from beeoffice.plugins.beesheet_pivot import refresh_pivot_package

    path, _ = _make_pivot_file(tmp_path)
    changed = DATA.copy()
    changed["销量"] = [100, 200, 50, 80]

    ok, message, pivot = refresh_pivot_package(path, data_df=changed)

    assert ok, message
    assert "当前表格" in message
    assert pivot is not None and pivot.iloc[0]["销量_1月"] == 100

    _, ws = _load(path)
    assert [c.value for c in ws[1]][0] == "产品", "表头不在第 1 行"
    assert [c.value for c in ws[2]][:2] == ["A", 100], "数据不在第 2 行开始"


def test_refresh_falls_back_to_snapshot(tmp_path):
    """没给数据时用文件内快照，并在文案里**说清用的是哪一份**。"""
    from beeoffice.plugins.beesheet_pivot import refresh_pivot_package

    path, _ = _make_pivot_file(tmp_path)

    ok, message, pivot = refresh_pivot_package(path, data_df=None)

    assert ok, message
    assert "快照" in message
    assert pivot is not None


def test_refresh_without_package_reports_clearly(tmp_path):
    from beeoffice.plugins.beesheet_pivot import refresh_pivot_package

    path = tmp_path / "没有规格.xlsx"
    DATA.to_excel(path, index=False)

    ok, message, pivot = refresh_pivot_package(path, data_df=DATA)

    assert ok is False
    assert "没有保存过透视表" in message
    assert pivot is None


def test_refresh_keeps_data_correct_after_shrink(tmp_path):
    """刷新后数据变少时，**旧行不能残留**（先删行再写的回归）。"""
    from beeoffice.plugins.beesheet_pivot import refresh_pivot_package

    path, _ = _make_pivot_file(tmp_path)
    smaller = DATA[DATA["产品"] == "A"].copy()      # 只剩 A

    ok, _, _ = refresh_pivot_package(path, data_df=smaller)
    assert ok

    _, ws = _load(path)
    assert ws.max_row == 2, f"旧行残留了：max_row={ws.max_row}"


# ==================== 4. 视图接线 ====================

@pytest.fixture
def sheet_view(qtbot):
    from PySide6.QtWidgets import QMessageBox

    from beeoffice.plugins.beesheet import BeeSheetView

    view = BeeSheetView()
    qtbot.addWidget(view)
    view._set_status = lambda *a, **k: None
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    return view


def test_view_saves_pivot_spec(qtbot, tmp_path):
    """视图保存时要把规格写进文件，导入时读回来。"""
    from beeoffice.plugins.beesheet import BeeSheetView
    from beeoffice.plugins.beesheet_pivot import build_pivot, read_pivot_package

    pivot, _ = build_pivot(DATA, SPEC)
    target = tmp_path / "视图透视.xlsx"

    writer = BeeSheetView()
    qtbot.addWidget(writer)
    writer._set_status = lambda *a, **k: None
    try:
        writer.model.set_full_dataframe(pivot)
        writer._pivot_spec = {"spec": SPEC, "source_sheet": "数据",
                              "source_path": None}
        writer._pivot_source_df = DATA
        writer.set_current_file_path(target)
        assert writer.save() is True
    finally:
        writer.close()

    package = read_pivot_package(target)
    assert package and package["spec"] == SPEC

    reader = BeeSheetView()
    qtbot.addWidget(reader)
    reader._set_status = lambda *a, **k: None
    try:
        reader._import_file_from_path(str(target))
        assert reader._pivot_spec, "导入后没有读回透视表规格"
    finally:
        reader.close()


def test_refresh_pivot_prompts_without_file(sheet_view, monkeypatch):
    """没保存过文件的表格：要提示先保存，而不是静默无事发生。"""
    from PySide6.QtWidgets import QMessageBox
    from beeoffice.plugins.beesheet_pivot import build_pivot

    shown = []
    monkeypatch.setattr(
        QMessageBox, "information",
        staticmethod(lambda parent, title, text, *a, **k: shown.append(text)),
    )
    pivot, _ = build_pivot(DATA, SPEC)
    sheet_view.model.set_full_dataframe(pivot)
    sheet_view._current_file_path = None

    sheet_view._refresh_pivot()

    assert shown and "保存" in shown[0]


def test_refresh_pivot_updates_view_and_file(sheet_view, tmp_path):
    from beeoffice.plugins.beesheet_pivot import build_pivot

    pivot, _ = build_pivot(DATA, SPEC)
    target = tmp_path / "刷新视图.xlsx"
    sheet_view.model.set_full_dataframe(pivot)
    sheet_view._pivot_spec = {"spec": SPEC, "source_sheet": "透视",
                              "source_path": None}
    sheet_view._pivot_source_df = DATA
    sheet_view.set_current_file_path(target)
    sheet_view.save()

    # 用户改了数据再刷新
    changed = DATA.copy()
    changed["销量"] = [1, 2, 3, 4]
    sheet_view.model.set_full_dataframe(changed)
    sheet_view._refresh_pivot()

    assert sheet_view.model.df.iloc[0]["销量_1月"] == 1

    _, ws = _load(target)
    assert [c.value for c in ws[2]][1] == 1, "文件里的透视表没有更新"


def test_menu_has_refresh_pivot_action():
    """菜单里要有入口（否则功能等于没有）。"""
    import inspect

    from beeoffice import menus

    source = inspect.getsource(menus)
    assert "刷新透视表" in source
    assert "_refresh_pivot" in source
