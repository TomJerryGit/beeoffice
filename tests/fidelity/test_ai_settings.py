# tests/fidelity/test_ai_settings.py
"""
AI 设置界面（服务商预设 / Key / 地址 / 模型 / 测试连接）。

## 为什么要有它
蜜演的 AI 功能此前**没有可视化配置入口** —— `ai_api_key` 只能手动改
`~/.beeoffice_settings.json`（失败提示也是这么教用户的）。用户点了「AI 大纲」
只看到降级模板，却不知道去哪填 Key。

## 测试要点
1. **预设**：三档（DeepSeek / 自定义 / Ollama）；`detect_preset` 能把已存配置
   反查回对应预设；**对不上的地址不许悄悄改成预设**。
2. **保存要真落盘**：改完 `_save()` 后，从同一个文件重新读设置必须能读回。
3. **校验分服务商**：DeepSeek 缺 Key 要拦；**Ollama 不需要 Key**，不能一刀切拦。
4. **测试连接**：走后台线程、按钮禁用/恢复、成功/失败/异常三种显示。
5. **`test_ai_connection` 本身**：用**注入的假传输层**覆盖各种失败
   （401/404/拒连/超时/格式异常），断言给出的是**可操作提示**而不是"失败"。
   —— 测试里**绝不真联网**。
6. **本地 Ollama 不发 Authorization 头**（发了有些网关会拒）。
7. **测试请求必须够短**（`max_tokens` 小）—— 用户点一下就该有结果。
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from beeoffice import ai_settings as ai_module                    # noqa: E402
from beeoffice.ai_settings import AISettingsDialog, show_ai_settings  # noqa: E402
from beeoffice.plugins.beeshow_ai_service import (                # noqa: E402
    AI_PROVIDER_PRESETS, detect_preset,
)
from beeoffice.plugins.beeshow_ai_service import (                # noqa: E402
    probe_ai_connection as check_connection,
)
from beeoffice.settings import AppSettings                        # noqa: E402


@pytest.fixture(autouse=True)
def _no_modal_dialogs(monkeypatch):
    """
    拦截所有模态提示框（**必须**，否则用例会挂死）。

    教训来自本文件的一次"改坏实现"验证：把 Ollama 的 `needs_key` 故意改成
    True 后，`test_ollama_saves_without_key` 走到了 `_save()` 里的
    `QMessageBox.warning` —— 测试环境没人点"确定"，**整个用例挂住 120 秒**。
    拦截后，这类校验路径无论怎么改都只会"断言失败"，不会挂住。
    """
    from PySide6.QtWidgets import QMessageBox

    shown = []
    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(
            QMessageBox, name,
            staticmethod(lambda *a, **k: shown.append(a)),
        )
    return shown


@pytest.fixture
def settings(tmp_path):
    return AppSettings(path=tmp_path / "settings.json")


@pytest.fixture
def dialog(qtbot, settings):
    dlg = AISettingsDialog(settings=settings)
    qtbot.addWidget(dlg)
    yield dlg
    dlg.close()


def _sync_runner(monkeypatch):
    """把 AsyncTaskManager.run 变成同步执行（测试里好断言）。"""
    calls = {}

    def run(fn, *args, on_result=None, on_error=None, **kwargs):
        calls["fn"] = fn
        calls["args"] = args
        try:
            result = fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            if on_error:
                on_error(str(e))
            return
        if on_result:
            on_result(result)

    monkeypatch.setattr(ai_module.AsyncTaskManager, "run", staticmethod(run))
    return calls


# ==================== 1. 预设 ====================

def test_three_presets_exist():
    assert set(AI_PROVIDER_PRESETS) == {"deepseek", "custom", "ollama"}


@pytest.mark.parametrize("key", ["deepseek", "custom", "ollama"])
def test_preset_has_required_fields(key):
    preset = AI_PROVIDER_PRESETS[key]

    assert preset["label"]
    assert "needs_key" in preset
    assert "hint" in preset


def test_deepseek_is_the_default_preset():
    preset = AI_PROVIDER_PRESETS["deepseek"]

    assert preset["api_base"] == "https://api.deepseek.com/v1"
    assert preset["model"] == "deepseek-chat"
    assert preset["needs_key"] is True


def test_ollama_does_not_need_key():
    assert AI_PROVIDER_PRESETS["ollama"]["needs_key"] is False


@pytest.mark.parametrize("key", ["deepseek", "ollama"])
def test_detect_preset_round_trips(key):
    preset = AI_PROVIDER_PRESETS[key]

    assert detect_preset(preset["api_base"], preset["model"]) == key


def test_detect_preset_returns_custom_for_unknown_base():
    """**不许**把用户的第三方地址悄悄认成某个预设。"""
    assert detect_preset("https://my.gateway.example/v1", "gpt-4o") == "custom"


def test_detect_preset_handles_trailing_slash():
    assert detect_preset("https://api.deepseek.com/v1/", "deepseek-chat") \
        == "deepseek"


# ==================== 2. 对话框加载与切换 ====================

def test_dialog_shows_saved_custom_config(qtbot, settings):
    settings.ai_api_base = "https://my.gateway.example/v1"
    settings.ai_model = "gpt-4o"
    settings.ai_api_key = "sk-test"

    dlg = AISettingsDialog(settings=settings)
    qtbot.addWidget(dlg)
    try:
        assert dlg.current_preset_key() == "custom"
        assert dlg.base_edit.text() == "https://my.gateway.example/v1"
        assert dlg.model_combo.currentText() == "gpt-4o"
        assert dlg.key_edit.text() == "sk-test"
    finally:
        dlg.close()


def test_dialog_falls_back_to_defaults_when_empty(qtbot, settings):
    """配置为空时界面要有可用默认值，不能一片空白让用户无从下手。"""
    dlg = AISettingsDialog(settings=settings)
    qtbot.addWidget(dlg)
    try:
        assert dlg.current_preset_key() == "deepseek"
        assert dlg.base_edit.text() == "https://api.deepseek.com/v1"
        assert dlg.model_combo.currentText() == "deepseek-chat"
    finally:
        dlg.close()


def test_switching_preset_updates_address_and_model(dialog):
    dialog.provider_combo.setCurrentIndex(
        dialog.provider_combo.findData("ollama")
    )

    assert dialog.base_edit.text() == "http://localhost:11434/v1"
    assert dialog.model_combo.currentText() == "qwen2.5"
    assert dialog.current_preset_key() == "ollama"


def test_switching_to_custom_keeps_current_values(dialog):
    """切到"自定义"时不能把用户刚填的地址冲掉。"""
    base = dialog.base_edit.text()
    dialog.provider_combo.setCurrentIndex(
        dialog.provider_combo.findData("custom")
    )

    assert dialog.base_edit.text() == base


def test_key_visibility_toggle(dialog):
    from PySide6.QtWidgets import QLineEdit

    assert dialog.key_edit.echoMode() == QLineEdit.EchoMode.Password
    dialog.show_key_btn.setChecked(True)
    assert dialog.key_edit.echoMode() == QLineEdit.EchoMode.Normal
    dialog.show_key_btn.setChecked(False)
    assert dialog.key_edit.echoMode() == QLineEdit.EchoMode.Password


# ==================== 3. 保存（必须真落盘）====================

def test_save_writes_to_settings_file(dialog, settings):
    dialog.key_edit.setText("sk-abc")
    dialog.base_edit.setText("https://api.deepseek.com/v1")
    dialog.model_combo.setCurrentText("deepseek-reasoner")

    dialog._save()

    assert settings.ai_api_key == "sk-abc"
    assert settings.ai_api_base == "https://api.deepseek.com/v1"
    assert settings.ai_model == "deepseek-reasoner"
    # **关键**：从文件重新读一遍，确认真的写进了磁盘
    reloaded = AppSettings(path=settings.path)
    assert reloaded.ai_api_key == "sk-abc"
    assert reloaded.ai_model == "deepseek-reasoner"


def test_save_without_key_warns_and_does_not_save(
        dialog, settings, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    shown = []
    monkeypatch.setattr(
        QMessageBox, "warning",
        staticmethod(lambda parent, title, text, *a, **k: shown.append(text)),
    )
    dialog.key_edit.setText("")

    dialog._save()

    assert shown, "缺 Key 时应提示"
    assert "platform.deepseek.com" in shown[0] or "Ollama" in shown[0], (
        "提示要告诉用户去哪申请或改用本地"
    )
    assert not settings.path.exists(), "校验没过却写了设置文件"


def test_ollama_saves_without_key(qtbot, settings, monkeypatch):
    """**Ollama 不需要 Key** —— 不能一刀切拦下来。"""
    dlg = AISettingsDialog(settings=settings)
    qtbot.addWidget(dlg)
    try:
        dlg.provider_combo.setCurrentIndex(
            dlg.provider_combo.findData("ollama")
        )
        dlg.key_edit.setText("")
        dlg._save()

        assert settings.ai_api_base == "http://localhost:11434/v1"
        assert settings.ai_model == "qwen2.5"
        assert AppSettings(path=settings.path).ai_model == "qwen2.5"
    finally:
        dlg.close()


def test_save_without_base_or_model_warns(dialog, settings, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    shown = []
    monkeypatch.setattr(
        QMessageBox, "warning",
        staticmethod(lambda *a, **k: shown.append(a)),
    )
    dialog.key_edit.setText("sk-x")
    dialog.base_edit.setText("")

    dialog._save()

    assert shown, "地址为空应提示"
    assert not settings.path.exists()


# ==================== 4. 「测试连接」的接线 ====================

def test_test_connection_runs_in_background_and_shows_success(
        dialog, monkeypatch):
    _sync_runner(monkeypatch)
    monkeypatch.setattr(
        ai_module, "probe_ai_connection",
        lambda config, **kw: (True, "连接成功：deepseek-chat 已响应「OK」", 123),
    )
    dialog.key_edit.setText("sk-x")

    dialog._test_connection()

    text = dialog.status_label.text()
    assert "✅" in text and "123" in text, text
    assert dialog.test_btn.isEnabled(), "测试结束后按钮要恢复可用"


def test_test_connection_shows_actionable_failure(dialog, monkeypatch):
    _sync_runner(monkeypatch)
    monkeypatch.setattr(
        ai_module, "probe_ai_connection",
        lambda config, **kw: (False, "API Key 无效或没有权限（HTTP 401/403）。", 42),
    )

    dialog._test_connection()

    text = dialog.status_label.text()
    assert "❌" in text and "API Key" in text, text
    assert dialog.test_btn.isEnabled()


def test_test_connection_handles_exception(dialog, monkeypatch):
    _sync_runner(monkeypatch)

    def boom(config, **kw):
        raise RuntimeError("炸了")

    monkeypatch.setattr(ai_module, "probe_ai_connection", boom)

    dialog._test_connection()

    assert "测试失败" in dialog.status_label.text()
    assert dialog.test_btn.isEnabled()


def test_test_connection_tests_current_form_values(dialog, monkeypatch):
    """测的是**界面上当前填的值**（先测再存），不是已保存的值。"""
    captured = {}

    def fake(config, **kw):
        captured.update(config)
        return True, "ok", 1

    _sync_runner(monkeypatch)
    monkeypatch.setattr(ai_module, "probe_ai_connection", fake)

    dialog.key_edit.setText("sk-form")
    dialog.base_edit.setText("https://form.example/v1")
    dialog.model_combo.setCurrentText("form-model")
    dialog._test_connection()

    assert captured == {
        "api_key": "sk-form",
        "api_base": "https://form.example/v1",
        "model": "form-model",
    }, captured


# ==================== 5. test_ai_connection 本身（注入假传输层）====================

def test_connection_refuses_without_key_for_remote():
    ok, message, _ = check_connection(
        {"api_base": "https://api.deepseek.com/v1"}
    )

    assert ok is False
    assert "API Key" in message


def test_connection_success_reports_model_and_latency():
    def opener(url, headers, payload, timeout):
        assert url.endswith("/chat/completions")
        assert headers["Authorization"] == "Bearer sk-x"
        return {"choices": [{"message": {"content": "OK"}}]}

    ok, message, latency = check_connection(
        {"api_key": "sk-x", "api_base": "https://api.deepseek.com/v1",
         "model": "deepseek-chat"},
        opener=opener,
    )

    assert ok is True
    assert "deepseek-chat" in message
    assert isinstance(latency, int)


def test_connection_request_is_short():
    """测试连接必须**很短** —— 用户点一下不该等 30 秒，也不该烧 token。"""
    seen = {}

    def opener(url, headers, payload, timeout):
        seen.update(payload)
        seen["timeout"] = timeout
        return {"choices": [{"message": {"content": "OK"}}]}

    check_connection({"api_key": "k"}, opener=opener)

    assert seen["max_tokens"] <= 16, seen["max_tokens"]
    assert seen["timeout"] <= 15, seen["timeout"]


@pytest.mark.parametrize("error_text,expect", [
    ("HTTP 401: Unauthorized", "API Key"),
    ("HTTP 403: Forbidden", "API Key"),
    ("HTTP 404: Not Found", "/v1"),
    ("HTTP 429: Too Many Requests", "429"),
])
def test_connection_error_messages_are_actionable(error_text, expect):
    def opener(url, headers, payload, timeout):
        raise RuntimeError(error_text)

    ok, message, _ = check_connection(
        {"api_key": "k", "api_base": "https://api.deepseek.com/v1"},
        opener=opener,
    )

    assert ok is False
    assert expect in message, message


def test_connection_error_mentions_ollama_when_local():
    def opener(url, headers, payload, timeout):
        raise RuntimeError("Connection refused")

    ok, message, _ = check_connection(
        {"api_base": "http://localhost:11434/v1"}, opener=opener,
    )

    assert ok is False
    assert "ollama serve" in message, message


def test_connection_handles_malformed_response():
    def opener(url, headers, payload, timeout):
        return {"unexpected": True}

    ok, message, _ = check_connection(
        {"api_key": "k", "api_base": "https://api.deepseek.com/v1"},
        opener=opener,
    )

    assert ok is False
    assert "choices" in message


def test_connection_omits_authorization_for_local_ollama():
    """本地 Ollama 不该带 Authorization（带了有些网关会拒）。"""
    seen = {}

    def opener(url, headers, payload, timeout):
        seen.update(headers)
        return {"choices": [{"message": {"content": "OK"}}]}

    ok, _, _ = check_connection(
        {"api_base": "http://localhost:11434/v1", "model": "qwen2.5"},
        opener=opener,
    )

    assert ok is True
    assert "Authorization" not in seen, seen


# ==================== 6. 菜单接线 ====================

def test_menu_has_ai_settings_entry():
    """菜单里必须有入口 —— 否则用户还是找不到。"""
    source = (ROOT / "beeoffice" / "menus.py").read_text(encoding="utf-8")

    assert "_show_ai_settings" in source
    assert "AI 设置" in source


def test_show_ai_settings_returns_false_on_cancel(monkeypatch, settings):
    from PySide6.QtWidgets import QDialog

    monkeypatch.setattr(
        AISettingsDialog, "exec",
        lambda self: QDialog.DialogCode.Rejected,
    )

    assert show_ai_settings(None, settings=settings) is False


def test_settings_json_keeps_ai_fields_secret_encoded(settings):
    """
    Key 在设置文件里是 base64（不是明文），与既有做法一致。
    （注意：base64 **不是加密**，只是避免肉眼直读。）
    """
    settings.ai_api_key = "sk-plain-secret"
    settings.save()

    raw = json.loads(Path(settings.path).read_text(encoding="utf-8"))
    assert raw["ai_api_key"] != "sk-plain-secret"
    assert AppSettings(path=settings.path).ai_api_key == "sk-plain-secret"
