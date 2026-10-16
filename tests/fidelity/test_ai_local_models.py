# tests/fidelity/test_ai_local_models.py
"""
AI 设置：**自动列出本机已安装的模型**（真机反馈驱动）。

## 问题
设置界面「本地 Ollama」的模型建议是**写死的**
`["qwen2.5", "llama3.1", "gemma2"]`，而用户机器上通常**一个都没装** ——
于是每台新机器第一次点开就撞 `模型不存在（HTTP 404）`，
用户还得自己猜 Ollama 里到底有什么。

## 修法
问 Ollama 要清单，**装了什么就用什么**：
* OpenAI 兼容：`GET {api_base}/models` → `{"data":[{"id": …}]}`
* Ollama 原生：`GET {host}/api/tags` → `{"models":[{"name": …}]}`
  （原生 API 在**根**路径上，所以要把结尾的 `/v1` 去掉再试）

两条都失败就**如实说明**（提示去 `ollama serve` / `ollama pull`），**绝不编造模型名**。
界面侧：切到「本地 Ollama」/ 打开时已是本地 / 点「刷新本机模型」三条路径都会拉清单，
并且当用户填的模型**本机没有**时，自动换成第一个可用的并**说明换过**。
"""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ==================== 1. 解析两种响应形态 ====================

def test_extract_names_from_openai_shape():
    from beeoffice.plugins.beeshow_ai_service import _extract_model_names

    names = _extract_model_names(
        {"data": [{"id": "b-model"}, {"id": "a-model"}, {"id": "a-model"}]},
        "openai",
    )
    assert names == ["a-model", "b-model"], names  # 去重 + 排序


def test_extract_names_from_ollama_shape():
    from beeoffice.plugins.beeshow_ai_service import _extract_model_names

    names = _extract_model_names(
        {"models": [{"name": "llama3.2:latest"}, {"name": "qwen2.5:7b"}]},
        "ollama",
    )
    assert names == ["llama3.2:latest", "qwen2.5:7b"]


def test_extract_names_ignores_garbage():
    from beeoffice.plugins.beeshow_ai_service import _extract_model_names

    assert _extract_model_names({}, "openai") == []
    assert _extract_model_names({"data": [{"nope": 1}, None]}, "openai") == []


# ==================== 2. 端点与降级（可注入 getter）====================

def test_prefers_openai_models_endpoint():
    from beeoffice.plugins.beeshow_ai_service import list_local_models

    seen = []

    def getter(url, headers, timeout):
        seen.append(url)
        return {"data": [{"id": "llama3.2:latest"}]}

    ok, names, message = list_local_models(
        "http://localhost:11434/v1", getter=getter
    )

    assert ok is True
    assert names == ["llama3.2:latest"]
    assert seen[0] == "http://localhost:11434/v1/models", seen


def test_falls_back_to_ollama_native_api():
    """`/v1/models` 不通时，退到根路径的 `/api/tags`（原生 API）。"""
    from beeoffice.plugins.beeshow_ai_service import list_local_models

    seen = []

    def getter(url, headers, timeout):
        seen.append(url)
        if url.endswith("/api/tags"):
            return {"models": [{"name": "qwen2.5:7b"}]}
        raise RuntimeError("HTTP 404")

    ok, names, message = list_local_models(
        "http://localhost:11434/v1", getter=getter
    )

    assert ok is True, message
    assert names == ["qwen2.5:7b"]
    assert seen == ["http://localhost:11434/v1/models",
                    "http://localhost:11434/api/tags"], seen


def test_empty_list_is_reported_not_invented():
    """拿不到清单就**如实失败**，绝不编造模型名。"""
    from beeoffice.plugins.beeshow_ai_service import list_local_models

    ok, names, message = list_local_models(
        "http://localhost:11434/v1",
        getter=lambda url, headers, timeout: {"data": []},
    )

    assert ok is False
    assert names == []
    assert message, "失败也要给出说明"


def test_no_api_base():
    from beeoffice.plugins.beeshow_ai_service import list_local_models

    ok, names, message = list_local_models("", getter=lambda *a: {})
    assert ok is False and names == []


# ==================== 3. 真实本地 HTTP 服务（端到端）====================

class _ModelsHandler(BaseHTTPRequestHandler):
    """按配置返回：/v1/models 和/或 /api/tags。"""

    serve_openai = True
    serve_native = False

    def do_GET(self):  # noqa: N802
        payload = None
        if self.path.endswith("/models") and type(self).serve_openai:
            payload = {"data": [{"id": "llama3.2:latest"},
                                {"id": "qwen2.5:7b"}]}
        elif self.path.endswith("/api/tags") and type(self).serve_native:
            payload = {"models": [{"name": "llama3.2:latest"}]}
        if payload is None:
            body = b'{"error":"404 page not found"}'
            self.send_response(404)
        else:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # noqa: ARG002
        return


