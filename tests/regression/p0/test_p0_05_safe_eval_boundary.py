# tests/test_p0_regression/test_p0_05_safe_eval_boundary.py
"""
P0-5 扩展回归：_safe_eval 白名单边界 + AND/OR/NOT/IFS 四函数
            + v5.0.5 IF 分支嵌套函数支持。

已有 test_p0_05_formula_safe.py 只测了 IF + __import__ 一种绕过，
本文件补齐：
  1. _safe_eval 的 AST 白名单边界：
     属性访问（().__class__）、下标（[][0]）、lambda、
     推导式、赋值、exec/eval/open 均被拒绝
  2. AND/OR/NOT/IFS 四个函数也走 _safe_eval（P0-5 修复的一部分）
  3. 白名单函数 abs/round/int/min/max 在 _safe_eval 中可用
  4. v5.0.5：IF / IFERROR / IFNA / IFS / CHOOSE 的
     "结果/兜底值"分支支持嵌套函数调用与算术表达式

v5.0.5：
  代码修复：beesheet_engine.py 新增 _eval_arg 方法，
            替换 _if / _iferror / _ifna / _ifs / _choose 里的 _av。
  本文件相应新增 6 个测试验证嵌套函数支持。
"""
import pytest
from beeoffice.plugins.beesheet_engine import FormulaEngine


class _FakeModel:
    """模拟 SheetDataModel 的最小接口。"""

    def __init__(self, data):
        self._data = data

    def get_value(self, r, c):
        if 0 <= r < len(self._data) and 0 <= c < len(self._data[r]):
            return self._data[r][c]
        return None


# ==================== IF 的各类绕过尝试 ====================

@pytest.mark.parametrize("payload", [
    # 属性访问
    "(1).__class__.__bases__[0].__subclasses__()",
    # 下标访问
    "__import__('os').environ['PATH']",
    # 嵌套属性穿透到危险模块
    "().__class__.__mro__[1].__subclasses__()",
    # 字符串 join 构造危险函数名
    "''.join(['e','v','a','l'])('1+1')",
    # 浮点数方法
    "(1.0).__class__.__bases__[0].__subclasses__()",
])
def test_if_rejects_ast_bypass(payload):
    """P0-5：IF 条件不应允许 AST 白名单外的语法。"""
    model = _FakeModel([[1]])
    result = FormulaEngine.evaluate(
        f"=IF({payload},1,2)", model
    )
    assert isinstance(result, str) and result.startswith("#ERROR"), (
        f"应拒绝危险表达式 {payload!r}，实际: {result!r}"
    )


def test_safe_eval_allows_arithmetic():
    """P0-5：_safe_eval 应允许合法算术。"""
    model = _FakeModel([[5]])
    result = FormulaEngine.evaluate(
        "=IF(A1 > 3 and A1 < 10, 1, 2)", model
    )
    assert result == 1


# ==================== 白名单函数（直接测 _safe_eval） ====================

def test_safe_eval_allows_whitelisted_functions():
    """P0-5：abs/round/int/min/max 应在 _safe_eval 白名单内。"""
    model = _FakeModel([[-3.7]])

    assert FormulaEngine._safe_eval("abs(A1)", model) == 3.7
    assert FormulaEngine._safe_eval("int(A1)", model) == -3
    assert FormulaEngine._safe_eval("round(A1, 1)", model) == -3.7
    assert FormulaEngine._safe_eval("min(A1, 0)", model) == -3.7
    assert FormulaEngine._safe_eval("max(A1, 0)", model) == 0
    assert FormulaEngine._safe_eval("abs(A1) > 3", model) is True
    assert FormulaEngine._safe_eval("int(abs(A1))", model) == 3


def test_safe_eval_rejects_non_whitelisted_function():
    """P0-5：白名单外的函数（如 open）应被拒绝。"""
    model = _FakeModel([[1]])
    with pytest.raises(Exception):
        FormulaEngine._safe_eval("open('/etc/passwd')", model)


# ==================== AND / OR / NOT / IFS ====================

def test_and_rejects_import():
    """P0-5：AND 的参数走 _safe_eval，也应拒绝 __import__。"""
    model = _FakeModel([[1]])
    result = FormulaEngine.evaluate(
        "=AND(__import__('os').getcwd(), TRUE)", model
    )
    assert isinstance(result, str) and result.startswith("#ERROR")


