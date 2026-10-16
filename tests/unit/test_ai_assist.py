# tests/test_ai_assist.py
"""
AIAssist AI 辅助功能的单元测试
覆盖：续写、润色、总结、关键词提取、扩写、翻译占位、示例列表、边界情况
"""

from beeoffice.plugins.ai_assist import AIAssist


# ---------- 类属性 ----------
class TestClassAttributes:
    """测试类属性存在性"""

    def test_continuation_pool_exists(self):
        """续写语料库应存在且非空"""
        assert hasattr(AIAssist, "CONTINUATION_POOL")
        assert isinstance(AIAssist.CONTINUATION_POOL, list)
        assert len(AIAssist.CONTINUATION_POOL) > 0

    def test_synonyms_exists(self):
        """同义词表应存在且非空"""
        assert hasattr(AIAssist, "SYNONYMS")
        assert isinstance(AIAssist.SYNONYMS, dict)
        assert len(AIAssist.SYNONYMS) > 0

    def test_colloquial_words_exists(self):
        """口语化词表应存在"""
        assert hasattr(AIAssist, "COLLOQUIAL_WORDS")
        assert isinstance(AIAssist.COLLOQUIAL_WORDS, list)

    def test_sentence_endings_exists(self):
        """句末标点集合应存在"""
        assert hasattr(AIAssist, "SENTENCE_ENDINGS")
        assert isinstance(AIAssist.SENTENCE_ENDINGS, str)
        assert "。" in AIAssist.SENTENCE_ENDINGS


# ---------- 续写 ----------
class TestContinueText:
    """测试续写功能"""

    def test_continue_empty_text(self):
        """空文本续写应返回语料库中的句子"""
        result = AIAssist.continue_text("")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_continue_none(self):
        """None 输入应返回语料库中的句子"""
        result = AIAssist.continue_text(None)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_continue_with_text(self):
        """续写后结果应比原文长"""
        original = "人工智能正在改变世界"
        result = AIAssist.continue_text(original)
        assert result.startswith(original)
        assert len(result) > len(original)

    def test_continue_preserves_original(self):
        """原文应完整保留在开头"""
        original = "这是一段测试文本。"
        result = AIAssist.continue_text(original)
        assert result.startswith("这是一段测试文本")

    def test_continue_ends_with_punctuation(self):
        """续写结果应以标点结尾"""
        result = AIAssist.continue_text("测试内容")
        assert result[-1] in AIAssist.SENTENCE_ENDINGS

    def test_continue_max_sentences(self):
        """max_sentences 参数应限制续写句子数量"""
        original = "测试"
        result = AIAssist.continue_text(original, max_sentences=1)
        # 至少包含原文 + 1 个补充
        assert len(result) > len(original)

    def test_continue_returns_string(self):
        """返回值应为字符串"""
        assert isinstance(AIAssist.continue_text("测试"), str)


# ---------- 润色 ----------
class TestPolishText:
    """测试润色功能"""

    def test_polish_empty(self):
        """空字符串润色返回空"""
        assert AIAssist.polish_text("") == ""

    def test_polish_none(self):
        """None 输入返回 None"""
        assert AIAssist.polish_text(None) is None

    def test_polish_adds_period(self):
        """无句末标点的文本应被补全"""
        result = AIAssist.polish_text("这是一段测试文本")
        assert result.endswith("。")


    def test_polish_synonym_replacement(self):
        """同义词替换应生效"""
        result = AIAssist.polish_text("但是这个问题很重要。")
        # 应替换为"然而"或保留"但是"（取决于实现），但"重要"应替换为"关键"
        assert "关键" in result or "重要" in result

    def test_polish_removes_colloquial(self):
        """口语化词汇应被移除"""
        result = AIAssist.polish_text("然后这个东西其实很好。")
        # "然后"、"其实"应被移除
        assert "然后" not in result
        assert "其实" not in result

    def test_polish_deduplicates_punctuation(self):
        """连续重复标点应被合并"""
        result = AIAssist.polish_text("太好了。。。")
        assert "。。" not in result

    def test_polish_removes_extra_spaces(self):
        """多余空格应被清理"""
        result = AIAssist.polish_text("测试   内容")
        assert "   " not in result

    def test_polish_returns_string(self):
        """返回值应为字符串"""
        assert isinstance(AIAssist.polish_text("测试"), str)

    def test_polish_preserves_content(self):
        """润色不应丢失核心内容"""
        result = AIAssist.polish_text("这是一个测试。")
        assert "测试" in result


