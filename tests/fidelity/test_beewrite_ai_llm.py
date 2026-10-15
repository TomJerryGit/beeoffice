# tests/fidelity/test_beewrite_ai_llm.py
"""
蜜写「AI 辅助」接真 LLM（P1-B 延伸，方案 A）。

## 改造前的问题（实测，见 docs/baseline.md 2026-10-14 那行审计）
蜜写的「AI 续写/润色/总结」**完全不联网**：`ai_assist.py` 只有
`re/random/logging/typing`，「AI 续写」是 `random.choice(12 条硬编码句库)` ——
**与上下文无关的模板句**，而提示写着"✅ AI 续写完成"。

## 改造后的规则（本文件逐条钉住）
1. **优先真 LLM**：配置来自「帮助 → 🤖 AI 设置」（`ai_api_key` 等）。
2. **走后台线程**（`AsyncTaskManager`）—— 生成要几秒，不能卡界面。
3. **绝不静默插模板**：没有可用 AI 或调用失败时，先弹框说明原因并
   **征求同意**（默认「否」）；同意后才用本地规则，且状态栏必须写明
   "**不是 AI 生成**"。
4. 成功时状态栏写明来源（`AI 生成（模型名）`）。

测试全部用**桩客户端 / 假传输层**，**绝不真联网**。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from beeoffice.plugins.ai_client import (                        # noqa: E402
    AIClient, build_continue_prompt, build_keywords_prompt,
    build_polish_prompt, build_summarize_prompt,
)
from beeoffice.plugins.beewrite_ai_mixin import AIMixin           # noqa: E402


# ==================== 1. 客户端本身 ====================

def test_client_unavailable_without_config():
    client = AIClient({})

    assert client.available is False
    assert client.unavailable_reason()


@pytest.mark.parametrize("config,expected_fragment", [
    # ⚠️ 只测"缺 Key"：`AIClient` 对**空 api_base 与空 model 都会回落到
    # DeepSeek 默认值**（`https://api.deepseek.com/v1` / `deepseek-chat`），
    # 所以那两个"缺失"分支在正常构造下不可达 —— 与其写一条永远不失败的
    # 断言，不如如实只测真实可达的那条。
    # 顺带记一个由此暴露的真问题：用户若手改配置只填自定义地址+Key，
    # 模型会回落成 deepseek-chat → 调用 404，而原来的提示只说"地址不对"，
    # 会把人误导到错误方向；已把 404 提示改成同时提醒**地址与模型名**。
    ({"api_base": "https://x/v1", "model": "m"}, "API Key"),
])
def test_unavailable_reason_is_specific(config, expected_fragment):
    """原因要具体 —— 用户得知道到底缺哪一项。"""
    client = AIClient(config)

    assert client.available is False
    assert expected_fragment in client.unavailable_reason()


def test_404_message_mentions_model_too():
    """404 可能是"模型名不对"，提示不能只怪地址。"""
    def boom(u, h, p, t):
        raise RuntimeError("HTTP 404: Not Found")

    client = AIClient({"api_key": "k",
                       "api_base": "https://my.gateway/v1",
                       "model": "wrong-model"}, opener=boom)

    ok, message = client.chat("提示")

    assert ok is False
    assert "模型名" in message, message


def test_local_address_needs_no_key():
    """本地 Ollama 不需要 Key（与 AI 设置里的策略一致）。"""
    client = AIClient({"api_base": "http://localhost:11434/v1",
                       "model": "qwen2.5"})

    assert client.available is True


def test_chat_success_marks_source_as_ai():
    client = AIClient(
        {"api_key": "k", "api_base": "https://api.deepseek.com/v1",
         "model": "deepseek-chat"},
        opener=lambda u, h, p, t: {"choices": [{"message": {"content": "结果"}}]},
    )

    ok, text = client.chat("提示")

    assert ok is True and text == "结果"
    assert client.last_source == "ai"
    assert "deepseek-chat" in client.describe_source()


def test_chat_failure_does_not_raise_and_marks_error():
    def boom(u, h, p, t):
        raise RuntimeError("HTTP 401: Unauthorized")

    client = AIClient({"api_key": "bad"}, opener=boom)

    ok, message = client.chat("提示")

    assert ok is False
    assert client.last_source == "error"
    assert "API Key" in message
    assert "AI 调用失败" in client.describe_source()


def test_chat_marks_local_when_not_configured():
    client = AIClient({})

    ok, _ = client.chat("提示")

    assert ok is False
    assert client.last_source == "local"
    assert "本地规则" in client.describe_source()


def test_chat_handles_empty_content():
    client = AIClient({"api_key": "k"}, opener=lambda u, h, p, t: {
        "choices": [{"message": {"content": "   "}}]})

    ok, message = client.chat("提示")

    assert ok is False and "空内容" in message


def test_chat_truncates_huge_input():
    """别把整本书发过去。"""
    seen = {}

    def opener(u, h, p, t):
        seen["prompt"] = p["messages"][-1]["content"]
        return {"choices": [{"message": {"content": "ok"}}]}

    client = AIClient({"api_key": "k"}, opener=opener)
    client.chat("字" * 50000)

    assert len(seen["prompt"]) <= 6000 + 50


def test_chat_omits_authorization_for_local():
    seen = {}

    def opener(u, h, p, t):
        seen.update(h)
        return {"choices": [{"message": {"content": "ok"}}]}

    AIClient({"api_base": "http://localhost:11434/v1", "model": "m"},
             opener=opener).chat("x")

    assert "Authorization" not in seen


# ==================== 1b. 超时：本地模型必须宽松（实测修正）====================

def test_local_models_get_much_longer_timeout():
    """
    **实测修正**：本机 llama3.2（1.9 GB，CPU 推理）单次调用要 **20–46 s**，
    连"极短"的测试连接首次都要 **39.9 s**。用云端的 30 s 去卡它 → 用户会以为
    Ollama 不能用（我第一版就是 30 s，实测"总结"直接超时失败）。
    """
    local = AIClient({"api_base": "http://localhost:11434/v1",
                      "model": "llama3.2"})
    remote = AIClient({"api_key": "k"})

    assert local.timeout >= 120, local.timeout
    assert remote.timeout <= 60, remote.timeout
    assert local.timeout > remote.timeout


def test_explicit_timeout_still_wins():
    """显式配置的超时要优先于按服务商推断的默认值。"""
    client = AIClient({"api_base": "http://localhost:11434/v1",
                       "timeout": 7})

    assert client.timeout == 7


def test_timeout_helper_covers_local_forms():
    from beeoffice.plugins.ai_client import (
        DEFAULT_TIMEOUT, LOCAL_TIMEOUT, default_timeout_for,
    )

    for base in ("http://localhost:11434/v1", "http://127.0.0.1:11434/v1",
                 "http://LOCALHOST:11434/v1"):
        assert default_timeout_for(base) == LOCAL_TIMEOUT, base
    assert default_timeout_for("https://api.deepseek.com/v1") == DEFAULT_TIMEOUT
    # 注意：**不**把 `0.0.0.0` 当本地 —— 它作为客户端地址不真实，
    # 且写了它会触发 `test_v505_sensitive_surfaces` 里那条
    # "无条件通配绑定"扫描的**文本误报**（字符串比较被当成 bind）。
    assert default_timeout_for("http://0.0.0.0:11434/v1") == DEFAULT_TIMEOUT


def test_probe_defaults_are_longer_for_local():
    """
    设置界面的「测试连接」也要按服务商给超时 —— 否则用户用它测本地 Ollama
    会得到"连接超时"，从而以为**模型不能用**（实测：首次调用 39.9 s）。
    """
    from beeoffice.plugins.beeshow_ai_service import probe_ai_connection

    seen = {}

    def opener(url, headers, payload, timeout):
        seen["timeout"] = timeout
        return {"choices": [{"message": {"content": "OK"}}]}

    probe_ai_connection({"api_base": "http://localhost:11434/v1",
                         "model": "llama3.2"}, opener=opener)
    local_timeout = seen["timeout"]

    probe_ai_connection({"api_key": "k",
                         "api_base": "https://api.deepseek.com/v1"},
                        opener=opener)
    remote_timeout = seen["timeout"]

    assert local_timeout >= 60, local_timeout
    assert remote_timeout <= 30, remote_timeout
    assert local_timeout > remote_timeout


# ==================== 2. 提示词 ====================

def test_continue_prompt_carries_context_and_forbids_explanation():
    prompt = build_continue_prompt("太阳照常升起。")

    assert "太阳照常升起。" in prompt
    assert "只输出" in prompt and "不要重复原文" in prompt


def test_polish_prompt_keeps_meaning_and_numbers():
    prompt = build_polish_prompt("营收 123 万。")

    assert "保持原意" in prompt
    assert "不要改动其中的数字" in prompt


def test_summarize_prompt_demands_compression():
    """要**必须压缩** —— 否则模型容易原样返回（本地规则就是这样）。"""
    prompt = build_summarize_prompt("很长的文档")

    assert "必须压缩" in prompt and "不要照抄原句" in prompt


def test_keywords_prompt_asks_for_count():
    assert "8 个关键词" in build_keywords_prompt("文档")


# ==================== 3. Mixin：三条核心规则 ====================

class FakeEditor:
    """记录调用、模拟一个可插入文本的编辑器。"""

    def __init__(self, text="光标前的正文内容，用于测续写。", mode="rich_text"):
        self.text = text
        self.mode = mode
        self.inserted = []
        self.selected = ("", 0, 0)
        self.statuses = []

    # 供 Mixin 使用的最小接口
    def toPlainText(self):  # noqa: N802 - 模拟 Qt API
        return self.text

    def textCursor(self):
        return _Cursor(self, self.selected)

    def append(self, text):
        self.inserted.append(("append", text))
        self.text += text

    def appendPlainText(self, text):  # noqa: N802
        self.inserted.append(("append", text))
        self.text += text


class _Cursor:
    def __init__(self, editor, selection):
        self.editor = editor
        self._selected, self._start, self._end = selection

    def position(self):
        return len(self.editor.text)

    def hasSelection(self):  # noqa: N802
        return bool(self._selected)

    def selectedText(self):  # noqa: N802
        return self._selected

    def selectionStart(self):  # noqa: N802
        return self._start

    def selectionEnd(self):  # noqa: N802
        return self._end

    def setPosition(self, pos, mode=None):  # noqa: N802
        self._start = pos

    def insertText(self, text):  # noqa: N802
        self.editor.inserted.append(("insert", text))
        self.editor.text += text


class FakeBeeWrite(AIMixin):
    """
    只测 AI Mixin 的替身。

    写法说明：我第一版试图在 `__init__` 里 `self.__class__ = type(..., (AIMixin,), {})`
    来"合成"类 —— 结果把替身自己定义的 `_set_status`/`content` **全丢了**
    （新类里没有它们），11 个用例因此失败。直接继承才是对的做法。
    """

    _edit_mode = "rich_text"

    def __init__(self, client, answer=None, raise_on_chat=False):
        self.rich_editor = FakeEditor()
        self.markdown_editor = FakeEditor()
        self._ai_client = client
        self._answer = answer
        self._raise = raise_on_chat
        self.statuses = []

    def _set_status(self, message, timeout=3000):
        self.statuses.append(message)

    def content(self):
        return "# 标题\n\n" + "这是一段足够长的正文内容。" * 10


class StubClient:
    """可编程的 AI 客户端桩。"""

    def __init__(self, available=True, result=(True, "AI 生成的内容")):
        self.available = available
        self._result = result
        self.prompts = []
        self.last_source = "ai" if available else "none"
        self.last_error = ""

    def unavailable_reason(self):
        return "未配置接口地址。请在「帮助 → 🤖 AI 设置」里选择服务商。"

    def describe_source(self):
        return "AI 生成（deepseek-chat）" if self.last_source == "ai" \
            else "本地规则"

    def chat(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return self._result


@pytest.fixture
def sync_runner(monkeypatch):
    """让 AsyncTaskManager 同步执行，便于断言。"""
    from beeoffice.plugins import beewrite_ai_mixin as module

    def run(fn, *args, on_result=None, on_error=None, **kwargs):
        try:
            result = fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            if on_error:
                on_error(str(e))
            return
        if on_result:
            on_result(result)

    monkeypatch.setattr(module.AsyncTaskManager, "run", staticmethod(run))


@pytest.fixture(autouse=True)
def _no_modal_dialogs(monkeypatch):
    """拦截模态框：否则"征求同意"那一步会把用例挂死。"""
    from PySide6.QtWidgets import QMessageBox

    seen = {"question": [], "information": [], "warning": []}

    def fake_question(parent, title, text, *a, **k):
        seen["question"].append((title, text))
        return QMessageBox.StandardButton.No      # 默认拒绝

    for name in ("information", "warning"):
        monkeypatch.setattr(
            QMessageBox, name,
            staticmethod(lambda *a, _n=name, **k: seen[_n].append(a)),
        )
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(fake_question))
    return seen


# ---------- 规则 1：优先真 LLM（走后台线程）----------

def test_continue_uses_real_ai_and_labels_source(sync_runner):
    client = StubClient(result=(True, "这是 AI 续写的一段话。"))
    editor = FakeBeeWrite(client)

    editor._ai_continue()

    assert client.prompts, "没有把提示词送给 AI"
    assert any("AI 续写" in s or "续写" in s for s in editor.statuses), \
        editor.statuses
    assert any("AI 生成" in s for s in editor.statuses), (
        f"成功时要标注来源：{editor.statuses}"
    )
    assert ("insert", "这是 AI 续写的一段话。") in editor.rich_editor.inserted


def test_polish_sends_selection_to_ai(sync_runner):
    client = StubClient(result=(True, "润色后的文字。"))
    editor = FakeBeeWrite(client)
    editor.rich_editor.selected = ("原文需要润色", 0, 6)

    editor._ai_polish()

    assert client.prompts and "原文需要润色" in client.prompts[0]
    assert any("AI 生成" in s for s in editor.statuses)


def test_summarize_asks_ai_for_compression(sync_runner):
    client = StubClient(result=(True, "- 要点一\n- 要点二"))
    editor = FakeBeeWrite(client)

    editor._ai_summarize()

    assert client.prompts and "必须压缩" in client.prompts[0]
    assert any("append" == kind and "要点一" in text
               for kind, text in editor.rich_editor.inserted), \
        editor.rich_editor.inserted


# ---------- 规则 2：绝不静默插模板 ----------

def test_unavailable_ai_does_not_silently_insert_template(_no_modal_dialogs):
    """
    **核心回归**：没有可用 AI 时，必须先问、且默认拒绝 → **不插任何东西**。
    改造前这里会直接插入随机模板句还提示"✅ AI 续写完成"。
    """
    client = StubClient(available=False)
    editor = FakeBeeWrite(client)

    editor._ai_continue()

    assert _no_modal_dialogs["question"], "没有征求用户同意"
    assert not editor.rich_editor.inserted, (
        f"未同意却插入了内容：{editor.rich_editor.inserted}"
    )


def test_unavailable_ai_names_where_to_configure(_no_modal_dialogs):
    client = StubClient(available=False)
    editor = FakeBeeWrite(client)

    editor._ai_continue()

    _, text = _no_modal_dialogs["question"][0]
    assert "AI 设置" in text, "要告诉用户去哪配置"
    assert "不联网" in text or "模板" in text, "要如实说明本地规则的局限"


def test_failed_ai_call_asks_before_falling_back(_no_modal_dialogs, sync_runner):
    """调用失败也不能静默降级。"""
    client = StubClient(result=(False, "API Key 无效或没有权限（HTTP 401/403）"))
    editor = FakeBeeWrite(client)

    editor._ai_continue()

    assert _no_modal_dialogs["question"], "失败后没有征求同意"
    assert not editor.rich_editor.inserted


def test_local_fallback_labels_itself_honestly(monkeypatch, sync_runner):
    """
    用户**明确同意**后才用本地规则，且提示必须写明"不是 AI 生成"。
    """
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )
    client = StubClient(available=False)
    editor = FakeBeeWrite(client)

    editor._ai_continue()

    assert editor.rich_editor.inserted, "同意后应当插入本地内容"
    assert any("不是 AI 生成" in s for s in editor.statuses), (
        f"本地兜底必须如实标注：{editor.statuses}"
    )


def test_local_polish_labels_itself(monkeypatch, sync_runner):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )
    client = StubClient(available=False)
    editor = FakeBeeWrite(client)
    editor.rich_editor.selected = ("这个东西挺好的", 0, 7)

    editor._ai_polish()

    assert any("不是 AI 生成" in s for s in editor.statuses), editor.statuses


# ---------- 规则 3：走后台线程 ----------

def test_ai_call_goes_through_async_runner(monkeypatch):
    """
    必须用 `AsyncTaskManager` —— LLM 生成要几秒，同步调用会卡死界面。
    """
    from beeoffice.plugins import beewrite_ai_mixin as module

    used = {}

    def run(fn, *args, on_result=None, on_error=None, **kwargs):
        used["called"] = True
        used["fn"] = getattr(fn, "__name__", str(fn))

    monkeypatch.setattr(module.AsyncTaskManager, "run", staticmethod(run))

    editor = FakeBeeWrite(StubClient())
    editor._ai_continue()

    assert used.get("called") is True
    assert used.get("fn") == "chat", used


# ---------- 规则 4：设置入口就在写作场景里 ----------

def test_ai_menu_has_settings_entry():
    """用户点了 AI 却不知道去哪填 Key —— 菜单里要能直接跳过去。"""
    source = (ROOT / "beeoffice" / "plugins" / "beewrite_ai_mixin.py").read_text(
        encoding="utf-8"
    )

    assert "AI 设置…" in source
    assert "_open_ai_settings" in source


def test_short_text_is_rejected_before_calling_ai(_no_modal_dialogs):
    client = StubClient()
    editor = FakeBeeWrite(client)
    editor.rich_editor.text = "太短"

    editor._ai_continue()

    assert not client.prompts, "文本太短时不该调 AI"
    assert _no_modal_dialogs["information"], "应告诉用户文本太短"


def test_polish_without_selection_does_not_call_ai(_no_modal_dialogs):
    client = StubClient()
    editor = FakeBeeWrite(client)
    editor.rich_editor.selected = ("", 0, 0)

    editor._ai_polish()

    assert not client.prompts
    assert _no_modal_dialogs["information"]


def test_open_ai_settings_resets_cached_client(monkeypatch):
    """改了配置要让缓存的客户端失效，否则用户以为没生效。"""
    import beeoffice.ai_settings as ai_module

    monkeypatch.setattr(ai_module, "show_ai_settings",
                        lambda parent=None, settings=None: True)

    editor = FakeBeeWrite(StubClient())
    editor._ai_client = StubClient()

    editor._open_ai_settings()

    assert editor._ai_client is None, "配置更新后必须重建客户端"
    assert any("已更新" in s for s in editor.statuses)
