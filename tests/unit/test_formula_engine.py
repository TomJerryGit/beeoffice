# tests/test_formula_engine.py
"""
FormulaEngine 公式引擎的单元测试

【重要说明】
  本文件测试的是 beeoffice/plugins/formula_engine.py —— 一个基于
  实例化的**旧版**公式引擎：
      engine = FormulaEngine(provider)
      engine.evaluate("=SUM(A1:A3)")

  与 beeoffice/plugins/beesheet_engine.py —— 一个基于 classmethod 的
  **新版**公式引擎（蜜算实际使用的）—— **不是同一个类**：

      FormulaEngine.evaluate("=SUM(A1:A3)", model)   # 新 API

  新引擎（beesheet_engine.FormulaEngine）的测试在：
    - tests/test_p0_regression/test_p0_05_formula_safe.py
    - tests/test_p0_regression/test_p0_05_safe_eval_boundary.py
    - tests/test_p0_regression/test_p0_11_sumifs.py

  本文档覆盖旧引擎的行为契约；两者 API 不同，请勿混用。

覆盖：统计函数、条件函数、查找函数、文本函数、数学函数、
      日期函数、算术表达式
"""
import pytest
from datetime import datetime

from beeoffice.plugins.formula_engine import FormulaEngine


# ---------- 测试数据与辅助 ----------
def make_engine(data):
    """
    创建 FormulaEngine 实例
    :param data: 二维列表或字典 {(row, col): value}
    """
    if isinstance(data, dict):
        def provider(row, col):
            return data.get((row, col))
    else:
        def provider(row, col):
            if 0 <= row < len(data) and 0 <= col < len(data[row]):
                return data[row][col]
            return None
    return FormulaEngine(provider)


@pytest.fixture
def simple_engine():
    """简单二维列表数据：3x3"""
    data = [
        [1, 2, 3],
        [4, 5, 6],
        [7, 8, 9],
    ]
    return make_engine(data)


@pytest.fixture
def mixed_engine():
    """混合数据：含字符串和数字"""
    data = [
        ["名称", "数量", "价格"],
        ["苹果", 10, 5.5],
        ["香蕉", 20, 3.0],
        ["橙子", 15, 4.5],
    ]
    return make_engine(data)


@pytest.fixture
def empty_engine():
    """空数据"""
    return make_engine([])


# ---------- 统计函数 ----------
class TestStatisticalFunctions:
    """测试统计类函数"""

    def test_sum_basic(self, simple_engine):
        """SUM 基础求和"""
        assert simple_engine.evaluate("=SUM(A1:C3)") == 45

    def test_sum_single_column(self, simple_engine):
        """SUM 单列"""
        assert simple_engine.evaluate("=SUM(A1:A3)") == 12

    def test_sum_single_row(self, simple_engine):
        """SUM 单行"""
        assert simple_engine.evaluate("=SUM(A1:C1)") == 6

    def test_sum_empty(self, empty_engine):
        """SUM 空数据返回 0"""
        assert empty_engine.evaluate("=SUM(A1:A5)") == 0

    def test_average_basic(self, simple_engine):
        """AVERAGE 基础平均"""
        assert simple_engine.evaluate("=AVERAGE(A1:C3)") == 5.0

    def test_average_single_column(self, simple_engine):
        """AVERAGE 单列"""
        assert simple_engine.evaluate("=AVERAGE(A1:A3)") == 4.0

    def test_average_empty(self, empty_engine):
        """AVERAGE 空数据返回 0"""
        assert empty_engine.evaluate("=AVERAGE(A1:A5)") == 0

    def test_count_numbers(self, simple_engine):
        """COUNT 统计数字个数"""
        assert simple_engine.evaluate("=COUNT(A1:C3)") == 9

    def test_count_mixed(self, mixed_engine):
        """COUNT 混合数据只数数字"""
        # 第一列是字符串，第二三列是数字
        result = mixed_engine.evaluate("=COUNT(B1:C4)")
        assert result == 6

    def test_counta_mixed(self, mixed_engine):
        """COUNTA 统计非空单元格"""
        result = mixed_engine.evaluate("=COUNTA(A1:C4)")
        assert result == 12

    def test_countif_numeric(self, simple_engine):
        """COUNTIF 数值条件"""
        # 大于 5 的数字：6, 7, 8, 9
        result = simple_engine.evaluate('=COUNTIF(A1:C3,">5")')
        assert result == 4

    def test_countif_equal(self, simple_engine):
        """COUNTIF 相等条件"""
        result = simple_engine.evaluate('=COUNTIF(A1:C3,"=5")')
        assert result == 1

    def test_max_basic(self, simple_engine):
        """MAX 最大值"""
        assert simple_engine.evaluate("=MAX(A1:C3)") == 9

    def test_max_empty(self, empty_engine):
        """MAX 空数据返回 0"""
        assert empty_engine.evaluate("=MAX(A1:A5)") == 0

    def test_min_basic(self, simple_engine):
        """MIN 最小值"""
        assert simple_engine.evaluate("=MIN(A1:C3)") == 1

    def test_min_empty(self, empty_engine):
        """MIN 空数据返回 0"""
        assert empty_engine.evaluate("=MIN(A1:A5)") == 0


