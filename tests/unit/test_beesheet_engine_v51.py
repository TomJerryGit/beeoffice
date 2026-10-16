# tests/unit/test_beesheet_engine_v51.py
"""
v5.1 B1：公式引擎新增函数单测

覆盖：
  - XLOOKUP 完整参数（if_not_found / match_mode / search_mode）
  - XMATCH
  - LET
  - SWITCH
  - XOR
  - MAXIFS / MINIFS
  - TEXTBEFORE / TEXTAFTER
  - VALUETOTEXT
  - ISBLANK / ISNUMBER / ISTEXT / ISLOGICAL / ISERROR

设计说明：
  - 引擎不支持 TRUE / FALSE 字面量（_safe_eval 的 AST 白名单里
    只有 Python 的 True / False，不含全大写形式），
    因此 XOR / ISLOGICAL 测试统一用比较表达式（A1>0）代替字面量。
    若要支持 TRUE / FALSE 字面量，需在 B3 阶段扩展 _safe_eval。
  - 所有测试用 _FakeModel 提供最小接口 get_value(r, c)。
"""

from beeoffice.plugins.beesheet_engine import FormulaEngine


# ==================== 测试辅助 ====================
class _FakeModel:
    """模拟 SheetDataModel 的最小接口。"""

    def __init__(self, data):
        self._data = data

    def get_value(self, r, c):
        if 0 <= r < len(self._data) and 0 <= c < len(self._data[r]):
            return self._data[r][c]
        return None


def _ev(expr, data):
    """便捷求值：expr 以 '=' 开头，data 为二维列表。"""
    return FormulaEngine.evaluate(expr, _FakeModel(data))


# ==================== XLOOKUP ====================
class TestXLookup:
    """XLOOKUP 6 参数版本。"""

    def test_basic(self):
        """基础精确查找。"""
        data = [["a", 1], ["b", 2], ["c", 3]]
        assert _ev('=XLOOKUP("b",A1:A3,B1:B3)', data) == 2

    def test_first_match(self):
        """匹配第一个元素。"""
        data = [["a", 1], ["b", 2]]
        assert _ev('=XLOOKUP("a",A1:A2,B1:B2)', data) == 1

    def test_last_match(self):
        """匹配最后一个元素。"""
        data = [["a", 1], ["b", 2]]
        assert _ev('=XLOOKUP("b",A1:A2,B1:B2)', data) == 2

    def test_not_found_default(self):
        """未找到时返回 if_not_found。"""
        data = [["a", 1], ["b", 2]]
        assert _ev('=XLOOKUP("x",A1:A2,B1:B2,"没找到")', data) == "没找到"

    def test_not_found_no_default(self):
        """未找到 + 无 if_not_found → #N/A。"""
        data = [["a", 1], ["b", 2]]
        assert _ev('=XLOOKUP("x",A1:A2,B1:B2)', data) == "#N/A"

    def test_not_found_numeric_default(self):
        """未找到 + 数字兜底值。"""
        data = [["a", 1]]
        assert _ev('=XLOOKUP("z",A1:A1,B1:B1,-1)', data) == -1

    def test_match_mode_wildcard(self):
        """match_mode=2 通配符匹配。"""
        data = [["apple", 10], ["banana", 20], ["cherry", 30]]
        # "a*" 匹配 apple
        assert _ev('=XLOOKUP("a*",A1:A3,B1:B3,"?",2)', data) == 10

    def test_match_mode_wildcard_question(self):
        """match_mode=2 问号通配符（单字符）。"""
        data = [["cat", 1], ["dog", 2], ["bat", 3]]
        # "?at" 匹配 cat（第一个）
        assert _ev('=XLOOKUP("?at",A1:A3,B1:B3,"?",2)', data) == 1

    def test_match_mode_next_larger(self):
        """match_mode=1 精确或下一个更大。"""
        data = [[10, "低"], [20, "中"], [30, "高"]]
        # 15 → 下一个更大 = 20 → "中"
        assert _ev("=XLOOKUP(15,A1:A3,B1:B3,0,1)", data) == "中"

    def test_match_mode_next_smaller(self):
        """match_mode=-1 精确或下一个更小。"""
        data = [[10, "低"], [20, "中"], [30, "高"]]
        # 25 → 下一个更小 = 20 → "中"
        assert _ev("=XLOOKUP(25,A1:A3,B1:B3,0,-1)", data) == "中"

    def test_search_mode_reverse(self):
        """search_mode=-1 从后往前搜索。"""
        data = [["x", 1], ["y", 2], ["x", 3]]
        # 从后往前找 x → 匹配第 3 行 → 返回 B3 = 3
        assert _ev('=XLOOKUP("x",A1:A3,B1:B3,0,0,-1)', data) == 3

    def test_search_mode_reverse_unique(self):
        """反向搜索 + 唯一匹配。"""
        data = [["a", 1], ["b", 2], ["c", 3]]
        # 反向搜 "b" → 只有一处 → 返回 2
        assert _ev('=XLOOKUP("b",A1:A3,B1:B3,0,0,-1)', data) == 2

    def test_return_array_horizontal(self):
        """return_array 是横向范围。"""
        data = [
            ["k1", 100, 200],
        ]
        # lookup_array 是 A1:A1，return_array 是 B1:C1
        assert _ev('=XLOOKUP("k1",A1:A1,B1:C1)', data) == 100

    def test_too_few_args(self):
        """参数不足时返回 #ERROR。"""
        assert _ev('=XLOOKUP("a")', [["a", 1]]) == "#ERROR"


