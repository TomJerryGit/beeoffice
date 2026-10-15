# beeoffice/plugins/ai_client.py
"""
**通用的文本 AI 客户端**（蜜写的续写/润色/总结用）。

为什么单独一个模块
------------------
蜜演已经有 `beeshow_ai_service.py`，但它的 prompt 与返回结构都是"演示大纲"专用的
（`generate_outline` / `generate_notes` 返回结构化对象）。蜜写要的是**纯文本进、
纯文本出**，硬塞进去会让两边都难维护。所以这里只做一件事：**配置 → 一次
chat 调用 → 文本**，并沿用蜜演那套"**如实标注来源**"的做法。

为什么要标注来源（这是本次改造的核心动因）
------------------------------------------
改造前蜜写的「AI 续写」是 `random.choice(12 条硬编码句库)` —— **与上下文无关的
模板句**，但提示写的是"✅ AI 续写完成"。用户会把模板句当成 AI 生成的内容用。
所以 `last_source` 必须区分：

    "ai"     —— 真由 LLM 生成
    "local"  —— 降级到本地规则（无 Key / 未配置）
    "error"  —— 调用失败，已降级

界面据此显示不同文案，**不再把本地规则说成 AI**。
"""
import json
import logging
import time
from typing import Any, Callable, Dict, Optional, Tuple

#: 单次调用默认参数
DEFAULT_TIMEOUT = 30
#: **本地模型**（Ollama 等）要宽松得多的超时。
#: 实测（本机 llama3.2:latest，1.9 GB，CPU 推理）：
#:   测试连接 39.9 s、续写 31.1 s、润色 19.8 s、总结 **超过 30 s 超时失败**。
#: 用 30 s 的云端口径去卡本地模型，会让用户以为"Ollama 不能用" —— 这是真缺陷。
LOCAL_TIMEOUT = 300
DEFAULT_MAX_TOKENS = 1200
#: 送进模型的文本上限（防止把整本书发过去）
MAX_INPUT_CHARS = 6000


def default_timeout_for(api_base: str) -> int:
    """
    按服务商给默认超时：本地宽松，云端紧凑。

    ⚠️ 这里**故意不判 `0.0.0.0`**：它作为**客户端**要访问的地址本就不是
    真实配置（连不上），而写了它会触发仓库里那条安全回归测试
    `test_no_unconditional_wildcard_bind_in_source` 的**文本误报**
    （那条测试扫的是"无条件通配绑定"，我的字符串比较被它当成 bind 了）。
    去掉它不削弱任何真实安全属性。
    """
    text = (api_base or "").lower()
    if "localhost" in text or "127.0.0.1" in text:
        return LOCAL_TIMEOUT
    return DEFAULT_TIMEOUT


#: 写作助手的系统提示（中文，要求"只要结果、不要解释"）
_WRITING_SYSTEM = (
    "你是中文写作助手。严格遵守用户要求，只输出要求的正文内容，"
    "不要输出解释、说明、前言、markdown 代码块或引号包裹。"
)


