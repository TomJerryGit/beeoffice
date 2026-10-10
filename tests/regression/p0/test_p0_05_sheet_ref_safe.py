# tests/regression/p0/test_p0_05_sheet_ref_safe.py
"""
P0-5 扩展回归（优化规划 §1.1）：跨表引用路径不得执行任意 Python。

背景
----
已有的 test_p0_05_formula_safe.py / test_p0_05_safe_eval_boundary.py 只覆盖了
IF / AND / OR / NOT / IFS 所走的 _safe_eval 分支。

而 beesheet_engine._eval_sheet_ref()（凡公式含 "!" 都走这里）在把跨表引用
替换成字面值之后，对**剩余表达式**执行裸 eval()：

    return eval(new_expr, {"__builtins__": {}}, {})

清空 __builtins__ 并不构成沙箱——().__class__.__base__.__subclasses__()
在没有 builtins 的情况下仍然返回 200+ 个类，据此可以取回 __import__。
实测可直接执行任意 Python：

    =S!A1+[c for c in ().__class__.__base__.__subclasses__()
           if c.__name__=='catch_warnings'][0]()._module
           .__builtins__['__import__']('math').sqrt(16)
    -> 5.0            # 修复前

修复后该路径改走 _safe_eval（AST 白名单），本文件即为回归防线。
"""
import math

import pandas as pd
import pytest

from beeoffice.plugins.beesheet_engine import FormulaEngine


class _FakeModel:
    """
    最小模型：本表取值恒为 None；跨表数据固定 A1=7、B1=8。
    """

    def __init__(self):
        self._sheet = pd.DataFrame([[7, 8]])

    def _get_sheet_data(self, name):
        return self._sheet

    def get_value(self, r, c):
        return None


# ==================== 攻击载荷必须被拒绝 ====================

BYPASS_PAYLOADS = [
    # 推导式 + catch_warnings 取回 __import__：本次实测真正可利用的那条
    ("=S!A1+[c for c in ().__class__.__base__.__subclasses__() "
     "if c.__name__=='catch_warnings'][0]()._module."
     "__builtins__['__import__']('math').sqrt(16)"),
    # 属性穿透
    "=S!A1+().__class__.__base__.__subclasses__()",
    "=S!A1+(1).__class__.__mro__[1].__subclasses__()",
    # 下标访问
    "=S!A1+().__class__.__base__.__subclasses__()[0]",
    # 用字符串拼接构造危险函数名
    "=S!A1+''.join(['e','v','a','l'])('1+1')",
    # 直接调用 __import__
    "=S!A1+__import__('os').getcwd()",
]


@pytest.mark.parametrize("payload", BYPASS_PAYLOADS)
def test_sheet_ref_rejects_code_execution(payload):
    """
    含 "!" 的公式不得执行任何代码。

    修复前这些载荷会返回一个算出来的数值（例如 sqrt(16) 给出 5.0）；
    修复后安全求值失败，表达式被原样作为字符串返回，绝不会是数值结果。
    """
    result = FormulaEngine.evaluate(payload, _FakeModel())
    assert isinstance(result, str), (
        f"载荷被执行了——应被拒绝并返回原表达式字符串，实际得到 {result!r}"
    )


def test_sheet_ref_payload_has_no_side_effect():
    """
    用"只有执行成功才会产生的可观测值"再确认一次。

    sqrt(16)=4.0 若被执行，7+4.0 会得到 11.0；这里必须不是数值。
    """
    payload = (
        "=S!A1+[c for c in ().__class__.__base__.__subclasses__() "
        "if c.__name__=='catch_warnings'][0]()._module."
        "__builtins__['__import__']('math').sqrt(16)"
    )
    result = FormulaEngine.evaluate(payload, _FakeModel())
    assert result != 11.0
    assert not isinstance(result, (int, float))


# ==================== 安全加固不得破坏合法用法 ====================

@pytest.mark.parametrize("formula,expected", [
    ("=S!A1", 7),
    ("=S!A1+1", 8),
    ("=S!A1*2", 14),      # 修复前错误地返回 0
    ("=S!A1-3", 4),
    ("=S!A1/2", 3.5),
])
def test_sheet_ref_arithmetic_works(formula, expected):
    """合法的跨表算术必须正确求值。"""
    assert FormulaEngine.evaluate(formula, _FakeModel()) == expected


def test_sheet_ref_comparison_works():
    """修复前 =S!A1>0 返回 False。"""
    assert FormulaEngine.evaluate("=S!A1>0", _FakeModel()) is True


def test_sheet_ref_function_still_dispatches():
    """
    跨表引用出现在函数参数里时，仍要能走到白名单函数分派器
    （_safe_eval 不允许调用 SUM，因此依赖 _func 兜底分支）。
    """
    result = FormulaEngine.evaluate("=SUM(S!A1:B1)", _FakeModel())
    # 常量/多参数聚合尚未支持（优化规划 §2.5 第 4 项），
    # 但不得抛异常、不得执行代码
    assert result is not None
    assert not isinstance(result, str) or not result.startswith("#ERROR: 未知函数")


# ==================== 顺带修复：此前全废的数学函数 ====================

@pytest.mark.parametrize("formula,expected", [
    ("=ABS(-3)", 3.0),
    ("=SQRT(4)", 2.0),
    ("=LOG10(100)", 2.0),
    ("=SIN(0)", 0.0),
])
def test_math_functions_usable(formula, expected):
    """
    优化规划 §2.5：ABS/SQRT/PI/RAND 因 math_funcs 调用参数个数与 lambda
    签名不匹配而抛 "missing 1 required positional argument"，在 UI 函数
    参考表里存在却完全不可用。
    """
    assert FormulaEngine.evaluate(formula, _FakeModel()) == expected


def test_pi_usable():
    assert FormulaEngine.evaluate("=PI()", _FakeModel()) == math.pi


def test_rand_usable():
    value = FormulaEngine.evaluate("=RAND()", _FakeModel())
    assert isinstance(value, float)
    assert 0.0 <= value < 1.0
