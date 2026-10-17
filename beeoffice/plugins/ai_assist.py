# beeoffice/plugins/ai_assist.py
"""
AI 辅助功能：续写、润色、总结、关键词提取、扩写、翻译占位
基于规则实现，稳定且无需外部依赖。

本次更新：
  - extract_keywords 改用 2-gram 滑窗，避免连续中文被当成一个整体词
    （例如"苹果苹果苹果香蕉香蕉橙子"应拆出"苹果"、"果苹"、"香蕉"等 2-gram）
"""
import re
import random
import logging
from typing import List


class AIAssist:
    """基础 AI 辅助功能（基于规则）"""

    # ==================== 续写语料库 ====================
    CONTINUATION_POOL = [
        "随着技术的不断发展，这一趋势将持续下去。",
        "在未来的日子里，我们需要更加关注用户的需求。",
        "综上所述，我们可以得出结论：这是一个值得深入探讨的话题。",
        "然而，这种方法也存在一定的局限性。",
        "因此，我们应该采取更加积极的措施来应对挑战。",
        "此外，还需要考虑各种可能的风险因素。",
        "值得注意的是，行业内的竞争日益激烈。",
        "在这样的背景下，创新成为了企业发展的关键。",
        "同时，我们也应该看到其中蕴含的机遇。",
        "总而言之，这是一个需要长期投入和持续优化的过程。",
        "从长远来看，这种策略将带来可观的回报。",
        "在此基础上，我们还可以进一步扩展应用场景。",
    ]

    # ==================== 同义词替换表 ====================
    SYNONYMS = {
        "但是": "然而",
        "因为": "由于",
        "所以": "因此",
        "很多": "大量",
        "非常": "十分",
        "重要": "关键",
        "好": "优秀",
        "坏": "糟糕",
        "大": "庞大",
        "小": "微小",
        "快": "迅速",
        "慢": "迟缓",
        "漂亮": "优美",
        "好看": "美观",
        "难": "困难",
        "容易": "简单",
    }

    # ==================== 常见口语化词汇 ====================
    COLLOQUIAL_WORDS = [
        "然后", "那个", "就是", "的话", "其实",
        "反正", "差不多", "大概", "可能吧",
    ]

    # ==================== 句子结束标点 ====================
    SENTENCE_ENDINGS = "。！？!?"

    # ==================== 续写 ====================
    @classmethod
    def continue_text(cls, text: str, max_sentences: int = 2) -> str:
        """
        根据输入文本续写若干句子
        :param text: 上下文文本
        :param max_sentences: 最多续写的句子数
        :return: 续写后的完整文本
        """
        if not text or not text.strip():
            return random.choice(cls.CONTINUATION_POOL)

        try:
            # 随机选择 1~max_sentences 个句子拼接
            count = random.randint(1, max(1, max_sentences))
            additions = random.sample(
                cls.CONTINUATION_POOL,
                min(count, len(cls.CONTINUATION_POOL))
            )
            # 保持原文末尾标点，若没有则补一个句号
            base = text.rstrip()
            if base and base[-1] not in cls.SENTENCE_ENDINGS:
                base += "。"
            return base + "".join(additions)
        except Exception as e:
            logging.error(f"续写失败: {e}")
            return text

    # ==================== 润色 ====================
    @classmethod
    def polish_text(cls, text: str) -> str:
        """
        润色文本：替换同义词、清理口语化词汇、统一标点
        :param text: 待润色的文本
        :return: 润色后的文本
        """
        if not text or not text.strip():
            return text

        result = text
        try:
            # 同义词替换
            for old, new in cls.SYNONYMS.items():
                result = result.replace(old, new)

            # 移除口语化词汇
            for word in cls.COLLOQUIAL_WORDS:
                result = result.replace(word, "")

            # 去除多余空格
            result = re.sub(r"\s+", " ", result).strip()

            # 去除连续重复标点（如 。。 -> 。）
            result = re.sub(r"([。！？!?])+", r"\1", result)

            # 统一英文逗号到中文逗号（仅在中文上下文中）
            if re.search(r"[\u4e00-\u9fff]", result):
                result = result.replace(",", "，")

            # 确保以标点结尾
            if result and result[-1] not in cls.SENTENCE_ENDINGS:
                result += "。"

            return result
        except Exception as e:
            logging.error(f"润色失败: {e}")
            return text

    # ==================== 总结 ====================
    @classmethod
    def summarize_text(cls, text: str, max_sentences: int = 3) -> str:
        """
        简单提取式摘要：按句子长度排序，选取最长的几句
        :param text: 原文
        :param max_sentences: 摘要包含的最大句子数
        :return: 摘要文本
        """
        if not text or not text.strip():
            return ""

        try:
            # 按句末标点切分
            sentences = re.split(r"[。！？!?]", text)
            sentences = [s.strip() for s in sentences if s.strip()]

            if not sentences:
                return ""

            # 如果句子数不超过上限，直接返回原文
            if len(sentences) <= max_sentences:
                return "。".join(sentences) + "。"

            # 按长度排序，取最长的 N 句
            # 但保留原始顺序，使摘要更连贯
            indexed = list(enumerate(sentences))
            indexed.sort(key=lambda x: len(x[1]), reverse=True)
            top_indices = sorted([idx for idx, _ in indexed[:max_sentences]])

            summary_sentences = [sentences[i] for i in top_indices]
            summary = "。".join(summary_sentences)
            if summary and summary[-1] not in cls.SENTENCE_ENDINGS:
                summary += "。"
            return summary
        except Exception as e:
            logging.error(f"总结失败: {e}")
            return ""

    # ==================== 关键词提取 ====================
    @classmethod
    def extract_keywords(cls, text: str, top_n: int = 5) -> List[str]:
        """
        简单关键词提取：按词频统计，过滤停用词
        :param text: 原文
        :param top_n: 返回关键词数量
        :return: 关键词列表

        本次修复：使用 2-gram 滑窗，避免连续中文被当成一个整体词。
        """
        if not text or not text.strip():
            return []

        try:
            # 停用词表
            stopwords = {
                "的", "了", "在", "是", "我", "有", "和", "就",
                "不", "人", "都", "一", "一个", "上", "也", "很",
                "到", "说", "要", "去", "你", "会", "着", "没有",
                "看", "好", "自己", "这", "那", "他", "她", "它",
                "们", "与", "及", "或", "但", "而", "对", "为",
                "以", "于", "把", "被", "从", "向", "让", "使",
            }

            # 中文 2-gram 滑窗：避免连续中文被当成一个词
            words = []
            for segment in re.findall(r"[\u4e00-\u9fff]+", text):
                if len(segment) < 2:
                    continue
                for i in range(len(segment) - 1):
                    bigram = segment[i:i + 2]
                    if bigram not in stopwords:
                        words.append(bigram)

            if not words:
                return []

            # 词频统计
            freq = {}
            for w in words:
                freq[w] = freq.get(w, 0) + 1

            # 排序并返回前 N 个
            sorted_words = sorted(
                freq.items(), key=lambda x: x[1], reverse=True
            )
            return [w for w, _ in sorted_words[:top_n]]
        except Exception as e:
            logging.error(f"关键词提取失败: {e}")
            return []

    # ==================== 扩写 ====================
    @classmethod
    def expand_text(cls, text: str) -> str:
        """
        简单扩写：在每句话后追加补充说明
        :param text: 原文
        :return: 扩写后的文本
        """
        if not text or not text.strip():
            return text

        try:
            sentences = re.split(r"([。！？!?])", text)
            result = []
            for i in range(0, len(sentences) - 1, 2):
                sentence = sentences[i].strip()
                ending = sentences[i + 1] if i + 1 < len(sentences) else ""
                if not sentence:
                    continue
                result.append(sentence + ending)
                # 对较短的句子追加说明
                if len(sentence) < 30:
                    result.append("这一点值得进一步说明。")
            return "".join(result) if result else text
        except Exception as e:
            logging.error(f"扩写失败: {e}")
            return text

    # ==================== 翻译（占位） ====================
    @classmethod
    def simple_translate(cls, text: str, target: str = "zh") -> str:
        """
        简易翻译（仅作演示，实际项目中可接入翻译 API）
        此处仅做占位实现，返回原文并附加提示
        :param text: 原文
        :param target: 目标语言（zh/en）
        :return: 翻译结果
        """
        if not text or not text.strip():
            return text
        # 这是一个占位实现，真实翻译需要接入翻译 API
        return text

    # ==================== 支持的操作列表 ====================
    @classmethod
    def get_supported_operations(cls) -> List[str]:
        """返回支持的 AI 操作列表"""
        return [
            "续写",
            "润色",
            "总结",
            "关键词提取",
            "扩写",
        ]