# ==================== XMATCH ====================
class TestXMatch:
    """XMATCH 4 参数版本。"""

    def test_basic(self):
        data = [["a"], ["b"], ["c"]]
        assert _ev('=XMATCH("b",A1:A3)', data) == 2

    def test_first(self):
        data = [["a"], ["b"]]
        assert _ev('=XMATCH("a",A1:A2)', data) == 1

    def test_not_found(self):
        data = [["a"], ["b"]]
        assert _ev('=XMATCH("z",A1:A2)', data) == "#N/A"

    def test_reverse(self):
        """search_mode=-1 从后往前搜索。"""
        data = [["x"], ["y"], ["x"]]
        # 从后往前找 x → 位置 3
        assert _ev('=XMATCH("x",A1:A3,0,-1)', data) == 3

    def test_match_mode_wildcard(self):
        """match_mode=2 通配符匹配。"""
        data = [["apple"], ["banana"], ["cherry"]]
        assert _ev('=XMATCH("b*",A1:A3,2)', data) == 2

    def test_too_few_args(self):
        assert _ev("=XMATCH()", [["a"]]) == "#ERROR"


# ==================== LET ====================
class TestLet:
    """LET 变量绑定。"""

    def test_basic(self):
        data = [[5], [3]]
        # x=5, y=3, x+y=8
        assert _ev("=LET(x,A1,y,A2,x+y)", data) == 8

    def test_single_binding(self):
        data = [[10]]
        # x=10, x*2=20
        assert _ev("=LET(x,A1,x*2)", data) == 20

    def test_nested_reference(self):
        """后面的变量可以引用前面的。"""
        data = [[2]]
        # x=2, y=x*3=6, y+x=8
        assert _ev("=LET(x,A1,y,x*3,y+x)", data) == 8

    def test_with_string(self):
        """绑定字符串变量。"""
        data = [["hello"]]
        assert _ev("=LET(greeting,A1,greeting)", data) == "hello"

    def test_invalid_args(self):
        """参数不足 → #ERROR。"""
        assert _ev("=LET(x)", [[1]]) == "#ERROR"

    def test_even_args(self):
        """参数个数为偶数（缺少 calculation）→ #ERROR。"""
        assert _ev("=LET(x,A1)", [[1]]) == "#ERROR"


# ==================== SWITCH ====================
class TestSwitch:
    """SWITCH 多分支匹配。"""

    def test_match_first(self):
        data = [["A"]]
        assert _ev('=SWITCH(A1,"A",100,"B",200)', data) == 100

    def test_match_second(self):
        data = [["B"]]
        assert _ev('=SWITCH(A1,"A",100,"B",200)', data) == 200

    def test_match_third(self):
        data = [["C"]]
        assert _ev('=SWITCH(A1,"A",100,"B",200,"C",300)', data) == 300

    def test_default(self):
        """带 default。"""
        data = [["Z"]]
        assert _ev('=SWITCH(A1,"A",100,"B",200,999)', data) == 999

    def test_no_default_no_match(self):
        """无 default + 无匹配 → #N/A。"""
        data = [["Z"]]
        assert _ev('=SWITCH(A1,"A",100,"B",200)', data) == "#N/A"

    def test_numeric_expr(self):
        """表达式为数字。"""
        data = [[2]]
        assert _ev("=SWITCH(A1,1,\"一\",2,\"二\",3,\"三\")", data) == "二"

    def test_too_few_args(self):
        assert _ev('=SWITCH(A1,"A")', [["A"]]) == "#ERROR"