# ---------- 条件函数 ----------
class TestConditionalFunctions:
    """测试条件类函数"""

    def test_if_true(self, simple_engine):
        """IF 条件成立"""
        assert simple_engine.evaluate('=IF(A1>0,"正","负")') == "正"

    def test_if_false(self, simple_engine):
        """IF 条件不成立"""
        assert simple_engine.evaluate('=IF(A1<0,"正","负")') == "负"

    def test_if_two_args(self, simple_engine):
        """IF 只有两个参数"""
        assert simple_engine.evaluate("=IF(A1>0,100)") == 100

    def test_if_nested(self, simple_engine):
        """IF 嵌套 SUM"""
        result = simple_engine.evaluate('=IF(SUM(A1:A3)>5,"大","小")')
        assert result == "大"

    def test_and_true(self, simple_engine):
        """AND 全部成立"""
        assert simple_engine.evaluate("=AND(A1>0,B1>0)") is True

    def test_and_false(self, simple_engine):
        """AND 存在不成立"""
        assert simple_engine.evaluate("=AND(A1>0,A1>10)") is False

    def test_or_true(self, simple_engine):
        """OR 任一成立"""
        assert simple_engine.evaluate("=OR(A1>100,A1>0)") is True

    def test_or_false(self, simple_engine):
        """OR 全部不成立"""
        assert simple_engine.evaluate("=OR(A1>100,A1>50)") is False


# ---------- 查找函数 ----------
class TestLookupFunctions:
    """测试查找类函数"""

    def test_vlookup_found(self, mixed_engine):
        """VLOOKUP 找到匹配值"""
        # 在 A1:C4 中查找 "苹果"，返回第 2 列（数量）
        result = mixed_engine.evaluate('=VLOOKUP("苹果",A1:C4,2)')
        assert result == 10

    def test_vlookup_not_found(self, mixed_engine):
        """VLOOKUP 未找到应报错"""
        with pytest.raises(ValueError):
            mixed_engine.evaluate('=VLOOKUP("西瓜",A1:C4,2)')

    def test_vlookup_col_index_out_of_range(self, mixed_engine):
        """VLOOKUP 列索引越界应报错"""
        with pytest.raises(ValueError):
            mixed_engine.evaluate('=VLOOKUP("苹果",A1:C4,10)')


# ---------- 文本函数 ----------
class TestTextFunctions:
    """测试文本类函数"""

    def test_concatenate(self, mixed_engine):
        """CONCATENATE 拼接"""
        result = mixed_engine.evaluate('=CONCATENATE("a","b","c")')
        assert result == "abc"

    def test_concatenate_with_cells(self, mixed_engine):
        """CONCATENATE 拼接单元格"""
        result = mixed_engine.evaluate("=CONCATENATE(A2,B2)")
        assert result == "苹果10"

    def test_left(self):
        """LEFT 取左侧字符"""
        engine = make_engine([["Hello World"]])
        assert engine.evaluate("=LEFT(A1,5)") == "Hello"

    def test_left_default(self):
        """LEFT 默认取1个字符"""
        engine = make_engine([["Hello"]])
        assert engine.evaluate("=LEFT(A1)") == "H"

    def test_right(self):
        """RIGHT 取右侧字符"""
        engine = make_engine([["Hello World"]])
        assert engine.evaluate("=RIGHT(A1,5)") == "World"

    def test_right_default(self):
        """RIGHT 默认取1个字符"""
        engine = make_engine([["Hello"]])
        assert engine.evaluate("=RIGHT(A1)") == "o"

    def test_len(self):
        """LEN 长度"""
        engine = make_engine([["Hello"]])
        assert engine.evaluate("=LEN(A1)") == 5

    def test_len_chinese(self):
        """LEN 中文字符长度"""
        engine = make_engine([["蜜蜂办公"]])
        assert engine.evaluate("=LEN(A1)") == 4

    def test_upper(self):
        """UPPER 转大写"""
        engine = make_engine([["hello"]])
        assert engine.evaluate("=UPPER(A1)") == "HELLO"

    def test_lower(self):
        """LOWER 转小写"""
        engine = make_engine([["HELLO"]])
        assert engine.evaluate("=LOWER(A1)") == "hello"


