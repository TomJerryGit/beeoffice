# tests/fidelity/test_ai_error_messages.py
"""
AI 报错的**归因正确性**（真机反馈驱动）。

## 问题（用户截图）
用户在「AI 设置」里用**本地 Ollama** 测试连接，填的
`http://localhost:11434/v1` **完全正确**，模型名是 `qwen2.5`。
弹出来的却是：

    ❌ 接口地址不对（HTTP 404）。地址应指向兼容 OpenAI 的端点…

**真实原因**：Ollama 对未知模型返回 **HTTP 404** + body
`{"error":"model \"qwen2.5\" not found, try pulling it first"}`
（`qwen2.5` 没带 tag → 该 tag 不存在）。提示把用户引向反复改地址，
**方向错了就永远修不好**。

## 为什么会这样（两条同时成立）
1. 主传输层用 `requests`，`raise_for_status()` 抛出的异常**字符串里不含响应体**
   → 代码看不到 `model ... not found`；
2. 仓库里对 404 有**两套口径**的文案（一套甩锅地址，一套说"地址或模型名"），
   用户撞上的是差的那套。

## 本文件的测试
* 表驱动覆盖各类失败的**归因与可操作性**（纯函数，快）；
* **端到端**：起一个真实本地 HTTP 服务返回 Ollama 的原样 404，
  走完整 `probe_ai_connection()` —— 这才证明"body 真的被带到了判断处"。
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


# ==================== 1. 归因表（纯函数）====================

def test_missing_model_is_diagnosed_as_model_not_url():
    """**核心回归**：Ollama 的"模型不存在"不能被说成"地址不对"。"""
    from beeoffice.plugins.ai_errors import explain_ai_error

    message = explain_ai_error(
        status=404,
        body='{"error":"model \\"qwen2.5\\" not found, try pulling it first"}',
        error_text='HTTP 404: Not Found for url: ...',
        api_base="http://localhost:11434/v1", model="qwen2.5", is_local=True,
    )

    assert "不存在" in message or "模型" in message, message
    assert "地址不对" not in message, f"仍在甩锅地址：{message}"
    assert "ollama pull" in message, f"没给可照抄的命令：{message}"
    assert "tag" in message, f"模型名缺 tag 这件事要说明：{message}"


def test_untagged_model_suggestion_shows_tag_example():
    from beeoffice.plugins.ai_errors import explain_ai_error

    message = explain_ai_error(
        status=404, body='model "qwen2.5" not found', error_text="HTTP 404",
        api_base="http://127.0.0.1:11434/v1", model="qwen2.5", is_local=True,
    )
    assert "qwen2.5:7b" in message, message


def test_tagged_model_suggestion_does_not_add_tag_noise():
    from beeoffice.plugins.ai_errors import explain_ai_error

    message = explain_ai_error(
        status=404, body='model "qwen2.5:9b" not found', error_text="HTTP 404",
        api_base="http://127.0.0.1:11434/v1", model="qwen2.5:9b", is_local=True,
    )
    assert "ollama pull qwen2.5:9b" in message
    assert ":7b" not in message, "已经带 tag 了就别再塞示例"


def test_wrong_path_still_reports_url():
    """真的是地址问题时要照旧说地址（不能为了修一个 bug 弄坏另一个）。"""
    from beeoffice.plugins.ai_errors import explain_ai_error

    message = explain_ai_error(
        status=404, body="404 page not found", error_text="HTTP 404",
        api_base="http://localhost:11434", model="qwen2.5:7b", is_local=True,
    )
    assert "接口地址" in message
    assert "11434/v1" in message, "本地场景要给出 Ollama 的正确写法"


def test_404_without_body_lists_both_possibilities():
    """拿不到 body 时**不赌方向**：两种可能都列出来。"""
    from beeoffice.plugins.ai_errors import explain_ai_error

    message = explain_ai_error(
        status=404, error_text="HTTP 404: Not Found",
        api_base="http://localhost:11434/v1", model="qwen2.5", is_local=True,
    )
    assert "接口地址" in message and "模型名" in message, message


def test_service_down_tells_user_to_start_ollama():
    from beeoffice.plugins.ai_errors import explain_ai_error

    message = explain_ai_error(
        error_text="Connection refused", api_base="http://localhost:11434/v1",
        model="qwen2.5:7b", is_local=True,
    )
    assert "ollama serve" in message
    assert "ollama pull" in message


def test_key_errors_still_reported():
    from beeoffice.plugins.ai_errors import explain_ai_error

    message = explain_ai_error(
        status=401, body='{"error":"invalid api key"}',
        error_text="HTTP 401 Unauthorized",
        api_base="https://api.deepseek.com/v1", model="deepseek-chat",
    )
    assert "401" in message or "Key" in message


def test_local_401_suggests_leaving_key_empty():
    from beeoffice.plugins.ai_errors import explain_ai_error

    message = explain_ai_error(
        status=401, error_text="HTTP 401", api_base="http://localhost:11434/v1",
        model="qwen2.5:7b", is_local=True,
    )
    assert "留空" in message, message


# ==================== 2. 端到端：真实本地服务（Ollama 原样 404）====================

class _OllamaLikeHandler(BaseHTTPRequestHandler):
    """模拟 Ollama：未知模型 → 404 + **真实 body**；模型正确 → 200。"""

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception:  # noqa: BLE001
            payload = {}
        model = payload.get("model", "")
        if model != "qwen2.5:7b":
            body = json.dumps(
                {"error": f'model "{model}" not found, try pulling it first'}
            ).encode("utf-8")
            status = 404
        else:
            body = json.dumps(
                {"choices": [{"message": {"content": "OK"}}]}
            ).encode("utf-8")
            status = 200
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # noqa: ARG002 - 静音
        return


@pytest.fixture
def ollama_like_server():
    server = HTTPServer(("127.0.0.1", 0), _OllamaLikeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    finally:
        server.shutdown()


def test_probe_end_to_end_diagnoses_model_not_url(ollama_like_server):
    """
    **最强的回归**：走完整 `probe_ai_connection()`（真实 HTTP）。
    它证明传输层确实把**响应体**带到了判断处 ——
    否则"模型不存在"永远会被误报成"地址不对"。
    """
    from beeoffice.plugins.beeshow_ai_service import probe_ai_connection

    ok, message, _latency = probe_ai_connection(
        {"api_key": "", "api_base": ollama_like_server, "model": "qwen2.5"}
    )

    assert ok is False
    assert "地址不对" not in message, f"又甩锅地址了：{message}"
    assert "ollama pull qwen2.5" in message, message


def test_probe_end_to_end_succeeds_with_correct_model(ollama_like_server):
    """happy path 不能被这次改动弄坏。"""
    from beeoffice.plugins.beeshow_ai_service import probe_ai_connection

    ok, message, _latency = probe_ai_connection(
        {"api_key": "", "api_base": ollama_like_server, "model": "qwen2.5:7b"}
    )

    assert ok is True, message
    assert "连接成功" in message


# ==================== 3. 界面：Ollama 不该留着 Key ====================

def test_ollama_preset_disables_and_clears_key_field(qtbot):
    """截图里的另一处小问题：选了「本地 Ollama」但 Key 框里还留着旧 Key。"""
    from beeoffice.ai_settings import AI_PROVIDER_PRESETS, AISettingsDialog

    dialog = AISettingsDialog()
    qtbot.addWidget(dialog)
    try:
        # 切到一个"需要 Key"的服务商并填上 Key
        needs_key = [k for k, v in AI_PROVIDER_PRESETS.items()
                     if v.get("needs_key", True)]
        assert needs_key, "测试前提：应存在需要 Key 的服务商"
        dialog._refresh_hint(needs_key[0])
        dialog.key_edit.setText("sk-abcdef")

        # 切到本地 Ollama（无需 Key）
        ollama = [k for k, v in AI_PROVIDER_PRESETS.items()
                  if not v.get("needs_key", True)]
        assert ollama, "测试前提：应存在无需 Key 的服务商（本地 Ollama）"
        dialog._refresh_hint(ollama[0])

        assert dialog.key_edit.text() == "", "旧 Key 还留着（会让人误以为必填）"
        assert dialog.key_edit.isEnabled() is False, "无需 Key 时该置灰"
    finally:
        dialog.close()
