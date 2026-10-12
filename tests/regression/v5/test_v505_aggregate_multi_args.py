# tests/regression/v5/test_v505_aggregate_multi_args.py
"""
优化规划 §2.5 回归：聚合函数支持逗号分隔的多参数。

原缺陷
------
`SUM` / `AVERAGE` / `MAX` / `MIN` / `COUNT` 都只走 `_vals(a, m)`，而 `_vals()`
内部只调用 `_range()` —— 只认 `A1:A3` 这种**冒号范围**。于是 Excel 里同样合法
的"逗号分隔参数"一律**静默返回 0**：

    =SUM(1,2,3)        -> 0     （应为 6）
    =SUM(A1,A2,A3)     -> 0     （应为 6）
    =AVERAGE(1,2,3)    -> 0     （应为 2）
    =MAX(1,5,3)        -> 0     （应为 5）

用户看到的是"算出来了，但是 0"，而不是报错——比抛异常更难发现。

修复：新增 `_numbers()`，用既有的 `_args()` 做顶层逗号切分，逐段识别
「范围 / 单元格 / 数值常量」，聚合函数改用它。
"""
import pytest

from beeoffice.plugins.beesheet_engine import FormulaEngine


class _Model:
    """A1=1 A2=2 A3=3 A4=文本 / B1=10 / C1=空"""

    DATA = {(0, 0): 1, (1, 0): 2, (2, 0): 3, (3, 0): "文本",
            (0, 1): 10, (0, 2): None}

    def get_value(self, r, c):
        return self.DATA.get((r, c))


@pytest.mark.parametrize("formula,expected", [
    # 数值常量（原先全部返回 0）
    ("=SUM(1,2,3)", 6),
    ("=SUM(1)", 1),
    ("=SUM(1.5,2.5)", 4),
    ("=SUM(-2,5)", 3),
    ("=AVERAGE(1,2,3)", 2),
    ("=MAX(1,5,3)", 5),
    ("=MIN(1,5,3)", 1),
    ("=COUNT(1,2,3)", 3),
    # 单元格引用（原先返回 0）
    ("=SUM(A1,A2,A3)", 6),
    ("=SUM(C1,0)", 0),
    # 混合：范围 + 单元格 + 常量
    ("=SUM(A1:A2,B1)", 13),
    ("=SUM(A1:A2,10)", 13),
    ("=SUM(A1:B1)", 11),
    # 回归：纯范围写法不能坏
    ("=SUM(A1:A3)", 6),
    ("=AVERAGE(A1:A3)", 2),
    ("=MAX(A1:A3)", 3),
    ("=MIN(A1:A3)", 1),
    ("=COUNT(A1:A3)", 3),
    # 空参数
    ("=SUM()", 0),
])
def test_aggregates_accept_comma_separated_args(formula, expected):
    assert FormulaEngine.evaluate(formula, _Model()) == expected


def test_sum_with_constants_is_not_silently_zero():
    """专门守住这个缺陷：不能"看起来算出来了、其实是 0"。"""
    got = FormulaEngine.evaluate("=SUM(1,2,3)", _Model())
    assert got != 0, "逗号分隔的常量参数被忽略，静默返回 0"
    assert got == 6


def test_non_numeric_arguments_are_ignored_not_crashing():
    """文本参数应被忽略（COUNT/SUM 语义），不应抛异常。"""
    assert FormulaEngine.evaluate("=SUM(A1,A4)", _Model()) == 1
    assert FormulaEngine.evaluate("=COUNT(A1,A4)", _Model()) == 1
    assert FormulaEngine.evaluate('=SUM("abc",1)', _Model()) == 1


def test_range_with_absolute_markers_in_args():
    """与 §2.5 的绝对引用修复配合：$ 写法同样可用。"""
    assert FormulaEngine.evaluate("=SUM($A$1,$A$2)", _Model()) == 3
    assert FormulaEngine.evaluate("=SUM($A$1:$A$3,1)", _Model()) == 7
