# tests/regression/v5/test_v505_formula_refs_and_ranges.py
"""
优化规划 §2.5 回归：绝对引用与反向范围。

原缺陷
------
`beesheet_engine._ref()` 的正则为 `^([A-Z]+)(\\d+)$`，**不接受 `$`**，
于是 `=SUM($A$1:$A$3)` 无法识别引用 → 静默返回 **0**（而不是报错）。
用户看到的是一个看起来正常的错误数字。而 `_safe_eval` 与跨表引用路径都
各自处理了 `$`，唯独 `_ref` 这条主路径没有。

`_range()` 也不归一化端点顺序，而所有调用方都按 `range(r1, r2 + 1)` 遍历，
因此 `=SUM(A3:A1)`（Excel 允许的反向写法）会得到空区间 → 同样静默返回 0。

修复：`_ref` 接受 `$A$1 / $A1 / A$1`；`_range` 归一化为左上/右下。
"""
import pytest

from beeoffice.plugins.beesheet_engine import FormulaEngine


class _Model:
    """A1=1 A2=2 A3=3 / B1=10 B2=20 B3=30"""

    DATA = {
        (0, 0): 1, (1, 0): 2, (2, 0): 3,
        (0, 1): 10, (1, 1): 20, (2, 1): 30,
    }

    def get_value(self, r, c):
        return self.DATA.get((r, c))


@pytest.mark.parametrize("formula,expected", [
    # 绝对引用（原实现静默返回 0）
    ("=SUM($A$1:$A$3)", 6),
    ("=$A$1+1", 2),
    ("=$A$1*$B$1", 10),
    ("=SUM($A1:A$3)", 6),          # 混合绝对
    # 相对引用（回归：不能因为改动而坏掉）
    ("=SUM(A1:A3)", 6),
    ("=A1+B1", 11),
    # 反向范围（Excel 允许 A3:A1）
    ("=SUM(A3:A1)", 6),
    ("=SUM(B3:B1)", 60),
    # 矩形区域
    ("=SUM(A1:B3)", 66),
])
def test_absolute_and_reverse_ranges(formula, expected):
    assert FormulaEngine.evaluate(formula, _Model()) == expected


def test_absolute_ref_is_not_treated_as_zero():
    """专门守住这个缺陷：不能"看起来算出来了，其实是 0"。"""
    got = FormulaEngine.evaluate("=SUM($A$1:$A$3)", _Model())
    assert got != 0, "绝对引用被当成无效引用而静默返回 0"
    assert got == 6


@pytest.mark.parametrize("formula", [
    "=COUNT($A$1:$A$3)",
    "=AVERAGE($A$1:$A$3)",
    "=MAX($A$1:$A$3)",
    "=MIN($A$1:$A$3)",
])
def test_absolute_refs_work_across_aggregates(formula):
    """不只 SUM：聚合函数都应支持绝对引用。"""
    got = FormulaEngine.evaluate(formula, _Model())
    assert got != 0, f"{formula} 疑似未识别绝对引用 -> {got!r}"


def test_ref_parser_accepts_dollar_forms():
    """直接测解析层，便于定位回归。"""
    assert FormulaEngine._ref("A1") == (0, 0)
    assert FormulaEngine._ref("$A$1") == (0, 0)
    assert FormulaEngine._ref("$A1") == (0, 0)
    assert FormulaEngine._ref("A$1") == (0, 0)
    assert FormulaEngine._ref("B3") == (2, 1)
    assert FormulaEngine._ref("!!") is None


def test_range_is_normalised():
    """_range 应返回左上/右下，与端点书写顺序无关。"""
    assert FormulaEngine._range("A3:A1") == FormulaEngine._range("A1:A3")
    assert FormulaEngine._range("B1:A3") == ((0, 0), (2, 1))
    assert FormulaEngine._range("$A$1:$A$3") == ((0, 0), (2, 0))
