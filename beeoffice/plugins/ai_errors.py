# beeoffice/plugins/ai_errors.py
"""
把 AI 调用的失败**翻译成用户能照着修的一句话**（**唯一的**一处实现）。

## 为什么要独立成模块（真实用户反馈驱动）
用户在真机截图里看到的是：

    ❌ 接口地址不对（HTTP 404）。地址应指向兼容 OpenAI 的端点…

但他填的 `http://localhost:11434/v1` **完全正确**，
真正的原因是 **Ollama 说"这个模型不存在"**（模型名填了 `qwen2.5`、没有 tag，
而 Ollama 对未知模型就是返回 **HTTP 404** + body
`{"error":"model \"qwen2.5\" not found, try pulling it first"}`）。
**提示把用户引到了错误方向**，他会去反复改地址，永远修不好。

为什么会这样？两条同时成立：
1. 主传输层用 `requests`，`raise_for_status()` 抛出的异常
   **字符串里不含响应体**（`404 Client Error: Not Found for url: ...`）→
   代码看不到 `"model ... not found"` 这几个字；
2. 仓库里对 404 有**两套不同口径**的文案（一套说"地址不对"，一套说
   "地址或模型名都可能"）—— 用户撞上的是较差的那套。

所以本模块：**内容来自响应体**（不再只看状态码），且**只有一份实现**，
`beeshow_ai_service`（设置界面「测试连接」）与 `ai_client`（蜜写 AI）都调用它。

## 设计要点
* 纯函数、无网络、无 Qt 依赖 → 可以对着"真实报错文本"做表驱动测试；
* **按证据说话**：能从 body 断定是"模型不存在"就直说，并且给出
  **可以照抄的命令**（`ollama pull …`）；断不定就把两种可能都列出来，
  不赌一个方向。
"""
from typing import Optional

#: body 里出现这些片段 → 判定为"模型名在该服务上不存在"
_MODEL_MISSING_HINTS = (
    "not found, try pulling",
    "try pulling it first",
    "no such model",
    "model not found",
    "model does not exist",
    "unknown model",
    "invalid model",
)

#: body 里出现这些片段 → 说明请求打到了**不是 API 端点**的地方
_NOT_A_ROUTE_HINTS = (
    "404 page not found",
    "page not found",
    "cannot post",
    "no route",
)


def _has_status(text: str, code: int) -> bool:
    """
    判断错误文本里是否出现了**状态码**（而不是碰巧包含这几个数字）。

    ⚠️ 实测坑：原先直接 `"404" in text` —— 于是 `localhost:4040` 的**拒连**
    也会被当成 HTTP 404（还把用户引向"地址不对"）。改成按数字边界匹配。
    """
    import re

    return re.search(rf"(?<!\d){code}(?!\d)", text or "") is not None


def _looks_like_model_missing(body: str, status: Optional[int]) -> bool:
    lowered = (body or "").lower()
    if any(hint in lowered for hint in _MODEL_MISSING_HINTS):
        return True
    # Ollama 的原始报错是 `model "x" not found`（没有 "try pulling" 的变体）
    return status == 404 and "model" in lowered and "not found" in lowered


def _suggest_pull(model: str) -> str:
    """给出可照抄的 `ollama pull` 命令；模型名没带 tag 时明确提醒补 tag。"""
    name = (model or "").strip() or "你的模型名"
    if ":" in name:
        return f"ollama pull {name}"
    return f"ollama pull {name}（注意要带 tag，例如 {name}:7b）"