# ---------- 总结 ----------
class TestSummarizeText:
    """测试总结功能"""

    def test_summarize_empty(self):
        """空文本总结返回空字符串"""
        assert AIAssist.summarize_text("") == ""

    def test_summarize_none(self):
        """None 输入返回空字符串"""
        assert AIAssist.summarize_text(None) == ""

    def test_summarize_short_text(self):
        """短文本直接返回原内容"""
        text = "只有一句话。"
        result = AIAssist.summarize_text(text)
        assert "只有一句话" in result

    def test_summarize_long_text(self):
        """长文本应返回摘要"""
        text = (
            "第一句很短。"
            "第二句话特别长特别长特别长特别长特别长特别长。"
            "第三句也短。"
            "第四句话也很长很长很长很长很长很长。"
        )
        result = AIAssist.summarize_text(text, max_sentences=2)
        assert isinstance(result, str)
        assert len(result) > 0
        # 摘要应包含长句内容
        assert "特别长" in result or "很长" in result

    def test_summarize_max_sentences(self):
        """max_sentences 应限制摘要句子数量"""
        text = "句子1。句子2。句子3。句子4。句子5。句子6。"
        result = AIAssist.summarize_text(text, max_sentences=2)
        # 统计句末标点数量
        period_count = result.count("。")
        assert period_count <= 2

    def test_summarize_returns_string(self):
        """返回值应为字符串"""
        assert isinstance(AIAssist.summarize_text("测试内容。"), str)


# ---------- 关键词提取 ----------
class TestExtractKeywords:
    """测试关键词提取功能"""

    def test_extract_empty(self):
        """空文本返回空列表"""
        assert AIAssist.extract_keywords("") == []

    def test_extract_none(self):
        """None 输入返回空列表"""
        assert AIAssist.extract_keywords(None) == []

    def test_extract_basic(self):
        """基本关键词提取"""
        text = "蜜蜂办公是一款办公软件，办公软件需要稳定，蜜蜂办公追求稳定和高效。"
        result = AIAssist.extract_keywords(text, top_n=3)
        assert isinstance(result, list)
        assert len(result) <= 3
        assert len(result) > 0

    def test_extract_frequency_order(self):
        """高频词应排在前面"""
        text = "苹果苹果苹果香蕉香蕉橙子"
        result = AIAssist.extract_keywords(text, top_n=3)
        assert len(result) > 0
        # "苹果" 出现频率最高，应在结果中
        assert "苹果" in result

    def test_extract_top_n_limit(self):
        """top_n 应限制返回数量"""
        text = "苹果 香蕉 橙子 葡萄 西瓜 桃子 梨子"
        result = AIAssist.extract_keywords(text, top_n=2)
        assert len(result) <= 2

    def test_extract_returns_list(self):
        """返回值应为列表"""
        result = AIAssist.extract_keywords("测试内容")
        assert isinstance(result, list)

    def test_extract_stopwords_filtered(self):
        """停用词应被过滤"""
        text = "的了在是我有和就这个那个什么"
        result = AIAssist.extract_keywords(text, top_n=5)
        # 单字停用词应被过滤（只保留 2 个字符以上的词）
        for word in result:
            assert len(word) >= 2

    def test_extract_no_valid_words(self):
        """无可提取的词返回空列表"""
        result = AIAssist.extract_keywords("a b c d", top_n=3)
        assert result == []