# ---------- 数学函数 ----------
class TestMathFunctions:
    """测试数学类函数"""

    def test_round(self):
        """ROUND 四舍五入"""
        engine = make_engine([[3.14159]])
        assert engine.evaluate("=ROUND(A1,2)") == 3.14

    def test_round_zero(self):
        """ROUND 取整"""
        engine = make_engine([[3.7]])
        assert engine.evaluate("=ROUND(A1,0)") == 4

    def test_abs_positive(self):
        """ABS 正数"""
        engine = make_engine([[5]])
        assert engine.evaluate("=ABS(A1)") == 5

    def test_abs_negative(self):
        """ABS 负数"""
        engine = make_engine([[-5]])
        assert engine.evaluate("=ABS(A1)") == 5

    def test_int(self):
        """INT 向下取整"""
        engine = make_engine([[3.9]])
        assert engine.evaluate("=INT(A1)") == 3

    def test_mod(self):
        """MOD 取余"""
        engine = make_engine([[10]])
        assert engine.evaluate("=MOD(A1,3)") == 1

    def test_mod_zero_divisor(self):
        """MOD 除数为 0 应报错"""
        engine = make_engine([[10]])
        with pytest.raises(ValueError):
            engine.evaluate("=MOD(A1,0)")


# ---------- 日期函数 ----------
class TestDateFunctions:
    """测试日期类函数"""

    def test_today(self):
        """TODAY 返回今天的日期字符串"""
        engine = make_engine([])
        result = engine.evaluate("=TODAY()")
        today = datetime.now().strftime("%Y-%m-%d")
        assert result == today

    def test_now(self):
        """NOW 返回当前日期时间"""
        engine = make_engine([])
        result = engine.evaluate("=NOW()")
        assert isinstance(result, str)
        # 应包含年份
        assert str(datetime.now().year) in result


# ---------- 算术表达式 ----------
class TestArithmeticExpressions:
    """测试纯算术表达式"""

    def test_simple_addition(self):
        """简单加法"""
        engine = make_engine([[1], [2]])
        assert engine.evaluate("=A1+A2") == 3

    def test_multiplication(self):
        """乘法"""
        engine = make_engine([[3], [4]])
        assert engine.evaluate("=A1*A2") == 12

    def test_mixed_operations(self):
        """混合运算"""
        engine = make_engine([[10], [5]])
        assert engine.evaluate("=A1+A2*2") == 20

    def test_parentheses(self):
        """带括号"""
        engine = make_engine([[10], [5]])
        assert engine.evaluate("=(A1+A2)*2") == 30

    def test_constants_only(self):
        """仅常量"""
        engine = make_engine([])
        assert engine.evaluate("=1+2*3") == 7

    def test_division(self):
        """除法"""
        engine = make_engine([[10], [2]])
        assert engine.evaluate("=A1/A2") == 5


# ---------- 边界与异常 ----------
class TestEdgeCases:
    """测试边界情况和异常处理"""

    def test_non_formula_returns_as_is(self, simple_engine):
        """非公式字符串原样返回"""
        assert simple_engine.evaluate("hello") == "hello"

    def test_non_string_returns_as_is(self, simple_engine):
        """非字符串输入原样返回"""
        assert simple_engine.evaluate(123) == 123
        assert simple_engine.evaluate(None) is None

    def test_empty_formula(self, simple_engine):
        """空公式"""
        result = simple_engine.evaluate("=")
        # 空表达式会触发求值错误或被捕获
        assert result is None or result == "" or result == 0

    def test_chinese_parentheses(self, simple_engine):
        """中文括号应被自动转换"""
        result = simple_engine.evaluate('=SUM（A1:A3）')
        assert result == 12

    def test_chinese_comma(self, simple_engine):
        """中文逗号应被自动转换"""
        result = simple_engine.evaluate("=IF（A1>0，100，0）")
        assert result == 100

    def test_trailing_semicolon(self, simple_engine):
        """末尾分号应被忽略"""
        result = simple_engine.evaluate('=SUM(A1:A3);')
        assert result == 12

    def test_invalid_function(self, simple_engine):
        """未知函数应抛出异常"""
        with pytest.raises(ValueError):
            simple_engine.evaluate("=UNKNOWN(A1)")

    def test_invalid_range(self, simple_engine):
        """无效范围"""
        with pytest.raises(ValueError):
            simple_engine.evaluate("=SUM(XYZ)")

    def test_unicode_in_string(self, mixed_engine):
        """中文字符串常量"""
        result = mixed_engine.evaluate('=IF(A1="名称","是","否")')
        assert result == "是"


# ---------- 集成测试 ----------
class TestIntegration:
    """组合使用多个函数的测试"""

    def test_sum_with_condition(self, simple_engine):
        """IF + SUM 组合"""
        result = simple_engine.evaluate('=IF(SUM(A1:C1)>5,"通过","不通过")')
        assert result == "通过"

    def test_average_round(self, simple_engine):
        """ROUND + AVERAGE 组合"""
        result = simple_engine.evaluate("=ROUND(AVERAGE(A1:C3),1)")
        assert result == 5.0

    def test_count_if_with_cells(self, mixed_engine):
        """COUNTIF + 单元格引用"""
        result = mixed_engine.evaluate('=COUNTIF(B1:B4,">10")')
        # 10 不满足 >10，20 和 15 满足
        assert result == 2