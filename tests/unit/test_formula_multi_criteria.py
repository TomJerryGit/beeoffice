# -*- coding: utf-8 -*-
"""
蜜算公式引擎：多条件函数语义（P1-14）

缺陷：
    COUNTIFS 把每对 (范围, 条件) **独立计数后相加**，
    等价于把 COUNTIFS 当成了 SUM(COUNTIF...)，结果系统性偏大。
    SUMIFS / AVERAGEIFS 结构正确，但条件区只取首列（cr[0][1] 恒定），
    多列条件范围时除首列外的条件全部失效。

正确语义（Excel）：
    所有条件范围与求和/计数范围**同形**，
    按相同偏移逐格比对，只有全部条件在同一点成立才计入。
"""
import pytest

from beeoffice.plugins.beesheet_engine import FormulaEngine


class _Model:
    def __init__(self, rows):
        self._rows = rows

    def get_value(self, r, c):
        try:
            return self._rows[r][c]
        except (IndexError, TypeError):
            return None


@pytest.fixture
def model():
    """A=数字, B=标签, C=金额。"""
    return _Model([
        [1, "x", 10],
        [2, "x", 20],
        [3, "y", 30],
    ])


def _ev(expr, model):
    return FormulaEngine.evaluate(expr, model)


def test_countifs_requires_all_conditions_on_same_row(model):
    """COUNTIFS(A>1, B='x') 只有第 2 行同时成立。"""
    assert _ev('=COUNTIFS(A1:A3,">1",B1:B3,"x")', model) == 1


def test_countifs_single_condition_still_works(model):
    assert _ev('=COUNTIFS(A1:A3,">1")', model) == 2


def test_sumifs_matches_same_row_only(model):
    """金额 20 属于 (2,'x') 那一行。"""
    assert _ev('=SUMIFS(C1:C3,A1:A3,">1",B1:B3,"x")', model) == 20


def test_sumifs_no_match_is_zero(model):
    assert _ev('=SUMIFS(C1:C3,A1:A3,">100")', model) == 0


def test_averageifs_matches_same_row_only(model):
    assert _ev('=AVERAGEIFS(C1:C3,A1:A3,">1",B1:B3,"x")', model) == 20


def test_sumifs_two_dimensional_ranges():
    """二维求和范围 + 二维条件范围：按偏移逐格比对，不能只取首列。"""
    # A/B 是求和范围，C/D 是条件范围
    m = _Model([
        [1, 2, 10, 20],
        [3, 4, 30, 40],
    ])
    # C2=30>25 -> A2=3 ; D2=40>25 -> B2=4 ; 合计 7
    assert _ev('=SUMIFS(A1:B2,C1:D2,">25")', m) == 7


def test_countifs_two_dimensional_ranges():
    m = _Model([
        [1, 2],
        [3, 4],
    ])
    # 只有 (1,1)=4 大于 3
    assert _ev('=COUNTIFS(A1:B2,">3")', m) == 1
