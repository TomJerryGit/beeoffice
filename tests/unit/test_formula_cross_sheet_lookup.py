# -*- coding: utf-8 -*-
"""
蜜算公式引擎：跨表查找（P1-15 收尾）

缺陷：
    `_eval_sheet_ref` 会把 `S1!A1:B3` 压平成 `1,一,2,二,...` 再交给函数，
    于是 VLOOKUP 的参数整体右移——列号参数拿到的是单元格内容，
    实际表现是 `int('一')` 直接抛错，跨表 VLOOKUP 一律 #ERROR。

修复：
    查找类函数（VLOOKUP/HLOOKUP）在跨表预处理**之前**拦截，
    保留原始区域参数，由 `_sheet_range` 按形状解析。
"""
import pytest

from beeoffice.plugins.beesheet_engine import FormulaEngine

pd = pytest.importorskip("pandas")


class _Model:
    """本表 A 列 = 5/10/20；S1 表有 A(键)、B(值) 两列。"""

    def __init__(self, sheets):
        self._sheets = sheets

    def get_value(self, r, c):
        data = [[5], [10], [20]]
        try:
            return data[r][c]
        except (IndexError, TypeError):
            return None

    def _get_sheet_data(self, name):
        return self._sheets.get(name)


@pytest.fixture
def model():
    return _Model({
        "S1": pd.DataFrame({"A": [1, 2, 3], "B": ["一", "二", "三"]}),
    })


@pytest.fixture
def no_sheet_model():
    return _Model({})


def test_vlookup_across_sheets(model):
    assert FormulaEngine.evaluate(
        "=VLOOKUP(2,S1!A1:B3,2,FALSE)", model
    ) == "二"


def test_vlookup_across_sheets_last_row(model):
    assert FormulaEngine.evaluate(
        "=VLOOKUP(3,S1!A1:B3,2,FALSE)", model
    ) == "三"


def test_vlookup_missing_key_returns_na(model):
    assert FormulaEngine.evaluate(
        "=VLOOKUP(99,S1!A1:B3,2,FALSE)", model
    ) == "#N/A"


def test_vlookup_unknown_sheet_is_error(no_sheet_model):
    assert FormulaEngine.evaluate(
        "=VLOOKUP(2,NOPE!A1:B3,2,FALSE)", no_sheet_model
    ) == "#ERROR"


def test_vlookup_same_sheet_still_works(model):
    """不跨表时行为不得改变（A1:A3 里没有 2，应为 #N/A）。"""
    assert FormulaEngine.evaluate(
        "=VLOOKUP(2,A1:A3,1,FALSE)", model
    ) == "#N/A"


def test_cross_sheet_sum_unaffected(model):
    """聚合函数仍然走压平路径，结果不变。"""
    assert float(FormulaEngine.evaluate("=SUM(S1!A1:A3)", model)) == 6
