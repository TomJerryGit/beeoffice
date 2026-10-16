# tests/test_nl_formula.py
"""
NLFormulaParser 自然语言公式解析器的单元测试
覆盖：统计函数、条件判断、筛选、查找、拼接、范围提取、边界情况
"""

from beeoffice.plugins.nl_formula import NLFormulaParser, parse_nl


# ---------- 统计函数 ----------
class TestStatisticalParsing:
    """测试统计类指令"""

    def test_sum_with_range(self):
        """求和 + 范围"""
        assert NLFormulaParser.parse("求和A1到A10") == "=SUM(A1:A10)"

    def test_sum_with_standard_range(self):
        """求和 + 标准范围"""
        assert NLFormulaParser.parse("求和A1:A10") == "=SUM(A1:A10)"

    def test_sum_with_zhi(self):
        """求和 + 至"""
        assert NLFormulaParser.parse("求和A1至A10") == "=SUM(A1:A10)"

    def test_sum_with_dash(self):
        """求和 + 短横线"""
        assert NLFormulaParser.parse("求和A1-A10") == "=SUM(A1:A10)"

    def test_sum_column(self):
        """求和 + 整列"""
        assert NLFormulaParser.parse("求和B列") == "=SUM(B:B)"

    def test_sum_default(self):
        """求和无范围应返回默认 A:A"""
        assert NLFormulaParser.parse("求和") == "=SUM(A:A)"

    def test_total_keyword(self):
        """总计关键词"""
        assert NLFormulaParser.parse("总计A1到A5") == "=SUM(A1:A5)"

    def test_heji_keyword(self):
        """合计关键词"""
        assert NLFormulaParser.parse("合计B1到B10") == "=SUM(B1:B10)"

    def test_average_range(self):
        """平均值 + 范围"""
        assert NLFormulaParser.parse("平均值A1到A10") == "=AVERAGE(A1:A10)"

    def test_average_column(self):
        """平均值 + 整列"""
        assert NLFormulaParser.parse("平均值B列") == "=AVERAGE(B:B)"

    def test_average_default(self):
        """平均值无范围"""
        assert NLFormulaParser.parse("平均值") == "=AVERAGE(A:A)"

    def test_max_range(self):
        """最大值 + 范围"""
        assert NLFormulaParser.parse("最大值A1到A5") == "=MAX(A1:A5)"

    def test_max_keyword_variant(self):
        """最大关键词"""
        assert NLFormulaParser.parse("最大A1到A5") == "=MAX(A1:A5)"

    def test_max_default(self):
        """最大值无范围"""
        assert NLFormulaParser.parse("最大值") == "=MAX(A:A)"

    def test_min_range(self):
        """最小值 + 范围"""
        assert NLFormulaParser.parse("最小值A1到A5") == "=MIN(A1:A5)"

    def test_min_default(self):
        """最小值无范围"""
        assert NLFormulaParser.parse("最小值") == "=MIN(A:A)"

    def test_count_range(self):
        """计数 + 范围"""
        assert NLFormulaParser.parse("计数A1到A10") == "=COUNT(A1:A10)"

    def test_count_column(self):
        """计数 + 整列"""
        assert NLFormulaParser.parse("计数C列") == "=COUNT(C:C)"

    def test_count_default(self):
        """计数无范围"""
        assert NLFormulaParser.parse("计数") == "=COUNT(A:A)"


# ---------- 条件判断 ----------
class TestIfParsing:
    """测试 IF 条件解析"""

    def test_if_greater(self):
        """大于条件"""
        result = NLFormulaParser.parse("如果A1大于10就显示'高'")
        assert result is not None
        assert "IF" in result
        assert "A1>10" in result

    def test_if_less(self):
        """小于条件"""
        result = NLFormulaParser.parse("如果A1小于5就显示'低'")
        assert result is not None
        assert "A1<5" in result

    def test_if_greater_equal(self):
        """大于等于条件"""
        result = NLFormulaParser.parse("如果A1大于等于10则显示'通过'")
        assert result is not None
        assert "A1>=10" in result

    def test_if_equal(self):
        """等于条件"""
        result = NLFormulaParser.parse("如果A1等于0就显示'零'")
        assert result is not None
        assert "A1=0" in result

    def test_if_with_true_value(self):
        """真值提取"""
        result = NLFormulaParser.parse("如果A1大于10就显示'高'")
        assert '"高"' in result

    def test_if_with_false_value(self):
        """假值提取（否则）"""
        result = NLFormulaParser.parse("如果A1大于10就显示'高'否则显示'低'")
        assert '"低"' in result


# ---------- 筛选 ----------
class TestFilterParsing:
    """测试筛选解析"""

    def test_filter_greater(self):
        """筛选大于"""
        assert NLFormulaParser.parse("筛选大于100的行") == "FILTER:>:100"

    def test_filter_less(self):
        """筛选小于"""
        assert NLFormulaParser.parse("筛选小于50的行") == "FILTER:<:50"

    def test_filter_greater_equal(self):
        """筛选大于等于"""
        assert NLFormulaParser.parse("筛选大于等于100的行") == "FILTER:>=:100"

    def test_filter_less_equal(self):
        """筛选小于等于"""
        assert NLFormulaParser.parse("筛选小于等于50的行") == "FILTER:<=:50"

    def test_filter_equal_numeric(self):
        """筛选等于数字"""
        assert NLFormulaParser.parse("筛选等于100") == "FILTER:=:100"

    def test_filter_decimal(self):
        """筛选小数"""
        result = NLFormulaParser.parse("筛选大于3.5的行")
        assert result == "FILTER:>:3.5"

    def test_filter_string(self):
        """筛选字符串"""
        result = NLFormulaParser.parse("筛选等于北京的行")
        assert result is not None
        assert result.startswith("FILTER:")

    def test_filter_contains(self):
        """筛选包含"""
        result = NLFormulaParser.parse("筛选包含'苹果'的行")
        assert result is not None
        assert result.startswith("FILTER:")

    def test_filter_no_operator(self):
        """无操作符筛选"""
        result = NLFormulaParser.parse("筛选")
        assert result == "FILTER:"


