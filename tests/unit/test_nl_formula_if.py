# tests/unit/test_nl_formula_if.py
"""
优化规划 §2.5 回归：自然语言 IF 指令的真值与假值不能相同。

原缺陷
------
`NLFormulaParser._extract_value(instruction, ["否则", "不然"], position="after")`
在指令里找不到「否则」时会**落到兜底分支**，而兜底是"返回全文第一个引号内容"。
于是假值又把真值取了回来：

    如果A1大于10就显示'高'
  -> =IF(A1>10,"高","高")

`nl_formula.py` 的 docstring 曾声称"本次更新修复 IF 公式中真假值都是同一个值
的问题"，但代码里该缺陷一直在（测试只断言 `"IF" in result` / `'"高"' in result`，
所以从未被发现）。

修复：只有当**没有指定关键词**时才使用"取第一个引号内容"这一兜底；
指定了关键词却没命中，说明该部分不存在，返回空串，由上层
`false_val or '"否"'` 提供默认假值。
"""
import pytest

from beeoffice.plugins.nl_formula import NLFormulaParser


def _quoted_values(formula: str):
    """取出公式里两个分支引号内的值。"""
    import re
    return re.findall(r'"([^"]*)"', formula)


# ==================== 只有真值：假值应回退到默认 ====================

def test_if_without_else_uses_default_false_value():
    result = NLFormulaParser.parse("如果A1大于10就显示'高'")
    assert result == '=IF(A1>10,"高","否")', result

    true_val, false_val = _quoted_values(result)
    assert true_val == "高"
    assert false_val == "否", "没有「否则」时假值应是默认值，而不是把真值抄一遍"
    assert true_val != false_val


def test_if_without_else_but_no_quotes():
    result = NLFormulaParser.parse("如果A1大于10就显示高")
    assert result is not None
    true_val, false_val = _quoted_values(result)
    assert true_val == "高"
    assert true_val != false_val


# ==================== 同时给出真假值 ====================

@pytest.mark.parametrize("text", [
    "如果A1大于10就显示'高'否则显示'低'",
    "如果A1大于10就显示'高'不然显示'低'",
    "如果A1大于10则返回'高'否则返回'低'",
])
def test_if_with_else_uses_both_values(text):
    result = NLFormulaParser.parse(text)
    assert result == '=IF(A1>10,"高","低")', result
    assert _quoted_values(result) == ["高", "低"]


def test_if_negative_condition():
    result = NLFormulaParser.parse("如果A1小于0则返回'负'否则返回'正'")
    assert result == '=IF(A1<0,"负","正")', result


# ==================== 各种比较运算符 ====================

@pytest.mark.parametrize("text,operator", [
    ("如果A1大于10就显示'大'否则显示'小'", ">"),
    ("如果A1小于10就显示'小'否则显示'大'", "<"),
    ("如果A1大于等于10就显示'大'否则显示'小'", ">="),
    ("如果A1小于等于10就显示'小'否则显示'大'", "<="),
    ("如果A1等于10就显示'等'否则显示'不等'", "="),
    ("如果A1不等于10就显示'不等'否则显示'等'", "<>"),
])
def test_all_comparison_operators(text, operator):
    result = NLFormulaParser.parse(text)
    assert result is not None, f"未能解析: {text}"
    assert f"A1{operator}10" in result, result
    true_val, false_val = _quoted_values(result)
    assert true_val != false_val, f"真假值不应相同: {result}"


# ==================== 无法解析时不应返回半成品 ====================

def test_non_if_instruction_is_not_parsed_as_if():
    """缺少「单元格 + 比较 + 数值」时不应当作 IF 处理。"""
    for text in ("求和A1到A10", "平均值B列"):
        result = NLFormulaParser.parse(text)
        assert result is None or not str(result).startswith("=IF"), result
