# beeoffice/plugins/beeshow_image_suggest.py
"""
蜜演 AI 配图建议（任务 1.3）

功能：
  根据幻灯片文本内容推荐配图。

对标：
  - WPS 智能美化「智能配图」

数据源：
  - Unsplash（免费，需 API Key；可选）
  - Lorem Picsum（免费，无需 Key）
  - Pexels（免费，需 API Key；可选）

实现：
  1. 从幻灯片文本提取关键词
  2. 调用图库 API 搜索候选图
  3. 返回 3-5 张图的 URL
  4. UI 展示候选图，用户点击插入

降级：
  - 无 API Key 时用 Lorem Picsum 随机图
  - 全部失败时返回内置占位图

依赖：
  - urllib（标准库）
  - json / logging / re

注意：
  - 不依赖 Qt，可在纯 Python 环境跑
  - API 调用带超时（默认 10s）
  - 缓存结果（同一关键词不重复请求）
"""

import json
import logging
import re
import urllib.parse
import urllib.request
from typing import List, Dict


# ==================== 停用词 ====================
STOPWORDS = {
    "的", "了", "在", "是", "我", "有", "和", "就",
    "不", "人", "都", "一", "一个", "上", "也", "很",
    "到", "说", "要", "去", "你", "会", "着", "没有",
    "看", "好", "自己", "这", "那", "他", "她", "它",
    "们", "与", "及", "或", "但", "而", "对", "为",
    "以", "于", "把", "被", "从", "向", "让", "使",
    "the", "a", "an", "is", "are", "and", "or", "of",
    "to", "in", "on", "at", "for", "with", "by",
}


# ==================== 关键词提取 ====================
def extract_keywords(text: str, top_n: int = 3) -> List[str]:
    """
    从文本提取关键词（简化版：按词频 + 长度排序）。

    :param text: 输入文本
    :param top_n: 返回前 N 个
    :return: 关键词列表
    """
    if not text or not text.strip():
        return []

    # 1. 中文：2-gram 滑窗
    chinese_words = []
    for segment in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(segment) < 2:
            continue
        for i in range(len(segment) - 1):
            bigram = segment[i:i + 2]
            if bigram not in STOPWORDS:
                chinese_words.append(bigram)

    # 2. 英文：按单词
    english_words = [
        w.lower() for w in re.findall(r"[a-zA-Z]{3,}", text)
        if w.lower() not in STOPWORDS
    ]

    # 3. 词频统计
    freq = {}
    for w in chinese_words + english_words:
        freq[w] = freq.get(w, 0) + 1

    # 4. 排序：词频优先，长度次之
    sorted_words = sorted(
        freq.items(),
        key=lambda x: (x[1], len(x[0])),
        reverse=True,
    )
    return [w for w, _ in sorted_words[:top_n]]