def _serve(handler_cls):
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def test_end_to_end_openai_endpoint():
    from beeoffice.plugins.beeshow_ai_service import list_local_models

    server, base = _serve(_ModelsHandler)
    try:
        ok, names, message = list_local_models(f"{base}/v1")
        assert ok is True, message
        assert names == ["llama3.2:latest", "qwen2.5:7b"], names
    finally:
        server.shutdown()


def test_end_to_end_native_fallback():
    """只有原生 `/api/tags` 可用的服务（模拟老版本 Ollama）也要能列出来。"""

    class NativeOnly(_ModelsHandler):
        serve_openai = False
        serve_native = True

    from beeoffice.plugins.beeshow_ai_service import list_local_models

    server, base = _serve(NativeOnly)
    try:
        ok, names, message = list_local_models(f"{base}/v1")
        assert ok is True, message
        assert names == ["llama3.2:latest"], names
    finally:
        server.shutdown()


# ==================== 4. 界面：自动填入 + 替换没装的默认值 ====================

@pytest.fixture
def dialog(qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from beeoffice.ai_settings import AISettingsDialog

    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: None))
    dlg = AISettingsDialog()
    qtbot.addWidget(dlg)
    return dlg


def _select_ollama(dialog):
    keys = [dialog.provider_combo.itemData(i)
            for i in range(dialog.provider_combo.count())]
    dialog.provider_combo.setCurrentIndex(keys.index("ollama"))


def _wait_models(dialog, qtbot):
    qtbot.waitUntil(lambda: dialog.refresh_models_btn.isEnabled(), timeout=5000)


def test_switching_to_ollama_lists_local_models(dialog, qtbot, monkeypatch):
    """**核心回归**：切到本地 Ollama → 下拉变成**本机真实装了的**模型。"""
    import beeoffice.ai_settings as settings_ui

    monkeypatch.setattr(
        settings_ui, "list_local_models",
        lambda base, **kw: (True, ["llama3.2:latest"], "1 个模型"),
    )

    _select_ollama(dialog)
    _wait_models(dialog, qtbot)

    items = [dialog.model_combo.itemText(i)
             for i in range(dialog.model_combo.count())]
    assert items == ["llama3.2:latest"], items
    # 预设里写死的 qwen2.5 本机没有 → 自动换成可用的，并说明换过
    assert dialog.model_combo.currentText() == "llama3.2:latest"
    assert "本机没有" in dialog.hint_label.text() or "自动选中" in dialog.hint_label.text()


def test_keeps_user_choice_when_it_is_installed(dialog, qtbot, monkeypatch):
    """用户填的模型本机确实有 → 尊重他的选择，不要乱改。"""
    import beeoffice.ai_settings as settings_ui

    monkeypatch.setattr(
        settings_ui, "list_local_models",
        lambda base, **kw: (True, ["llama3.2:latest", "qwen2.5:7b"], "2 个"),
    )
    _select_ollama(dialog)
    _wait_models(dialog, qtbot)
    dialog.model_combo.setCurrentText("qwen2.5:7b")

    dialog._refresh_model_list()
    _wait_models(dialog, qtbot)

    assert dialog.model_combo.currentText() == "qwen2.5:7b"


def test_no_models_gives_actionable_hint(dialog, qtbot, monkeypatch):
    """本机一个模型都没有 → 提示去 pull，而不是静默。"""
    import beeoffice.ai_settings as settings_ui

    monkeypatch.setattr(
        settings_ui, "list_local_models",
        lambda base, **kw: (False, [], "connection refused"),
    )

    _select_ollama(dialog)
    _wait_models(dialog, qtbot)

    hint = dialog.hint_label.text()
    assert "ollama" in hint and ("pull" in hint or "serve" in hint), hint


def test_non_local_address_does_not_probe(dialog, qtbot, monkeypatch):
    """远端地址不该去问"本机装了哪些模型"（那是 Ollama 才有的接口）。"""
    import beeoffice.ai_settings as settings_ui

    called = []
    monkeypatch.setattr(
        settings_ui, "list_local_models",
        lambda base, **kw: (called.append(base), (True, ["x"], ""))[1],
    )

    keys = [dialog.provider_combo.itemData(i)
            for i in range(dialog.provider_combo.count())]
    dialog.provider_combo.setCurrentIndex(keys.index("deepseek"))
    dialog.base_edit.setText("https://api.deepseek.com/v1")

    dialog._refresh_model_list()

    assert called == [], f"不该探测远端地址：{called}"


def test_local_detection(dialog):
    assert dialog._is_local_base("http://localhost:11434/v1") is True
    assert dialog._is_local_base("http://127.0.0.1:11434/v1") is True
    assert dialog._is_local_base("https://api.deepseek.com/v1") is False