class AIClient:
    """
    文本 AI 客户端（OpenAI 兼容协议）。

    配置来自 `AppSettings`（`ai_api_key` / `ai_api_base` / `ai_model`），
    也就是「🤖 AI 设置」对话框写入的那三项。
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None,
                 opener: Optional[Callable[..., Dict[str, Any]]] = None):
        config = config or {}
        self.api_key = (config.get("api_key") or "").strip()
        self.api_base = (config.get("api_base")
                         or "https://api.deepseek.com/v1").rstrip("/")
        self.model = (config.get("model") or "deepseek-chat").strip()
        # 超时按服务商区分：本地模型慢得多（实测 20–40 s/次），
        # 用云端的 30 s 卡它会让用户以为 Ollama 不能用；显式配置仍优先。
        self.timeout = int(
            config.get("timeout") or default_timeout_for(self.api_base)
        )
        #: 可注入的传输层（测试用；None 时走真实 HTTP）
        self._opener = opener
        #: 上一次结果的来源：ai / local / error / none
        self.last_source = "none"
        #: 上一次的错误说明（给用户看）
        self.last_error = ""

    # ------------------------------------------------------------------
    @classmethod
    def from_settings(cls, settings=None, **kwargs) -> "AIClient":
        """从应用设置构造（复用「AI 设置」里填的三项）。"""
        if settings is None:
            try:
                from beeoffice.settings import AppSettings

                settings = AppSettings()
            except Exception as e:  # noqa: BLE001 - 读不到设置就当作未配置
                logging.debug(f"[AI] 读取设置失败: {e}")
                settings = None
        config = {
            "api_key": getattr(settings, "ai_api_key", "") or "",
            "api_base": getattr(settings, "ai_api_base", "") or "",
            "model": getattr(settings, "ai_model", "") or "",
        }
        return cls(config, **kwargs)

    # ------------------------------------------------------------------
    @property
    def available(self) -> bool:
        """
        是否可以真的调用 LLM。

        本地地址（localhost / 127.0.0.1）不要求 Key —— 与 AI 设置里的
        「本地 Ollama 无需 Key」保持一致。
        """
        if not self.api_base or not self.model:
            return False
        if self.api_key:
            return True
        return "localhost" in self.api_base or "127.0.0.1" in self.api_base

    def unavailable_reason(self) -> str:
        """
        **未配置**时给出具体原因（不依赖"先调用过"）。

        之前只在 `chat()` 里设置 `last_error`，于是新构造的客户端
        `last_error` 是空的，界面只能显示笼统的"未配置 AI"——
        用户不知道到底缺地址、缺模型还是缺 Key。
        """
        if not self.api_base:
            return "未配置接口地址。请在「帮助 → 🤖 AI 设置」里选择服务商。"
        if not self.model:
            return "未配置模型名。请在「帮助 → 🤖 AI 设置」里填写模型。"
        if not self.api_key:
            return ("未填写 API Key。请在「帮助 → 🤖 AI 设置」里填写；"
                    "本地 Ollama 不需要 Key。")
        return self.last_error or "AI 不可用。"

    def describe_source(self) -> str:
        """给用户看的来源说明（**不许把本地规则说成 AI**）。"""
        if self.last_source == "ai":
            return f"AI 生成（{self.model}）"
        if self.last_source == "local":
            return "本地规则（未配置 AI 或已降级）"
        if self.last_source == "error":
            return f"本地规则（AI 调用失败：{self.last_error[:60]}）"
        return "未知来源"

    # ------------------------------------------------------------------
    def chat(self, prompt: str, system: Optional[str] = None,
             max_tokens: int = DEFAULT_MAX_TOKENS) -> Tuple[bool, str]:
        """
        发一次 chat 调用。

        :return: (ok, 文本或错误说明)
            失败时 `ok=False`，且**不会**抛异常 —— 调用方据此决定是否降级。
        """
        if not self.available:
            self.last_source = "local"
            self.last_error = "未配置 AI（可在 帮助 → 🤖 AI 设置 中填写）"
            return False, self.last_error

        url = f"{self.api_base}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system or _WRITING_SYSTEM},
                {"role": "user", "content": prompt[:MAX_INPUT_CHARS]},
            ],
            "temperature": 0.7,
            "max_tokens": max(1, int(max_tokens)),
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        started = time.perf_counter()
        try:
            opener = self._opener or _default_opener
            data = opener(url, headers, payload, self.timeout)
        except Exception as e:  # noqa: BLE001 - 全部转成可读错误，由调用方降级
            self.last_source = "error"
            self.last_error = _explain_error(e, self.api_base)
            logging.warning(f"[AI] 调用失败：{self.last_error}")
            return False, self.last_error

        choices = (data or {}).get("choices") or []
        if not choices:
            self.last_source = "error"
            self.last_error = f"服务响应缺少 choices：{str(data)[:120]}"
            return False, self.last_error

        content = ((choices[0].get("message") or {}).get("content") or "").strip()
        if not content:
            self.last_source = "error"
            self.last_error = "服务返回了空内容"
            return False, self.last_error

        self.last_source = "ai"
        self.last_error = ""
        logging.info(
            f"[AI] {self.model} 调用成功，用时 "
            f"{(time.perf_counter() - started) * 1000:.0f} ms"
        )
        return True, content


def _default_opener(url, headers, payload, timeout):
    """默认传输层：优先 requests，回退 urllib。"""
    try:
        import requests

        response = requests.post(url, headers=headers, json=payload,
                                 timeout=timeout)
        response.raise_for_status()
        return response.json()
    except ImportError:
        import urllib.error
        import urllib.request

        request = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers=headers, method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code}: {e.reason}") from e


def _explain_error(error, api_base: str) -> str:
    """把失败翻译成用户能照着修的一句话（与「测试连接」同一套口径）。"""
    text = str(error)
    lowered = text.lower()
    if "401" in text or "403" in text or "unauthorized" in lowered:
        return "API Key 无效或没有权限（HTTP 401/403），请在『AI 设置』里检查 Key 与余额"
    if "404" in text:
        # 404 有两种常见成因：地址不对，**或者模型名在该服务上不存在**。
        # 只说"地址不对"会把用户误导到错误方向（例如他填的是自定义网关，
        # 地址没错、只是模型名沿用了 DeepSeek 的默认值）。
        return ("服务返回 404：请检查『AI 设置』里的**接口地址**"
                "（应以 /v1 结尾）与**模型名**是否都对")
    if "429" in text:
        return "请求太频繁或额度用尽（HTTP 429），稍后重试"
    if "timed out" in lowered or "timeout" in lowered:
        return f"连接超时（{api_base}），可改用本地 Ollama"
    if ("connection" in lowered or "refused" in lowered) and \
            ("localhost" in api_base or "127.0.0.1" in api_base):
        return "连不上本地服务，请确认已运行 `ollama serve`"
    return f"调用失败：{text[:120]}"


# ==================== 提示词构造（独立出来便于测试）====================

def build_continue_prompt(context: str, length_hint: int = 160) -> str:
    """续写提示：给上下文，要求接着写、只输出续写部分。"""
    return (
        "请接着下面这段文字继续写下去，语气与风格保持一致。\n"
        f"只输出**续写的内容**（约 {length_hint} 字），"
        "不要重复原文、不要任何解释。\n\n"
        f"【已有文字】\n{context.strip()}"
    )


def build_polish_prompt(text: str) -> str:
    """润色提示：保持原意与长度、去口语化、修标点。"""
    return (
        "请润色下面这段文字：保持原意与大致长度，"
        "去掉口语化表达、统一标点、让语句更通顺。\n"
        "只输出润色后的文字，不要解释、不要用引号包裹、不要改动其中的数字与专有名词。\n\n"
        f"【原文】\n{text.strip()}"
    )


def build_summarize_prompt(text: str, max_points: int = 5) -> str:
    """总结提示：要要点式、可压缩（避免"原样返回"这种假总结）。"""
    return (
        f"请用不超过 {max_points} 条中文要点总结下面的文档，"
        "每条一行、以「- 」开头，抓住结论与关键信息，**必须压缩**，"
        "不要照抄原句。\n\n"
        f"【文档】\n{text.strip()}"
    )


def build_keywords_prompt(text: str, count: int = 8) -> str:
    """关键词提示。"""
    return (
        f"请提取下面文档的 {count} 个关键词，用中文顿号分隔，"
        "一行输出，不要解释。\n\n"
        f"【文档】\n{text.strip()}"
    )