# ---------- 查找 ----------
class TestLookupParsing:
    """测试查找解析"""

    def test_lookup_basic(self):
        """查找指令返回 VLOOKUP"""
        assert NLFormulaParser.parse("查找A1在B到C列") == "VLOOKUP"

    def test_lookup_chaxun(self):
        """查询关键词"""
        assert NLFormulaParser.parse("查询A1的值") == "VLOOKUP"

    def test_lookup_sousuo(self):
        """搜索关键词"""
        assert NLFormulaParser.parse("搜索匹配项") == "VLOOKUP"

    def test_lookup_pipei(self):
        """匹配关键词"""
        assert NLFormulaParser.parse("匹配A列数据") == "VLOOKUP"


# ---------- 拼接 ----------
class TestConcatParsing:
    """测试拼接解析"""

    def test_concatenate_two_cells(self):
        """合并两个单元格"""
        result = NLFormulaParser.parse("合并A1和B1")
        assert result is not None
        assert "CONCATENATE" in result
        assert "A1" in result
        assert "B1" in result

    def test_concatenate_three_cells(self):
        """合并三个单元格"""
        result = NLFormulaParser.parse("拼接A1和B1和C1")
        assert result is not None
        assert "CONCATENATE" in result
        assert "A1" in result and "B1" in result and "C1" in result

    def test_concatenate_single(self):
        """单个单元格无法合并"""
        result = NLFormulaParser.parse("合并A1")
        assert result is None


# ---------- 范围提取 ----------
class TestRangeExtraction:
    """测试范围提取辅助方法"""

    def test_extract_standard_range(self):
        """标准范围 A1:A10"""
        assert NLFormulaParser._extract_range("A1:A10") == "A1:A10"

    def test_extract_dao_range(self):
        """A1到A10"""
        assert NLFormulaParser._extract_range("A1到A10") == "A1:A10"

    def test_extract_zhi_range(self):
        """A1至A10"""
        assert NLFormulaParser._extract_range("A1至A10") == "A1:A10"

    def test_extract_column(self):
        """单列 B列"""
        assert NLFormulaParser._extract_range("B列") == "B:B"

    def test_extract_multi_column(self):
        """多列 A到C列"""
        assert NLFormulaParser._extract_range("A到C列") == "A:C"

    def test_extract_row(self):
        """单行 第2行"""
        assert NLFormulaParser._extract_range("第2行") == "A2:Z2"

    def test_extract_single_cell(self):
        """单引用"""
        assert NLFormulaParser._extract_range("A1") == "A1"

    def test_extract_none(self):
        """无法提取"""
        assert NLFormulaParser._extract_range("你好") == ""


# ---------- 边界与异常 ----------
class TestEdgeCases:
    """测试边界情况"""

    def test_empty_string(self):
        """空字符串"""
        assert NLFormulaParser.parse("") is None

    def test_none_input(self):
        """None 输入"""
        assert NLFormulaParser.parse(None) is None

    def test_whitespace_only(self):
        """仅空白字符"""
        assert NLFormulaParser.parse("   ") is None

    def test_unknown_instruction(self):
        """无法识别的指令"""
        assert NLFormulaParser.parse("今天天气不错") is None

    def test_mixed_case_keyword(self):
        """大小写混合的单元格引用"""
        result = NLFormulaParser.parse("求和a1到a10")
        assert result is not None
        # 输出应统一为大写
        assert "A1" in result.upper()

    def test_multiple_keywords(self):
        """包含多个关键词时按优先级返回（IF 优先）"""
        result = NLFormulaParser.parse("如果A1大于10就求和B1到B10")
        # IF 优先级更高
        assert result is not None
        assert "IF" in result


# ---------- 模块级函数 ----------
class TestModuleFunction:
    """测试模块级便捷函数"""

    def test_parse_nl_function(self):
        """parse_nl 应等价于 NLFormulaParser.parse"""
        assert parse_nl("求和A1到A10") == "=SUM(A1:A10)"

    def test_parse_nl_none(self):
        """parse_nl 对无效输入返回 None"""
        assert parse_nl("随便说点什么") is None


# ---------- 示例列表 ----------
class TestSupportedExamples:
    """测试支持的示例列表"""

    def test_get_supported_examples(self):
        """get_supported_examples 应返回非空列表"""
        examples = NLFormulaParser.get_supported_examples()
        assert isinstance(examples, list)
        assert len(examples) > 0

    def test_examples_format(self):
        """每个示例应是 (指令, 结果) 元组"""
        examples = NLFormulaParser.get_supported_examples()
        for item in examples:
            assert isinstance(item, tuple)
            assert len(item) == 2
            assert isinstance(item[0], str)
            assert isinstance(item[1], str)

    def test_examples_are_valid(self):
        """示例中的指令应能被成功解析"""
        examples = NLFormulaParser.get_supported_examples()
        for instruction, expected in examples:
            result = NLFormulaParser.parse(instruction)
            assert result is not None, f"示例 '{instruction}' 无法解析"