def explain_ai_error(
    *,
    status: Optional[int] = None,
    body: str = "",
    error_text: str = "",
    api_base: str = "",
    model: str = "",
    is_local: bool = False,
) -> str:
    """
    把一次失败的调用翻译成**可操作**的一句话。

    :param status: HTTP 状态码（拿不到就 None）
    :param body: **响应体原文**（关键：404 的真实原因在这里）
    :param error_text: 异常/错误原文（用于识别超时、拒连等非 HTTP 失败）
    :param api_base: 接口地址（提示里回显给用户）
    :param model: 模型名（用于给出 `ollama pull` 命令）
    :param is_local: 是否指向本机（localhost/127.0.0.1）
    """
    text = str(error_text or "")
    lowered = text.lower()
    combined = f"{text}\n{body or ''}".lower()
    local = bool(is_local) or "localhost" in (api_base or "").lower() \
        or "127.0.0.1" in (api_base or "")

    # ---------- 401 / 403：Key 或权限 ----------
    if status in (401, 403) or _has_status(text, 401) \
            or _has_status(text, 403) or "unauthorized" in combined:
        if local:
            return ("本地服务拒绝了请求（HTTP 401/403）。"
                    "Ollama 一般不需要 Key，请把『API Key』留空重试。")
        return ("API Key 无效或没有权限（HTTP 401/403）："
                "请检查 Key 是否填对、账户是否有余额。")

    # ---------- 404：**先看响应体**再下结论 ----------
    if status == 404 or _has_status(text, 404):
        if _looks_like_model_missing(body, status):
            return (
                f"模型「{model or '（未填）'}」在该服务上不存在（HTTP 404）。\n"
                f"• 先拉取模型：{_suggest_pull(model)}\n"
                f"• 再用 `ollama list` 确认名字与 tag 完全一致后重试"
                if local else
                f"模型「{model or '（未填）'}」在该服务上不存在（HTTP 404）。\n"
                f"• 请核对『模型名』与服务商文档一致（大小写/tag 都要对）"
            )
        if any(hint in (body or "").lower() for hint in _NOT_A_ROUTE_HINTS):
            return ("接口地址不对（HTTP 404，服务回了『page not found』）。"
                    f"当前地址：{api_base or '（空）'}\n"
                    "• 地址应指向兼容 OpenAI 的端点，通常以 /v1 结尾；\n"
                    "• Ollama 的正确写法是 http://localhost:11434/v1"
                    if local else
                    "接口地址不对（HTTP 404，服务回了『page not found』）。\n"
                    "• 地址应指向兼容 OpenAI 的端点，通常以 /v1 结尾，"
                    "例如 https://api.deepseek.com/v1")
        # 没有任何 body 线索：**两种可能都列出来，不赌**
        return ("服务返回 404，两种原因都可能：\n"
                "• **接口地址**是否指向兼容 OpenAI 的端点（通常以 /v1 结尾）；\n"
                f"• **模型名**在该服务上是否存在"
                + (f"（本地建议 `ollama list` 核对；{_suggest_pull(model)}）"
                   if local else ""))

    # ---------- 429：限流/额度 ----------
    if status == 429 or _has_status(text, 429):
        return "请求太频繁或额度用尽（HTTP 429）：稍后再试，或检查账户余额。"

    # ---------- 连不上本地服务 ----------
    refused = "connection" in lowered or "refused" in lowered \
        or "拒绝" in text or "无法连接" in text
    if local and (refused or "timed out" in lowered or "timeout" in lowered):
        return (f"连不上本地服务（{api_base or '本机'}）。\n"
                "• 确认已运行 `ollama serve`；\n"
                f"• 确认模型已拉取：{_suggest_pull(model)}")

    if "timed out" in lowered or "timeout" in lowered:
        return (f"连接超时（{api_base or '接口地址'}）。"
                "本地模型首次调用要加载权重、可能 20–60 秒，可稍后重试；"
                "或改用本地 Ollama。")

    if "name or service not known" in lowered or "getaddrinfo" in lowered \
            or "nodename" in lowered:
        return f"域名解析失败（{api_base or '接口地址'}）：请检查地址是否写错。"

    # ---------- 兜底：把原文带上，别吞掉 ----------
    detail = (text or body or "").strip()[:160]
    return f"调用失败：{detail}" if detail else "调用失败（没有更多信息）"