# ==================== XOR ====================
class TestXor:
    """
    异或逻辑。奇数个 TRUE → TRUE。
    注意：引擎不支持 TRUE / FALSE 字面量，测试用比较表达式。
    """

    def test_single_true(self):
        assert _ev("=XOR(A1>0)", [[1]]) is True

    def test_single_false(self):
        assert _ev("=XOR(A1<0)", [[1]]) is False

    def test_two_true(self):
        assert _ev("=XOR(A1>0, A1>0)", [[1]]) is False

    def test_three_true(self):
        assert _ev("=XOR(A1>0, A1>0, A1>0)", [[1]]) is True

    def test_all_false(self):
        assert _ev("=XOR(A1<0, A1<0, A1<0)", [[1]]) is False

    def test_mixed_with_cells(self):
        data = [[5], [10]]
        # A1>0=T, A2<5=F → XOR = T
        assert _ev("=XOR(A1>0, A2<5)", data) is True

    def test_mixed_three(self):
        data = [[5], [10]]
        # T, T, F → XOR = F
        assert _ev("=XOR(A1>0, A2>0, A1<0)", data) is False


# ==================== MAXIFS ====================
class TestMaxIfs:
    """MAXIFS 单条件 / 多条件。"""

    def test_basic(self):
        data = [
            ["A", 10],
            ["B", 20],
            ["A", 30],
            ["A", 5],
        ]
        assert _ev('=MAXIFS(B1:B4,A1:A4,"A")', data) == 30

    def test_no_match(self):
        data = [["A", 10], ["B", 20]]
        assert _ev('=MAXIFS(B1:B2,A1:A2,"C")', data) == 0

    def test_numeric_condition(self):
        data = [
            [1, 10],
            [2, 20],
            [3, 30],
            [2, 40],
        ]
        # 条件 >1 → 20, 30, 40 → max 40
        assert _ev('=MAXIFS(B1:B4,A1:A4,">1")', data) == 40

    def test_multi_conditions(self):
        data = [
            ["A", 1, 10],
            ["A", 2, 20],
            ["B", 1, 30],
            ["A", 1, 40],
        ]
        # A1:A4="A" 且 B1:B4=1 → 10, 40 → max 40
        assert _ev('=MAXIFS(C1:C4,A1:A4,"A",B1:B4,1)', data) == 40

    def test_too_few_args(self):
        assert _ev('=MAXIFS(A1:A2)', [[1], [2]]) == "#ERROR"


# ==================== MINIFS ====================
class TestMinIfs:
    """MINIFS 单条件 / 多条件。"""

    def test_basic(self):
        data = [
            ["A", 10],
            ["B", 20],
            ["A", 30],
            ["A", 5],
        ]
        assert _ev('=MINIFS(B1:B4,A1:A4,"A")', data) == 5

    def test_no_match(self):
        data = [["A", 10], ["B", 20]]
        assert _ev('=MINIFS(B1:B2,A1:A2,"C")', data) == 0

    def test_numeric_condition(self):
        data = [
            [1, 10],
            [2, 20],
            [3, 30],
            [2, 40],
        ]
        # 条件 >1 → 20, 30, 40 → min 20
        assert _ev('=MINIFS(B1:B4,A1:A4,">1")', data) == 20

    def test_multi_conditions(self):
        data = [
            ["A", 1, 10],
            ["A", 2, 20],
            ["B", 1, 30],
            ["A", 1, 40],
        ]
        # A1:A4="A" 且 B1:B4=1 → 10, 40 → min 10
        assert _ev('=MINIFS(C1:C4,A1:A4,"A",B1:B4,1)', data) == 10


# ==================== TEXTBEFORE ====================
class TestTextBefore:
    """TEXTBEFORE 取分隔符之前的文本。"""

    def test_first(self):
        assert _ev('=TEXTBEFORE("a-b-c","-")', [[1]]) == "a"

    def test_second(self):
        assert _ev('=TEXTBEFORE("a-b-c","-",2)', [[1]]) == "a-b"

    def test_reverse(self):
        """instance=-1 从后往前第一次。"""
        assert _ev('=TEXTBEFORE("a-b-c","-",-1)', [[1]]) == "a-b"

    def test_reverse_second(self):
        assert _ev('=TEXTBEFORE("a-b-c-d","-",-2)', [[1]]) == "a-b"

    def test_no_delim(self):
        assert _ev('=TEXTBEFORE("abc","-")', [[1]]) == "#N/A"

    def test_not_enough_instances(self):
        """instance 超过实际数量。"""
        assert _ev('=TEXTBEFORE("a-b","-",5)', [[1]]) == "#N/A"

    def test_multichar_delim(self):
        assert _ev('=TEXTBEFORE("hello::world","::")', [[1]]) == "hello"

    def test_chinese(self):
        assert _ev('=TEXTBEFORE("张三-李四-王五","-")', [[1]]) == "张三"

    def test_too_few_args(self):
        assert _ev('=TEXTBEFORE("abc")', [[1]]) == "#ERROR"


