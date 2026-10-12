# beeoffice/plugins/beeshow_ai_service.py
"""
蜜演 AI 服务层（任务 1.1）

职责：
  - generate_outline  : 调用 LLM 生成结构化演示大纲
  - generate_notes    : 生成演讲稿（任务 1.2）
  - suggest_images    : 推荐配图（任务 1.3，本次占位）

设计：
  - 纯 Python 服务层，不依赖 Qt，可独立测试
  - 支持多家 LLM 提供商：OpenAI 兼容 API / DeepSeek / Ollama 本地
  - 输出结构化 JSON（SlideOutline 列表），驱动版式系统
  - 支持多轮对话：clarify() 澄清意图，refine() 修改大纲
  - 无 API Key 时优雅降级到本地模板（保持向后兼容）

对标：
  - WPS AIPPT 的「意图澄清 + 边聊边改 + 分层精调」
  - 蜜演：JSON IR → LAYOUTS 版式 → Markdown 渲染

依赖：
  - json / logging / urllib（标准库，无需第三方）
  - 可选 requests（若已安装，优先使用）

注意：
  - API Key 从 AppSettings 读取：settings.ai_api_key
  - 无 Key 时降级到 _local_fallback_outline
  - 所有 LLM 调用带超时（默认 30s）
  - 输出严格用 JSON Schema 约束，失败时重试 2 次
"""

import json
import logging
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any


