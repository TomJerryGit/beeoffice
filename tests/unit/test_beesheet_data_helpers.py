"""结构化补测：BeeSheet DataMixin 纯逻辑。"""
import pandas as pd

from beeoffice.plugins.beesheet_data_mixin import DataMixin


def test_trim_empty_tail_removes_trailing_blank_rows():
    df = pd.DataFrame({"a": ["1", "", ""], "b": ["x", None, ""]})
    out = DataMixin._trim_empty_tail(df)
    assert len(out) == 1
    assert out.iloc[0]["a"] == "1"


def test_trim_empty_tail_empty_and_none():
    assert DataMixin._trim_empty_tail(None) is None
    out = DataMixin._trim_empty_tail(pd.DataFrame(columns=["a", "b"]))
    assert out.empty


def test_parse_csv_quoted_and_blank_lines():
    dm = DataMixin()
    data = dm._parse_csv('a,b\n"x,1",2\n\n c , d ', ",")
    assert data[0] == ["a", "b"]
    assert data[1] == ["x,1", "2"]
    assert data[2] == ["c", "d"]


def test_is_pattern_source_variants():
    dm = DataMixin()
    assert dm._is_pattern_source("", "x") is False
    assert dm._is_pattern_source("abc", "") is False
    assert dm._is_pattern_source("hello world", "world")
    assert dm._is_pattern_source("a12b", "12")
    assert dm._is_pattern_source("姓名", "姓名：张三")
    assert dm._is_pattern_source("MiXeD", "mixed")
    assert not dm._is_pattern_source("abc", "zzz")


def test_learn_and_apply_patterns():
    dm = DataMixin()
    assert dm._learn_pattern("abc", "abc") == ("copy", None)
    assert dm._learn_pattern("abc", "ABC") == ("upper", None)
    assert dm._learn_pattern("ABC", "abc") == ("lower", None)
    assert dm._learn_pattern("abcdef", "abc") == ("prefix", 3)
    assert dm._learn_pattern("abcdef", "def") == ("suffix", 3)
    assert dm._learn_pattern("a12b", "12") == ("extract_number", None)
    assert dm._learn_pattern("城市-北京", "北京") == ("suffix", 2)
    assert dm._learn_pattern("a-b-c", "b") == ("split", ("-", 1))
    pattern = ("split", ("-", 1))
    assert dm._apply_pattern(pattern, "城市-上海") == "上海"
    assert dm._apply_pattern(("upper", None), "abc") == "ABC"
    assert dm._apply_pattern(("extract_number", None), "a1b2") == "12"
    assert dm._apply_pattern(("copy", None), "x") == "x"