# ==================== TEXTAFTER ====================
class TestTextAfter:
    """TEXTAFTER 取分隔符之后的文本。"""

    def test_first(self):
        assert _ev('=TEXTAFTER("a-b-c","-")', [[1]]) == "b-c"

    def test_second(self):
        assert _ev('=TEXTAFTER("a-b-c","-",2)', [[1]]) == "c"

    def test_reverse(self):
        """instance=-1 从后往前第一次。"""
        assert _ev('=TEXTAFTER("a-b-c","-",-1)', [[1]]) == "c"

    def test_reverse_second(self):
        assert _ev('=TEXTAFTER("a-b-c-d","-",-2)', [[1]]) == "c-d"

    def test_no_delim(self):
        assert _ev('=TEXTAFTER("abc","-")', [[1]]) == "#N/A"

    def test_multichar_delim(self):
        assert _ev('=TEXTAFTER("hello::world","::")', [[1]]) == "world"

    def test_chinese(self):
        assert _ev('=TEXTAFTER("张三-李四-王五","-")', [[1]]) == "李四-王五"

    def test_too_few_args(self):
        assert _ev('=TEXTAFTER("abc")', [[1]]) == "#ERROR"


# ==================== VALUETOTEXT ====================
class TestValueToText:
    """VALUETOTEXT 转文本。"""

    def test_number(self):
        assert _ev("=VALUETOTEXT(123)", [[1]]) == "123"

    def test_float(self):
        assert _ev("=VALUETOTEXT(3.14)", [[1]]) == "3.14"

    def test_text(self):
        assert _ev('=VALUETOTEXT("hello")', [[1]]) == "hello"

    def test_cell_ref_number(self):
        assert _ev("=VALUETOTEXT(A1)", [[42]]) == "42"

    def test_cell_ref_text(self):
        assert _ev("=VALUETOTEXT(A1)", [["蜜蜂办公"]]) == "蜜蜂办公"

    def test_cell_ref_empty(self):
        assert _ev("=VALUETOTEXT(A1)", [[None]]) == ""


# ==================== ISBLANK ====================
class TestIsBlank:
    """ISBLANK 判断空。"""

    def test_true_none(self):
        assert _ev("=ISBLANK(A2)", [["x"], [None]]) is True

    def test_true_empty_string(self):
        assert _ev("=ISBLANK(A1)", [[""]]) is True

    def test_true_whitespace(self):
        """空白字符也算空（引擎特意放宽）。"""
        assert _ev("=ISBLANK(A1)", [["   "]]) is True

    def test_false(self):
        assert _ev("=ISBLANK(A1)", [["x"]]) is False

    def test_false_number(self):
        assert _ev("=ISBLANK(A1)", [[42]]) is False

    def test_false_zero(self):
        """0 不是空。"""
        assert _ev("=ISBLANK(A1)", [[0]]) is False


# ==================== ISNUMBER ====================
class TestIsNumber:
    """ISNUMBER 判断数字。"""

    def test_number(self):
        assert _ev("=ISNUMBER(A1)", [[42]]) is True

    def test_float(self):
        assert _ev("=ISNUMBER(A1)", [[3.14]]) is True

    def test_numeric_string(self):
        assert _ev("=ISNUMBER(A1)", [["42.5"]]) is True

    def test_zero(self):
        assert _ev("=ISNUMBER(A1)", [[0]]) is True

    def test_negative(self):
        assert _ev("=ISNUMBER(A1)", [[-5]]) is True

    def test_text(self):
        assert _ev("=ISNUMBER(A1)", [["abc"]]) is False

    def test_empty_string(self):
        assert _ev("=ISNUMBER(A1)", [[""]]) is False

    def test_none(self):
        assert _ev("=ISNUMBER(A2)", [["x"], [None]]) is False