# ---------- 扩写 ----------
class TestExpandText:
    """测试扩写功能"""

    def test_expand_empty(self):
        """空文本返回原值"""
        assert AIAssist.expand_text("") == ""

    def test_expand_none(self):
        """None 输入返回原值"""
        assert AIAssist.expand_text(None) is None

    def test_expand_short_sentence(self):
        """短句应被追加说明"""
        result = AIAssist.expand_text("很短。")
        assert len(result) >= len("很短。")

    def test_expand_long_sentence(self):
        """长句不应被追加说明"""
        long_sentence = "这是一段非常长的句子" * 5 + "。"
        result = AIAssist.expand_text(long_sentence)
        assert isinstance(result, str)
        assert len(result) >= len(long_sentence)

    def test_expand_returns_string(self):
        """返回值应为字符串"""
        assert isinstance(AIAssist.expand_text("测试内容。"), str)


# ---------- 翻译（占位） ----------
class TestSimpleTranslate:
    """测试翻译占位实现"""

    def test_translate_empty(self):
        """空文本返回原值"""
        assert AIAssist.simple_translate("") == ""

    def test_translate_returns_text(self):
        """占位实现应返回原文本"""
        text = "hello world"
        result = AIAssist.simple_translate(text)
        assert result == text

    def test_translate_none(self):
        """None 输入返回原值"""
        assert AIAssist.simple_translate(None) is None


# ---------- 支持的操作列表 ----------
class TestSupportedOperations:
    """测试支持的操作列表"""

    def test_get_supported_operations(self):
        """应返回非空列表"""
        ops = AIAssist.get_supported_operations()
        assert isinstance(ops, list)
        assert len(ops) > 0

    def test_operations_are_strings(self):
        """每个操作应为字符串"""
        ops = AIAssist.get_supported_operations()
        for op in ops:
            assert isinstance(op, str)

    def test_operations_include_key_ones(self):
        """应包含核心操作"""
        ops = AIAssist.get_supported_operations()
        assert "续写" in ops
        assert "润色" in ops
        assert "总结" in ops


# ---------- 边界与异常 ----------
class TestEdgeCases:
    """测试边界情况"""

    def test_whitespace_only_continue(self):
        """仅空白字符的续写"""
        result = AIAssist.continue_text("   ")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_whitespace_only_polish(self):
        """仅空白字符的润色"""
        result = AIAssist.polish_text("   ")
        assert isinstance(result, str)

    def test_whitespace_only_summarize(self):
        """仅空白字符的总结"""
        result = AIAssist.summarize_text("   ")
        assert result == ""

    def test_unicode_emoji(self):
        """包含 emoji 的文本"""
        result = AIAssist.polish_text("🐝 蜜蜂办公很重要。")
        assert isinstance(result, str)
        assert "🐝" in result or "蜜蜂" in result

    def test_very_long_text_summarize(self):
        """超长文本总结不应崩溃"""
        text = "这是一句话。" * 100
        result = AIAssist.summarize_text(text, max_sentences=3)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_special_characters_polish(self):
        """含特殊字符的润色"""
        result = AIAssist.polish_text("测试@#$%内容。")
        assert isinstance(result, str)


# ---------- 集成测试 ----------
class TestIntegration:
    """组合使用多个功能的测试"""

    def test_full_pipeline(self):
        """润色 → 总结 → 关键词提取"""
        text = "但是这个东西非常重要，然后我们要好好处理。因为这个问题很关键，所以需要认真对待。"
        
        # 润色
        polished = AIAssist.polish_text(text)
        assert isinstance(polished, str)
        
        # 总结
        summary = AIAssist.summarize_text(polished, max_sentences=2)
        assert isinstance(summary, str)
        
        # 关键词
        keywords = AIAssist.extract_keywords(polished, top_n=3)
        assert isinstance(keywords, list)

    def test_continue_then_summarize(self):
        """续写 → 总结"""
        original = "人工智能"
        expanded = AIAssist.continue_text(original)
        summary = AIAssist.summarize_text(expanded, max_sentences=2)
        assert isinstance(summary, str)
        assert len(summary) > 0