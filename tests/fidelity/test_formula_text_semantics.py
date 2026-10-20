# tests/fidelity/test_formula_text_semantics.py
"""
v5.0.17：`TEXT` / `TEXTJOIN` 的 Excel 兼容语义（审计遗留项 §3.3）。

## 修的是什么
1. `TEXT(value, format_text)` 之前**完全忽略格式**，直接 `str(value)`：
   `=TEXT(1234.5,"0.00")` 返回 `"1234.5"`，与 Excel 的 `"1234.50"` 不符。
2. `TEXTJOIN(delimiter, ignore_empty, text1, ...)` 之前把第 1 个参数当分隔符、
   其余全部 join：没有 `ignore_empty`、**不展开区域**、不处理数字/布尔格式。
   `=TEXTJOIN(",",TRUE,A1:A3)` 会把 `"TRUE"` 和 `"A1:A3"` 拼进去。

## 口径
这里是**常用子集**：数字（0/#/./,/%%/E±/字面量/正;负;零段）与日期时间
（y/m/d/h/s、AM/PM、中文年月日）；不支持的复杂格式返回 `#ERROR` 而不是静默给错值。
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
    ["a", None, "b"],
    [1, 2, 3],
    [True, False, "x"],
    [None, "", "  "],
]


def _ev(expr):
    return FormulaEngine.evaluate(expr, _FakeModel(DATA))


# ==================== 1. TEXT 数值格式 ====================

class TestTextNumberFormats:
    def test_fixed_decimals(self):
        assert _ev('=TEXT(1234.567,"0.00")') == "1234.57"
        assert _ev('=TEXT(0.5,"0.00")') == "0.50"
        assert _ev('=TEXT(0,"0.00")') == "0.00"

    def test_thousands_separator(self):
        assert _ev('=TEXT(1234.567,"#,##0.00")') == "1,234.57"
        assert _ev('=TEXT(1234567,"#,##0")') == "1,234,567"

    def test_percent(self):
        assert _ev('=TEXT(0.25,"0%")') == "25%"
        assert _ev('=TEXT(0.2567,"0.0%")') == "25.7%"

    def test_round_half_up_like_excel(self):
        # Excel 的 TEXT/ROUND 是半进位：2.5 → 3，而不是 Python 的银行家舍入
        assert _ev('=TEXT(1234.5,"0")') == "1235"
        assert _ev('=TEXT(2.5,"0")') == "3"

    def test_leading_zero_placeholder(self):
        assert _ev('=TEXT(1,"0000")') == "0001"

    def test_optional_hash_leading_zero(self):
        assert _ev('=TEXT(0.5,"#.##")') == ".5"

    def test_negative_default_prefix(self):
        assert _ev('=TEXT(-1234.567,"#,##0.00")') == "-1,234.57"

    def test_negative_section(self):
        assert _ev('=TEXT(-1234.567,"0.00;(0.00)")') == "(1234.57)"

    def test_literal_prefix_suffix(self):
        assert _ev('=TEXT(1234.567,"¥#,##0.00")') == "¥1,234.57"
        assert _ev('=TEXT(1234.567,"0.00元")') == "1234.57元"

    def test_scientific(self):
        assert _ev('=TEXT(1.2345,"0.00E+00")') == "1.23E+00"
        assert _ev('=TEXT(0.000123,"0.00E+00")') == "1.23E-04"

    def test_cell_reference_and_general(self):
        assert _ev('=TEXT(A2,"0.00")') == "1.00"
        assert _ev('=TEXT(A2,"General")') == "1"


# ==================== 2. TEXT 日期/时间 ====================

class TestTextDateFormats:
    def test_serial_one(self):
        assert _ev('=TEXT(1,"yyyy-mm-dd")') == "1900-01-01"

    def test_excel_1900_fake_leap_day(self):
        # Excel 的 1900 闰年 bug：序列号 60 显示为 1900-02-29（Excel 里不存在）
        assert _ev('=TEXT(60,"yyyy-mm-dd")') == "1900-02-29"

    def test_serial_61(self):
        assert _ev('=TEXT(61,"yyyy-mm-dd")') == "1900-03-01"

    def test_common_date(self):
        assert _ev('=TEXT(45000,"yyyy-mm-dd")') == "2023-03-15"
        assert _ev('=TEXT(45000,"yyyy/mm/dd")') == "2023/03/15"

    def test_chinese_date_literals(self):
        assert _ev('=TEXT(45000,"yyyy年m月d日")') == "2023年3月15日"

    def test_time_and_datetime(self):
        assert _ev('=TEXT(0.5,"hh:mm:ss")') == "12:00:00"
        assert (
            _ev('=TEXT(45000.5,"yyyy-mm-dd hh:mm:ss")')
            == "2023-03-15 12:00:00"
        )

    def test_am_pm(self):
        assert _ev('=TEXT(0.5,"h:mm AM/PM")') == "12:00 PM"
        assert _ev('=TEXT(0.25,"h:mm AM/PM")') == "6:00 AM"


# ==================== 3. TEXT 对文本值 ====================

class TestTextTextValues:
    def test_text_passthrough(self):
        assert _ev('=TEXT("abc","0.00")') == "abc"

    def test_at_placeholder(self):
        assert _ev('=TEXT("abc","@")') == "abc"
        assert _ev('=TEXT(A1,"@")') == "a"


# ==================== 4. TEXTJOIN Excel 语义 ====================

class TestTextjoinExcelSemantics:
    def test_ignore_empty_true(self):
        assert _ev('=TEXTJOIN("-",TRUE,"a","","b")') == "a-b"

    def test_ignore_empty_false(self):
        assert _ev('=TEXTJOIN("-",FALSE,"a","","b")') == "a--b"

    def test_range_expansion(self):
        assert _ev('=TEXTJOIN(",",TRUE,A1:C1)') == "a,b"
        assert _ev('=TEXTJOIN(",",FALSE,A1:C1)') == "a,,b"

    def test_multiple_ranges(self):
        assert _ev('=TEXTJOIN(",",TRUE,A1:C1,A2:C2)') == "a,b,1,2,3"

    def test_empty_delimiter(self):
        assert _ev('=TEXTJOIN("",TRUE,A1:C2)') == "ab123"

    def test_number_and_boolean_formatting(self):
        assert _ev('=TEXTJOIN(",",TRUE,1,2.5,TRUE)') == "1,2.5,TRUE"

    def test_whitespace_is_not_empty(self):
        # Excel：空格串不是空值；只有 ""/空单元格才被 ignore_empty 跳过
        assert _ev('=TEXTJOIN(",",TRUE,"x"," ","y")') == "x, ,y"

    def test_ignore_empty_numeric_flag(self):
        assert _ev('=TEXTJOIN(",",1,"a","","b")') == "a,b"

    def test_too_few_args(self):
        assert _ev('=TEXTJOIN(",",TRUE)') == "#ERROR"

    def test_nested_text_as_delimiter(self):
        assert _ev('=TEXTJOIN(TEXT(1,"0"),TRUE,"a","b")') == "a1b"
