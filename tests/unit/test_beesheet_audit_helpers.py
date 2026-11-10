"""BeeSheet 审计辅助函数补测。"""
from beeoffice.plugins.beesheet_audit_mixin import AuditMixin


def make_audit():
    return AuditMixin()


def test_translate_formula_to_chinese():
    a = make_audit()
    text = a._translate_formula_to_chinese("=SUM(A1:A3)")
    assert "求和" in text and "A1:A3" in text
    assert "算术表达式" in a._translate_formula_to_chinese("=1+2")
    assert a._translate_formula_to_chinese("plain") == "plain"


def test_diagnose_error_branches():
    a = make_audit()
    assert "除零错误" in a._diagnose_error("=A1/B1", "#DIV/0!")
    assert "未找到匹配值" in a._diagnose_error("=VLOOKUP(x)", "#N/A")
    assert "函数名拼写错误" in a._diagnose_error("=FOO(1)", "未知函数")
    assert "括号不匹配" in a._diagnose_error("=SUM(1", "unknown error")
    assert "详细错误信息" in a._diagnose_error("=A1", "unknown error")


def test_formula_compatibility():
    a = make_audit()
    assert a._check_formula_compatibility("") == {"level": "ok"}
    assert a._check_formula_compatibility("=XLOOKUP(a,b,c)")["level"] == "warning"
    assert a._check_formula_compatibility("=A1||A2")["level"] == "error"
    assert a._check_formula_compatibility("=SUM(A1:A3)")["level"] == "ok"
