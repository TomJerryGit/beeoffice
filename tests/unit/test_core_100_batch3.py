"""核心 100% 批次 3：旧版 formula_engine 私有分支。"""
import pytest

from beeoffice.plugins.formula_engine import FormulaEngine


def engine():
    data = [[1, 2], [3, 4]]
    def provider(r, c):
        if 0 <= r < len(data) and 0 <= c < len(data[r]):
            return data[r][c]
        return None
    return FormulaEngine(provider)


@pytest.mark.parametrize("call", [
    lambda e: e._eval_sum("SUM()"),
    lambda e: e._eval_average("AVERAGE()"),
    lambda e: e._eval_count("COUNT()"),
    lambda e: e._eval_counta("COUNTA()"),
    lambda e: e._eval_countif("COUNTIF()"),
    lambda e: e._eval_countif("COUNTIF(A1:A2)"),
    lambda e: e._eval_max("MAX()"),
    lambda e: e._eval_min("MIN()"),
    lambda e: e._eval_if("IF(1)", 0, 0),
    lambda e: e._eval_vlookup("VLOOKUP(1,A1:A2)", 0, 0),
    lambda e: e._eval_vlookup("VLOOKUP(1,bad,2)", 0, 0),
    lambda e: e._eval_round("ROUND(1)", 0, 0),
    lambda e: e._eval_mod("MOD(1)", 0, 0),
])
def test_formula_error_branches(call):
    with pytest.raises(ValueError):
        call(engine())


def test_formula_string_coercion_and_conditions():
    e = engine()
    assert e._eval_round('ROUND("1.234", 2)', 0, 0) == 1.23
    assert e._eval_abs('ABS("-2")', 0, 0) == 2
    assert e._eval_int('INT("2.9")', 0, 0) == 2
    assert e._eval_mod('MOD("5", "2")', 0, 0) == 1
    assert e._eval_if("IF(0,2)", 0, 1) is False
    # 数值比较所有运算符
    assert e._eval_condition("A1>=1", 0, 0)
    assert e._eval_condition("1<=2", 0, 0)
    assert e._eval_condition("1==1", 0, 0)
    assert e._eval_condition("1<>2", 0, 0)
    assert e._eval_condition("2>1", 0, 0)
    assert e._eval_condition("1<2", 0, 0)
    # 非数字字符串比较走 str 分支
    assert e._eval_condition("abc>1", 0, 0)
    assert e._eval_condition("TRUE", 0, 0) is True
    assert e._eval_condition("FALSE", 0, 0) is False
    assert e._eval_condition("", 0, 0) is False
    assert e._eval_condition("A1", 0, 0) is True


def test_formula_parse_value_and_ranges():
    e = engine()
    assert e._parse_value(5, 0, 0) == 5
    assert e._parse_value("", 0, 0) is None
    assert e._parse_value("A1:A2", 0, 0) == "A1:A2"
    assert e._parse_value("$A$1", 0, 0) == 1
    assert e._parse_value("1e2", 0, 0) == 100.0
    assert e._parse_value("'text'", 0, 0) == "text"
    assert e._get_cell_value_by_ref("bad") is None
    assert e._get_range_values("A1") == [1]
    assert e._get_range_values("bad") == []
    assert e._get_table_data("bad") == []


def test_formula_flatten_args():
    e = engine()
    vals = e._flatten_args_to_values(["", "A1", '"x"', "SUM(A1:A1)", "1.5"])
    assert 1 in vals and "x" in vals and 1.5 in vals
    with pytest.raises(ValueError):
        e._flatten_args_to_values(["abc"], need_number=True)


def test_formula_criteria_operators():
    e = engine()
    assert e._match_criteria(2, ">=2")
    assert e._match_criteria(2, "<=2")
    assert e._match_criteria(2, ">1")
    assert e._match_criteria(2, "<3")
    assert e._match_criteria(2, "=2")
    assert e._match_criteria(2, "!=3")
    assert e._match_criteria("abc", "abc")
    assert e._is_number("1") is True
    assert e._is_number("abc") is False
    assert e._is_number([]) is False


def test_formula_math_replace_errors():
    e = engine()
    assert e._eval_math("A9+1", 0, 0) == 1
    class Bad:
        def __call__(self, r, c):
            return "x"
    b = FormulaEngine(Bad())
    assert b._eval_math("A1+1", 0, 0) == 1