# ==================== ISTEXT ====================
class TestIsText:
    """ISTEXT 判断文本。"""

    def test_text(self):
        assert _ev("=ISTEXT(A1)", [["hello"]]) is True

    def test_chinese(self):
        assert _ev("=ISTEXT(A1)", [["蜜蜂办公"]]) is True

    def test_number(self):
        assert _ev("=ISTEXT(A1)", [[42]]) is False

    def test_empty_string(self):
        """空字符串不算文本。"""
        assert _ev("=ISTEXT(A1)", [[""]]) is False

    def test_whitespace(self):
        """纯空白不算文本。"""
        assert _ev("=ISTEXT(A1)", [["   "]]) is False

    def test_none(self):
        assert _ev("=ISTEXT(A2)", [["x"], [None]]) is False


# ==================== ISLOGICAL ====================
class TestIsLogical:
    """
    ISLOGICAL 判断布尔。
    注意：引擎不支持 TRUE / FALSE 字面量，测试用比较表达式。
    """

    def test_true_from_compare(self):
        assert _ev("=ISLOGICAL(A1>0)", [[5]]) is True

    def test_false_from_compare(self):
        assert _ev("=ISLOGICAL(A1<0)", [[5]]) is True

    def test_number(self):
        assert _ev("=ISLOGICAL(A1)", [[1]]) is False

    def test_text(self):
        assert _ev("=ISLOGICAL(A1)", [["abc"]]) is False

    def test_empty(self):
        assert _ev("=ISLOGICAL(A1)", [[""]]) is False


# ==================== ISERROR ====================
class TestIsError:
    """ISERROR 判断错误。"""

    def test_div_zero(self):
        """1/0 抛 ZeroDivisionError → 被捕获 → 返回 True。"""
        assert _ev("=ISERROR(1/0)", [[1]]) is True

    def test_normal(self):
        assert _ev("=ISERROR(1+1)", [[1]]) is False

    def test_normal_text(self):
        assert _ev('=ISERROR("hello")', [[1]]) is False

    def test_error_string(self):
        """已经是 #ERROR 形式的字符串。"""
        assert _ev("=ISERROR(A1)", [["#ERROR: something"]]) is True

    def test_na_string(self):
        assert _ev("=ISERROR(A1)", [["#N/A"]]) is True

    def test_numeric_cell(self):
        assert _ev("=ISERROR(A1)", [[42]]) is False

    def test_unknown_function(self):
        """未知函数会返回 #ERROR 字符串 → ISERROR = True。"""
        assert _ev("=ISERROR(UNKNOWN_FN(1))", [[1]]) is True


# ==================== 组合测试 ====================
class TestCombinations:
    """多个新函数组合使用。"""

    def test_let_with_switch(self):
        data = [[2]]
        # x=2, SWITCH(x, 1, "一", 2, "二") → "二"
        result = _ev(
            '=LET(x,A1,SWITCH(x,1,"一",2,"二",3,"三"))', data
        )
        assert result == "二"

    def test_xlookup_with_default_from_cell(self):
        data = [["a", 1], ["b", 2], ["z", 999]]
        # 未找到 "z" → 返回 A3 = "z"？不，lookup 是 "x"
        # 用 A3 作为兜底值：未找到 "x" 时返回 A3 = "z"
        result = _ev(
            '=XLOOKUP("x",A1:A2,B1:B2,A3)', data
        )
        assert result == "z"

    def test_isnumber_inside_let(self):
        data = [["42"]]
        # x="42", ISNUMBER(x) → True
        assert _ev("=LET(x,A1,ISNUMBER(x))", data) is True

    def test_textbefore_with_let(self):
        data = [["prefix:suffix"]]
        assert _ev('=LET(s,A1,TEXTBEFORE(s,":"))', data) == "prefix"

    def test_maxifs_with_switch(self):
        """MAXIFS + SWITCH 组合。"""
        data = [
            [1, 10],
            [2, 20],
            [3, 30],
        ]
        result = _ev(
            '=SWITCH(MAXIFS(B1:B3,A1:A3,">1"),20,"中",30,"高","?")',
            data,
        )
        assert result == "高"


# ==================== 回归检查 ====================
class TestRegression:
    """确保新增函数不破坏旧函数。"""

    def test_sum_still_works(self):
        data = [[1], [2], [3]]
        assert _ev("=SUM(A1:A3)", data) == 6

    def test_if_still_works(self):
        data = [[5]]
        assert _ev('=IF(A1>0,"正","负")', data) == "正"

    def test_vlookup_still_works(self):
        data = [["a", 1], ["b", 2]]
        assert _ev('=VLOOKUP("b",A1:B2,2,FALSE)', data) == 2

    def test_sumifs_still_works(self):
        data = [
            [1, 10],
            [2, 20],
            [3, 30],
            [2, 40],
        ]
        assert _ev('=SUMIFS(B1:B4,A1:A4,"2")', data) == 60