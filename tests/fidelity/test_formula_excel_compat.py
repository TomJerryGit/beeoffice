# tests/fidelity/test_formula_excel_compat.py
"""
v5.0.12：公式引擎的 Excel 兼容语义（审计 §3.3 L2/L3）。

## 修的是什么
1. **单等号 / 不等号**：从 Excel 粘贴的 `=IF(A1=1,…)`、`=IF(A1<>2,…)`、
   `=AND(A1=1,B1=2)` 原先直接 `#ERROR`（`_safe_eval` 只认 Python 的 `==`/`!=`）。
2. **函数结果参与四则运算**：`=SUM(A1:A8)/2` 原先静默返回**公式文本**，
   `=SUM()+SUM()` 更静默返回 0 —— 用户完全看不出来算错了。

## 证据
这些用例直接跑 `FormulaEngine.evaluate`（纯逻辑，不依赖 Qt），
并与 `tests/unit/test_beesheet_engine_v51.py` 的既有 113 条用例并存。
"""

from beeoffice.plugins.beesheet_engine import FormulaEngine


class _FakeModel:
    """模拟 SheetDataModel 的最小接口。"""

    def __init__(self, data):
        self._data = data

    def get_value(self, r, c):
        if 0 <= r < len(self._data) and 0 <= c < len(self._data[r]):
            return self._data[r][c]
        return None


DATA = [
    [1, 10],
    [2, 20],
    [3, 30],
    [4, 40],
]


def _ev(expr):
    return FormulaEngine.evaluate(expr, _FakeModel(DATA))


# ==================== 1. Excel 条件运算符（单 = / <> / !=） ====================

class TestExcelConditionOperators:
    def test_if_single_equals(self):
        assert _ev('=IF(A1=1,"eq","ne")') == "eq"

    def test_if_python_double_equals_still_works(self):
        assert _ev('=IF(A1==1,"eq","ne")') == "eq"

    def test_if_not_equal_angle(self):
        assert _ev('=IF(A1<>2,"yes","no")') == "yes"

    def test_if_not_equal_bang(self):
        assert _ev('=IF(A1!=2,"yes","no")') == "yes"

    def test_if_greater_equal(self):
        assert _ev('=IF(A1>=1,"ge","lt")') == "ge"

    def test_if_less_equal_false_branch(self):
        assert _ev('=IF(A1<=0,"le","gt")') == "gt"

    def test_and_with_single_equals(self):
        assert _ev("=AND(A1=1,B1=10)") is True
        assert _ev("=AND(A1=2,B1=10)") is False

    def test_or_with_single_equals(self):
        assert _ev("=OR(A1=2,B1=10)") is True
        assert _ev("=OR(A1=2,B1=99)") is False

    def test_not_with_single_equals(self):
        assert _ev("=NOT(A1=2)") is True

    def test_ifs_with_single_equals(self):
        assert _ev('=IFS(A1=1,"one",A1=2,"two")') == "one"

    def test_top_level_comparison(self):
        assert _ev("=A1=1") is True
        assert _ev("=A1<>2") is True

    def test_comparison_of_function_result(self):
        assert _ev("=SUM(A1:A4)>9") is True


# ==================== 2. 函数结果参与四则运算 ====================

class TestFunctionResultsInArithmetic:
    def test_division(self):
        assert _ev("=SUM(A1:A4)/2") == 5.0

    def test_addition(self):
        assert _ev("=SUM(A1:A4)+1") == 11

    def test_multiplication(self):
        assert _ev("=AVERAGE(A1:A4)*2") == 5.0

    def test_two_functions(self):
        # 原先整串不匹配"函数调用"→ 返回公式文本；这条防静默错值
        assert _ev("=SUM(A1:A2)+SUM(B1:B2)") == 33

    def test_function_result_as_argument(self):
        assert _ev("=ROUND(SUM(A1:A4)/4,0)") == 3

    def test_if_branch_function_arithmetic(self):
        assert _ev("=IF(A1=1,SUM(B1:B4)/2,0)") == 50

    def test_min_max_in_expression(self):
        assert _ev("=MIN(A1:A4)+MAX(A1:A4)") == 5

    def test_plain_arithmetic_not_broken(self):
        assert _ev("=1+2*3") == 7
        assert _ev("=A1+B1*2") == 21


# ==================== 3. 字符串字面量不能被误处理 ====================

class TestStringLiterals:
    def test_quoted_cell_ref_is_string(self):
        assert _ev('="A1"') == "A1"

    def test_quoted_function_call_is_string(self):
        assert _ev('="SUM(A1:A4)"') == "SUM(A1:A4)"

    def test_string_equality(self):
        assert _ev('=IF("A1"="A1","same","diff")') == "same"


# ==================== 4. 错误不被吞成"公式文本" ====================

class TestErrorPropagation:
    def test_error_value_in_arithmetic(self):
        result = _ev("=VLOOKUP(99,A1:A4,B1:B4)+1")
        assert isinstance(result, str) and result.startswith("#ERROR"), result

    def test_unknown_function_in_arithmetic(self):
        result = _ev("=NOSUCHFUNC(A1)/2")
        assert isinstance(result, str) and result.startswith("#ERROR"), result

    def test_injection_still_blocked(self):
        """安全回归：新求值路径不得让 __import__ 执行。"""
        result = _ev("=IF(__import__('os').system('echo pwned'),1,2)")
        assert isinstance(result, str) and result.startswith("#ERROR"), result
        assert "pwned" not in result