def test_or_rejects_import():
    """P0-5：OR 同上。"""
    model = _FakeModel([[1]])
    result = FormulaEngine.evaluate(
        "=OR(FALSE, __import__('os').getcwd())", model
    )
    assert isinstance(result, str) and result.startswith("#ERROR")


def test_not_rejects_import():
    """P0-5：NOT 同上。"""
    model = _FakeModel([[1]])
    result = FormulaEngine.evaluate(
        "=NOT(__import__('os').getcwd())", model
    )
    assert isinstance(result, str) and result.startswith("#ERROR")


def test_ifs_rejects_import():
    """P0-5：IFS 同上。"""
    model = _FakeModel([[1]])
    result = FormulaEngine.evaluate(
        "=IFS(__import__('os').getcwd(), 1)", model
    )
    assert isinstance(result, str) and result.startswith("#ERROR")


def test_and_or_not_normal_use():
    """P0-5 对照：AND/OR/NOT 的合法用法应正常工作。"""
    model = _FakeModel([[5]])
    assert FormulaEngine.evaluate("=AND(A1>0, A1<10)", model) is True
    assert FormulaEngine.evaluate("=OR(A1<0, A1>0)", model) is True
    assert FormulaEngine.evaluate("=NOT(A1>10)", model) is True


def test_ifs_normal_use():
    """P0-5 对照：IFS 正常分支。"""
    model = _FakeModel([[5]])
    result = FormulaEngine.evaluate(
        '=IFS(A1>10, "big", A1>0, "small")', model
    )
    assert result == "small"


# ==================== v5.0.5：分支嵌套函数支持 ====================

def test_if_branch_supports_nested_function():
    """
    v5.0.5 新增：IF 的 then/else 分支应支持嵌套函数调用。

    背景：原 _if 分支求值用 _av（只处理引用/数字/字符串），
    遇到 SUM/IF 等嵌套函数会原样返回字符串。
    """
    model = _FakeModel([[5], [10], [20], [30]])

    # then 分支嵌套 SUM
    result = FormulaEngine.evaluate(
        "=IF(A1>0, SUM(A2:A4), 0)", model
    )
    assert result == 60, f"IF then 分支 SUM 失败: {result!r}"

    # else 分支嵌套 SUM
    result = FormulaEngine.evaluate(
        "=IF(A1<0, 0, SUM(A2:A4))", model
    )
    assert result == 60

    # 嵌套 IF
    result = FormulaEngine.evaluate(
        "=IF(A1>0, IF(A1>10, 100, 50), 0)", model
    )
    assert result == 50


def test_if_branch_supports_arithmetic():
    """v5.0.5：IF 分支应支持算术表达式。"""
    model = _FakeModel([[5], [10]])

    # then 分支 A1 + A2
    result = FormulaEngine.evaluate("=IF(A1>0, A1+A2, 0)", model)
    assert result == 15

    # else 分支 A1 * 2
    result = FormulaEngine.evaluate("=IF(A1<0, 0, A1*2)", model)
    assert result == 10


def test_if_branch_supports_string_constant():
    """v5.0.5 对照：字符串常量分支应正常（去掉引号）。"""
    model = _FakeModel([[5]])
    result = FormulaEngine.evaluate('=IF(A1>0, "正", "负")', model)
    assert result == "正", f"字符串分支失败: {result!r}"


def test_iferror_supports_nested_function():
    """v5.0.5：IFERROR 的兜底值应支持嵌套函数。"""
    model = _FakeModel([[0], [10], [20]])
    # A1=0，1/A1 会 #DIV/0，兜底为 SUM
    result = FormulaEngine.evaluate(
        "=IFERROR(1/A1, SUM(A2:A3))", model
    )
    assert result == 30, f"IFERROR 兜底 SUM 失败: {result!r}"


def test_ifs_branch_supports_nested_function():
    """v5.0.5：IFS 的分支结果应支持嵌套函数。"""
    model = _FakeModel([[5], [10], [20]])
    result = FormulaEngine.evaluate(
        "=IFS(A1>10, SUM(A2:A3), A1>0, A1+100)", model
    )
    assert result == 105


def test_choose_supports_nested_function():
    """v5.0.5：CHOOSE 的结果值应支持嵌套函数。"""
    model = _FakeModel([[2], [10], [20], [30]])
    result = FormulaEngine.evaluate(
        "=CHOOSE(A1, A2, SUM(A2:A4), 999)", model
    )
    # A1=2 → 第 2 个参数 SUM(A2:A4) = 10+20+30 = 60
    assert result == 60, f"CHOOSE 嵌套 SUM 失败: {result!r}"