# ==================== 数据结构 ====================
@dataclass
class SlideOutline:
    """
    单张幻灯片的大纲。

    字段：
      title    : 页面标题
      layout   : 版式 ID（对应 LAYOUTS 的键）
      bullets  : 要点列表
      notes    : 演讲备注（可选）
    """
    title: str = ""
    layout: str = "title_content"
    bullets: List[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SlideOutline":
        return cls(
            title=str(data.get("title", "")),
            layout=str(data.get("layout", "title_content")),
            bullets=list(data.get("bullets", [])),
            notes=str(data.get("notes", "")),
        )

    def to_markdown(self) -> str:
        """
        将大纲转为 Markdown 骨架。

        规则：
          - title_only : # 标题 + 副标题
          - title_content : # 标题 + 要点列表
          - two_column : # 标题 + 两栏 div
          - 其他 : # 标题 + 要点列表
        """
        if self.layout == "title_only":
            parts = [f"# {self.title}"]
            if self.bullets:
                parts.append(f"> {self.bullets[0]}")
            return "\n\n".join(parts) + "\n"

        if self.layout == "two_column" and len(self.bullets) >= 2:
            mid = len(self.bullets) // 2
            left = "\n".join(f"- {b}" for b in self.bullets[:mid])
            right = "\n".join(f"- {b}" for b in self.bullets[mid:])
            return (
                f"# {self.title}\n\n"
                f'<div class="columns">\n'
                f'<div class="column">\n\n{left}\n\n</div>\n'
                f'<div class="column">\n\n{right}\n\n</div>\n'
                f"</div>\n"
            )

        # 默认：标题 + 要点
        lines = [f"# {self.title}", ""]
        for b in self.bullets:
            lines.append(f"- {b}")
        return "\n".join(lines) + "\n"


# ==================== AI 服务 ====================
class BeeshowAIService:
    """蜜演 AI 服务"""

    # 上一次调用的结果来源（优化规划 §1.8）：
    #   "ai"    —— 真的由 LLM 生成
    #   "local" —— 降级到本地模板 / 未配置 Key
    #   "error" —— 调用失败
    #   "none"  —— 尚未调用
    # 之所以显式记录：原实现在失败后静默返回本地模板，调用方与用户都无法区分
    # "AI 生成的内容"和"占位大纲"，用户会把占位内容直接拿去演示。
    last_source: str = "none"

    # 支持的版式 ID 集合（供 LLM 约束输出）
    VALID_LAYOUTS = {
        "title_only", "title_content", "two_column",
        "three_column", "data_table", "image_caption",
        "quote", "timeline", "process", "summary",
        "ending", "blank",
    }

    # 默认 API 端点（OpenAI 兼容）
    DEFAULT_API_BASE = "https://api.deepseek.com/v1"

    # 超时（秒）
    DEFAULT_TIMEOUT = 30

    # 重试次数
    DEFAULT_RETRY = 2

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        :param config: 配置字典，可含：
            - api_key  : API 密钥
            - api_base : API 端点（默认 DeepSeek）
            - model    : 模型名（默认 deepseek-chat）
            - timeout  : 超时秒数
            - retry    : 重试次数
        """
        config = config or {}
        self.api_key = config.get("api_key", "")
        self.api_base = config.get("api_base", self.DEFAULT_API_BASE).rstrip("/")
        self.model = config.get("model", "deepseek-chat")
        self.timeout = int(config.get("timeout", self.DEFAULT_TIMEOUT))
        self.retry = int(config.get("retry", self.DEFAULT_RETRY))
        self.last_source = "none"

    def source_is_ai(self) -> bool:
        """上一次返回的内容是否真的来自 LLM。"""
        return self.last_source == "ai"

    def describe_last_source(self) -> str:
        """把 last_source 转成可直接展示给用户的中文说明。"""
        return {
            "ai": "AI 生成",
            "local": "本地模板（未调用 AI 或调用失败后降级）",
            "error": "AI 调用失败",
            "none": "未调用",
        }.get(self.last_source, self.last_source)

    # ==================== 公开接口 ====================
    def generate_outline(
        self,
        topic: str,
        audience: str = "普通听众",
        duration: int = 10,
        page_count: int = 8,
    ) -> List[SlideOutline]:
        """
        生成结构化演示大纲。

        :param topic: 演示主题
        :param audience: 目标受众
        :param duration: 演示时长（分钟）
        :param page_count: 期望页数
        :return: SlideOutline 列表

        流程：
          1. 无 API Key → 本地模板降级
          2. 构造 prompt（含 JSON Schema 约束）
          3. 调用 LLM，解析 JSON
          4. 失败时重试
        """
        if not topic or not topic.strip():
            return []

        if not self.api_key:
            self.last_source = "local"
            logging.warning(
                "未配置 AI API Key，改用本地模板大纲（非 AI 生成）"
            )
            return self._local_fallback_outline(
                topic, audience, duration, page_count
            )

        prompt = self._build_outline_prompt(
            topic, audience, duration, page_count
        )

        for attempt in range(self.retry + 1):
            try:
                raw = self._call_llm(prompt)
                outlines = self._parse_outline_json(raw)
                if outlines:
                    self.last_source = "ai"
                    logging.info(
                        f"AI 大纲生成成功：{len(outlines)} 页"
                        f"（第 {attempt + 1} 次尝试）"
                    )
                    return outlines
            except Exception as e:
                logging.warning(
                    f"AI 大纲生成失败（第 {attempt + 1} 次）：{e}"
                )

        self.last_source = "local"
        logging.warning(
            "AI 大纲生成多次失败，改用本地模板大纲（非 AI 生成）"
        )
        return self._local_fallback_outline(
            topic, audience, duration, page_count
        )

    def refine_outline(
        self,
        current: List[SlideOutline],
        instruction: str,
    ) -> List[SlideOutline]:
        """
        根据用户指令修改大纲（边聊边改）。

        :param current: 当前大纲
        :param instruction: 用户指令（如"第 3 页加一个数据对比"）
        :return: 修改后的新大纲

        实现：
          - 把当前大纲和指令发给 LLM
          - LLM 返回完整的新大纲 JSON
        """
        if not self.api_key:
            self.last_source = "local"
            logging.warning(
                "未配置 AI API Key，忽略 refactor 指令（大纲保持原样）"
            )
            return current

        prompt = self._build_refine_prompt(current, instruction)
        try:
            raw = self._call_llm(prompt)
            outlines = self._parse_outline_json(raw)
            if outlines:
                self.last_source = "ai"
                return outlines
        except Exception as e:
            logging.warning(f"AI 大纲修改失败：{e}")
        self.last_source = "error"
        return current

    def generate_notes(
        self,
        slide_title: str,
        slide_content: str,
        duration_sec: int = 30,
    ) -> str:
        """
        为单页生成演讲稿（任务 1.2 接口预留）。

        :param slide_title: 页面标题
        :param slide_content: 页面内容（Markdown 或纯文本）
        :param duration_sec: 期望演讲时长（秒）
        :return: 演讲稿文本
        """
        if not self.api_key:
            self.last_source = "local"
            return ""

        prompt = (
            f"请为以下幻灯片撰写 {duration_sec} 秒的中文演讲稿，"
            f"口语化、自然、可直接朗读。只输出演讲稿正文，不要任何前缀。\n\n"
            f"【标题】{slide_title}\n\n"
            f"【内容】\n{slide_content}\n"
        )
        try:
            text = self._call_llm(prompt).strip()
            self.last_source = "ai" if text else "error"
            return text
        except Exception as e:
            self.last_source = "error"
            logging.warning(f"生成演讲稿失败：{e}")
            return ""

    def suggest_images(
        self, slide_content: str, count: int = 3
    ) -> List[str]:
        """
        推荐配图（任务 1.3 接口预留）。

        当前返回空列表，等 1.3 实现时接入图库 API。
        """
        return []

    # ==================== 内部：Prompt 构造 ====================
    def _build_outline_prompt(
        self, topic: str, audience: str, duration: int, page_count: int
    ) -> str:
        """构造大纲生成的 prompt"""
        layouts_str = ", ".join(sorted(self.VALID_LAYOUTS))
        return f"""你是一个专业的演示文稿策划师。请为主题"{topic}"设计一份演示大纲。

【背景】
- 目标受众：{audience}
- 演示时长：{duration} 分钟
- 期望页数：{page_count} 页

【输出要求】
严格输出 JSON 数组，不要任何额外文字、不要 markdown 代码块标记。
数组每一项形如：
{{
  "title": "页面标题",
  "layout": "版式ID",
  "bullets": ["要点1", "要点2"],
  "notes": "演讲备注（可选）"
}}

【版式ID 可选值】
{layouts_str}

【版式建议】
- 第一页用 "title_only"
- 中间内容页用 "title_content" / "two_column" / "data_table"
- 最后一页用 "ending"

【内容要求】
- 每页标题简洁有力（10 字以内）
- 每页要点 2-5 条
- 逻辑连贯：背景 → 问题 → 方案 → 数据 → 总结

现在请生成 JSON 数组："""

    def _build_refine_prompt(
        self, current: List[SlideOutline], instruction: str
    ) -> str:
        """构造大纲修改的 prompt"""
        current_json = json.dumps(
            [s.to_dict() for s in current],
            ensure_ascii=False,
            indent=2,
        )
        layouts_str = ", ".join(sorted(self.VALID_LAYOUTS))
        return f"""你是一个专业的演示文稿策划师。以下是当前演示大纲：

{current_json}

用户的修改指令是：「{instruction}」

请根据指令修改大纲，保持其他页不变。严格输出完整的 JSON 数组
（不要只输出修改部分），不要任何额外文字。

版式ID 可选值：{layouts_str}

现在请输出修改后的完整 JSON 数组："""

    # ==================== 内部：LLM 调用 ====================
    def _call_llm(self, prompt: str) -> str:
        """
        调用 LLM（OpenAI 兼容 API）。

        :param prompt: 完整 prompt
        :return: LLM 返回的文本
        :raises: RuntimeError 当调用失败
        """
        url = f"{self.api_base}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 4000,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        # 优先用 requests，回退到 urllib
        try:
            import requests
            resp = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except ImportError:
            data = self._call_llm_urllib(url, headers, payload)

        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError(f"LLM 返回无 choices：{data}")
        return choices[0].get("message", {}).get("content", "")

    def _call_llm_urllib(
        self, url: str, headers: Dict[str, str], payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """用 urllib 调用 LLM（无 requests 时的回退）"""
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                req, timeout=self.timeout
            ) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTP {e.code}: {body[:200]}")

    # ==================== 内部：JSON 解析 ====================
    def _parse_outline_json(self, raw: str) -> List[SlideOutline]:
        """
        解析 LLM 返回的 JSON。

        容错：
          - 剥离可能的 ```json ... ``` 包裹
          - 剥离可能的前后说明文字
          - 校验 layout 是否在 VALID_LAYOUTS 内
        """
        if not raw:
            return []

        text = raw.strip()

        # 剥离 markdown 代码块
        if text.startswith("```"):
            lines = text.split("\n")
            # 去掉首尾 ```
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        # 剥离前后说明文字，只保留 [...] 部分
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            text = text[start:end + 1]

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 解析失败：{e}")

        if not isinstance(data, list):
            raise ValueError("LLM 输出不是 JSON 数组")

        outlines = []
        for item in data:
            if not isinstance(item, dict):
                continue
            outline = SlideOutline.from_dict(item)
            # 校验 layout
            if outline.layout not in self.VALID_LAYOUTS:
                outline.layout = "title_content"
            # 校验必填
            if not outline.title and not outline.bullets:
                continue
            outlines.append(outline)
        return outlines

    # ==================== 内部：本地降级 ====================
    def _local_fallback_outline(
        self, topic: str, audience: str, duration: int, page_count: int
    ) -> List[SlideOutline]:
        """
        无 API Key 时的本地模板降级。

        生成一份基础大纲：封面 → 背景 → 核心内容 → 总结 → 结束。
        结构与 AI 输出保持一致，便于上层统一处理。
        """
        topic = topic.strip()
        return [
            SlideOutline(
                title=topic,
                layout="title_only",
                bullets=[f"{audience} · {duration} 分钟"],
                notes="",
            ),
            SlideOutline(
                title="背景",
                layout="title_content",
                bullets=["背景1", "背景2", "背景3"],
                notes="介绍主题的背景和意义",
            ),
            SlideOutline(
                title="核心内容",
                layout="title_content",
                bullets=["要点1", "要点2", "要点3"],
                notes="详细讲解核心内容",
            ),
            SlideOutline(
                title="数据支撑",
                layout="data_table",
                bullets=[],
                notes="用数据支撑观点",
            ),
            SlideOutline(
                title="总结",
                layout="summary",
                bullets=["回顾要点1", "回顾要点2", "下一步行动"],
                notes="总结并给出行动建议",
            ),
            SlideOutline(
                title="感谢聆听",
                layout="ending",
                bullets=[],
                notes="",
            ),
        ]


# ==================== 模块级便捷函数 ====================
def create_service_from_settings() -> BeeshowAIService:
    """
    从 AppSettings 创建服务实例。

    读取：
      - settings.ai_api_key
      - settings.ai_api_base（可选）
      - settings.ai_model（可选）
    """
    try:
        from beeoffice.settings import AppSettings
        settings = AppSettings()
        config = {
            "api_key": getattr(settings, "ai_api_key", "") or "",
            "api_base": getattr(settings, "ai_api_base", "")
                or BeeshowAIService.DEFAULT_API_BASE,
            "model": getattr(settings, "ai_model", "")
                or "deepseek-chat",
        }
        return BeeshowAIService(config)
    except Exception as e:
        logging.error(f"创建 AI 服务失败：{e}")
        return BeeshowAIService()