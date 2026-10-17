# -*- coding: utf-8 -*-
"""
蜜算导入：IO 与 UI 分离的回归测试（P0-线程）

背景：
    原 `_import_file_from_path` 把"读文件"和"改模型 + 弹 QMessageBox"
    揉在一起，而 `app.py` 又把它丢进 `AsyncTaskManager`，
    于是在 worker 线程里 `setModel` / 弹模态框——Qt 明确禁止。

本文件锁定拆分后的契约：
    1. `_read_sheet_file` 纯读取，不得修改模型（可跑在后台线程）
    2. `_apply_imported_dataframe` 在 GUI 线程应用数据
    3. 导入新文件时清空上一个文件的公式缓存（P0-7）

至于 5 万行的真实大文件，单独放在 `slow` 用例里：
    实测 `pd.read_excel` 读该文件约 **64 秒**，且 `nrows=200` 仍需 **28 秒**
    （openpyxl 的固定开销与行数无关）。所以常规用例用现场生成的小文件，
    避免整套测试被一个 IO 特性拖慢。
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BIG_SAMPLE = ROOT / "test+files" / "销售数据_50000条.xlsx"


@pytest.fixture
def small_xlsx(tmp_path):
    """现场生成一个小 xlsx（5 行 × 3 列），避免依赖大样例。"""
    from openpyxl import Workbook

    path = tmp_path / "small.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["姓名", "数量", "金额"])
    for i in range(5):
        ws.append([f"客户{i}", i + 1, (i + 1) * 100])
    wb.save(path)
    return path


@pytest.fixture
def sheet_view(qtbot):
    from beeoffice.plugins.beesheet import BeeSheetView

    view = BeeSheetView()
    qtbot.addWidget(view)
    return view


def test_read_sheet_file_does_not_touch_model(sheet_view, small_xlsx):
    """读取阶段跑在后台线程，绝不能改模型。"""
    before_rows = sheet_view.model.rowCount()
    before_cols = sheet_view.model.columnCount()

    df = sheet_view._read_sheet_file(str(small_xlsx))

    assert len(df) == 5
    assert sheet_view.model.rowCount() == before_rows, (
        "读取阶段不应修改模型行数"
    )
    assert sheet_view.model.columnCount() == before_cols


def test_apply_imported_dataframe_updates_model(sheet_view, small_xlsx):
    """应用阶段在 GUI 线程，模型应真正被替换。"""
    df = sheet_view._read_sheet_file(str(small_xlsx))

    assert sheet_view._apply_imported_dataframe(df, str(small_xlsx)) is True
    assert sheet_view.model.rowCount() >= len(df)
    assert sheet_view.model.get_value(0, 0) == "客户0"


def test_formula_cells_cleared_on_new_import(sheet_view, small_xlsx):
    """导入新文件必须清空上一个文件的公式缓存（P0-7）。"""
    sheet_view._formula_cells["=A1+1"] = (0, 0)

    df = sheet_view._read_sheet_file(str(small_xlsx))
    sheet_view._apply_imported_dataframe(df, str(small_xlsx))

    assert sheet_view._formula_cells == {}


@pytest.mark.slow
@pytest.mark.timeout(300)
@pytest.mark.skipif(not BIG_SAMPLE.exists(), reason="缺少 50000 行样例文件")
def test_full_large_file_read(sheet_view):
    """
    完整读取 50000 行（实测约 64 秒）。

    这条用例既验证大文件路径可用，也是性能基线：
    耗时显著变长说明导入链路退化。
    """
    df = sheet_view._read_sheet_file(str(BIG_SAMPLE))

    assert len(df) == 50000, f"应读到 50000 行，实际 {len(df)}"
    assert sheet_view._apply_imported_dataframe(df, str(BIG_SAMPLE)) is True
    assert sheet_view.model.rowCount() >= 50000
