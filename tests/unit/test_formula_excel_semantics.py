# -*- coding: utf-8 -*-
"""
蜜算公式引擎：Excel 语义回归（P0）

为什么单独一个文件：
    原有测试几乎只用 `>` / `<`，没有一条 `=IF(A1=1,…)`。
    于是"引擎不支持 Excel 的 `=` 比较符"这个缺陷长期没有被发现，
    直到按 Excel 的真实写法做冒烟才暴露。

本文件锁定三类行为：
    1. 运算符：`=` / `<>` / `^`（Excel 写法，不是 Python 写法）
    2. 复合表达式：函数调用之后继续运算
    3. 跨表引用 + 安全回归：属性链不得被求值

对应缺陷编号：报告 P0-1、P0-6，P1-13、P1-15。
"""
import pytest

from beeoffice.plugins.beesheet_engine import FormulaEngine


class _Model:
    """最小模型：A1=5, A2=10, A3=20。"""

    def __init__(self, rows, sheets=None):
        self._rows = rows
        self._sheets = sheets or {}

    def get_value(self, r, c):
        try:
            return self._rows[r][c]
        except IndexError:
            return None

    def _get_sheet_data(self, name):
        return self._sheets.get(name)


@pytest.fixture
def model():
    return _Model([[5], [10], [20]])


@pytest.fixture
def sheet_model():
    """带跨表数据的模型：S1 = [1,2,3]，S2 = [100]。"""
    pd = pytest.importorskip("pandas")
    return _Model(
        [[5], [10], [20]],
        {
            "S1": pd.DataFrame({"A": [1, 2, 3]}),
            "S2": pd.DataFrame({"A": [100]}),
        },
    )


# ==================== 运算符 ====================

@pytest.mark.parametrize("formula,expected", [
    ("=A1+A2", 15),
    ("=2^3", 8),
    ("=IF(A1>3,1,2)", 1),
    # Excel 写法的相等 / 不等，历史上前者恒为 #ERROR
    ("=IF(A1=5,1,2)", 1),
    ("=IF(A1<>5,1,2)", 2),
    ("=IF(A1=5,\"yes\",\"no\")", "yes"),
    # 与 Python 写法并存，不能因为归一化而回归
    ("=IF(A1==5,1,2)", 1),
    ("=IF(A1!=5,1,2)", 2),
    ("=IF(A1>=10,1,0)", 0),
    ("=IF(A1<=5,1,0)", 1),
])
def test_operators(model, formula, expected):
    assert FormulaEngine.evaluate(formula, model) == expected


# ==================== 复合表达式 ====================

@pytest.mark.parametrize("formula,expected", [
    ("=SUM(A1:A3)", 35),
    ("=SUM(A1:A3)*2", 70),
    ("=SUM(A1:A3)/2", 17.5),
    ("=ROUND(3.14159,2)", 3.14),
    ("=SUM(1,2,3)", 6),          # 标量参数
    ("=SUM(A1)", 5),             # 单格（原实现返回 0）
    ("=IF(A1=5,SUM(A2:A3),0)", 30),
])
def test_compound_expressions(model, formula, expected):
    actual = FormulaEngine.evaluate(formula, model)
    if isinstance(expected, float):
        assert float(actual) == pytest.approx(expected)
    else:
        assert actual == expected


def test_len_of_quoted_string(model):
    """LEN 应按 Excel 语义去掉引号后计数。"""
    assert FormulaEngine.evaluate('=LEN("abc")', model) == 3


# ==================== 跨表引用 ====================

def test_cross_sheet_range_sum(sheet_model):
    """=SUM(S1!A1:A3) 应得 6（历史返回 0）。"""
    assert float(FormulaEngine.evaluate("=SUM(S1!A1:A3)", sheet_model)) == 6


def test_cross_sheet_cell_plus_local(sheet_model):
    assert FormulaEngine.evaluate("=S2!A1+A1", sheet_model) == 105


def test_cross_sheet_range_plus_cell(sheet_model):
    assert float(
        FormulaEngine.evaluate("=SUM(S1!A1:A3)+S2!A1", sheet_model)
    ) == 106


# ==================== 安全 ====================

def test_attribute_chain_is_not_evaluated(sheet_model):
    """
    安全回归（P0-6）：
        旧实现把替换后的表达式直接交给 eval，`(1).real` 这类属性访问
        会被执行；配合 `().__class__.__bases__[0].__subclasses__()`
        即可逃逸沙箱执行任意代码。
        修复后必须走 AST 白名单，不得返回数值结果。
    """
    result = FormulaEngine.evaluate("=S2!A1+(1).real", sheet_model)
    assert not isinstance(result, (int, float)), (
        f"属性访问不应被求值，实际返回 {result!r}"
    )


def test_unknown_function_is_rejected(sheet_model):
    """白名单外的函数不应被调用。"""
    result = FormulaEngine.evaluate("=S2!A1+__import__('os')", sheet_model)
    assert not isinstance(result, (int, float))