# ==================== 图库 API ====================
class ImageSuggester:
    """配图建议器"""

    # Lorem Picsum（免费，无需 Key）
    PICSUM_BASE = "https://picsum.photos/seed/{seed}/800/600"

    # Unsplash API（需 Key）
    UNSPLASH_API = "https://api.unsplash.com/search/photos"

    # Pexels API（需 Key）
    PEXELS_API = "https://api.pexels.com/v1/search"

    def __init__(
        self,
        unsplash_key: str = "",
        pexels_key: str = "",
        timeout: int = 10,
    ):
        """
        :param unsplash_key: Unsplash API Key（可选）
        :param pexels_key: Pexels API Key（可选）
        :param timeout: 请求超时秒数
        """
        self.unsplash_key = unsplash_key
        self.pexels_key = pexels_key
        self.timeout = timeout
        # 缓存：关键词 → 结果列表
        self._cache: Dict[str, List[Dict[str, str]]] = {}

    # ==================== 公开接口 ====================
    def suggest(
        self, text: str, count: int = 3
    ) -> List[Dict[str, str]]:
        """
        根据文本推荐配图。

        :param text: 幻灯片文本
        :param count: 返回的图片数
        :return: [{"url": ..., "thumb": ..., "source": ..., "query": ...}]
        """
        keywords = extract_keywords(text, top_n=3)
        if not keywords:
            return self._picsum_fallback("default", count)

        query = " ".join(keywords[:2])
        return self.suggest_by_query(query, count)

    def suggest_by_query(
        self, query: str, count: int = 3
    ) -> List[Dict[str, str]]:
        """
        按关键词推荐配图。

        :param query: 搜索关键词
        :param count: 返回数量
        :return: 图片列表
        """
        if not query:
            return self._picsum_fallback("default", count)

        # 缓存命中
        if query in self._cache:
            cached = self._cache[query]
            return cached[:count]

        # 依次尝试各源
        results = []

        if self.unsplash_key:
            results = self._search_unsplash(query, count)
        if not results and self.pexels_key:
            results = self._search_pexels(query, count)
        if not results:
            results = self._picsum_fallback(query, count)

        self._cache[query] = results
        return results[:count]

    # ==================== Unsplash ====================
    def _search_unsplash(
        self, query: str, count: int
    ) -> List[Dict[str, str]]:
        """调用 Unsplash API"""
        try:
            url = (
                f"{self.UNSPLASH_API}?"
                f"{urllib.parse.urlencode({'query': query, 'per_page': count})}"
            )
            req = urllib.request.Request(
                url,
                headers={
                    "Authorization": f"Client-ID {self.unsplash_key}",
                    "Accept-Version": "v1",
                },
            )
            with urllib.request.urlopen(
                req, timeout=self.timeout
            ) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            results = []
            for item in data.get("results", [])[:count]:
                results.append({
                    "url": item["urls"]["regular"],
                    "thumb": item["urls"]["small"],
                    "source": "Unsplash",
                    "query": query,
                    "author": item.get("user", {}).get("name", ""),
                })
            return results
        except Exception as e:
            logging.warning(f"Unsplash 搜索失败：{e}")
            return []

    # ==================== Pexels ====================
    def _search_pexels(
        self, query: str, count: int
    ) -> List[Dict[str, str]]:
        """调用 Pexels API"""
        try:
            url = (
                f"{self.PEXELS_API}?"
                f"{urllib.parse.urlencode({'query': query, 'per_page': count})}"
            )
            req = urllib.request.Request(
                url,
                headers={"Authorization": self.pexels_key},
            )
            with urllib.request.urlopen(
                req, timeout=self.timeout
            ) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            results = []
            for item in data.get("photos", [])[:count]:
                results.append({
                    "url": item["src"]["large"],
                    "thumb": item["src"]["medium"],
                    "source": "Pexels",
                    "query": query,
                    "author": item.get("photographer", ""),
                })
            return results
        except Exception as e:
            logging.warning(f"Pexels 搜索失败：{e}")
            return []

    # ==================== Lorem Picsum 降级 ====================
    def _picsum_fallback(
        self, query: str, count: int
    ) -> List[Dict[str, str]]:
        """
        无 API Key 时用 Lorem Picsum 随机图。

        特点：
          - 免费、无需 Key
          - 按 seed 返回固定图（同 seed 同图）
          - 不能按关键词搜索
        """
        results = []
        for i in range(count):
            seed = f"{query}-{i}"
            # URL 编码
            seed_encoded = urllib.parse.quote(seed)
            results.append({
                "url": self.PICSUM_BASE.format(seed=seed_encoded),
                "thumb": self.PICSUM_BASE.format(seed=seed_encoded)
                    .replace("800/600", "200/150"),
                "source": "Lorem Picsum",
                "query": query,
                "author": "",
            })
        return results


# ==================== 便捷函数 ====================
def create_suggester_from_settings() -> ImageSuggester:
    """
    从 AppSettings 创建建议器。

    读取：
      - settings.unsplash_api_key
      - settings.pexels_api_key
    """
    try:
        from beeoffice.settings import AppSettings
        settings = AppSettings()
        return ImageSuggester(
            unsplash_key=getattr(settings, "unsplash_api_key", "") or "",
            pexels_key=getattr(settings, "pexels_api_key", "") or "",
        )
    except Exception as e:
        logging.error(f"创建配图建议器失败：{e}")
        return ImageSuggester()


def suggest_images_for_text(text: str, count: int = 3) -> List[Dict[str, str]]:
    """
    便捷函数：为文本推荐配图。

    :param text: 文本
    :param count: 数量
    :return: 图片列表
    """
    suggester = create_suggester_from_settings()
    return suggester.suggest(text, count)