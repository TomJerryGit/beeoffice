# beeoffice/ai_settings.py
"""
AI 设置对话框（P1-B 延伸）。

为什么要有它
------------
蜜演的 AI 功能（AI 大纲 / AI 细化 / AI 讲稿）此前**没有任何可视化配置入口**：
`ai_api_key` / `ai_api_base` / `ai_model` 只有 `settings.py`（存储层）读写，
用户得**手动编辑 `~/.beeoffice_settings.json`** —— 而且失败提示就是这么教用户的
（`beeshow_notes_mixin.py:249`）。结果是：用户点了「AI 大纲」，只看到降级模板，
却不知道去哪填 Key。

本对话框提供：
  · **服务商预设下拉**（DeepSeek / OpenAI 兼容自定义 / 本地 Ollama）
  · API Key、接口地址、模型名
  · **「测试连接」**：发一次**极短**请求（`max_tokens=8`、超时 12 秒），
    并把失败翻译成**可操作**的提示（401/K 不对、404/地址不对、拒连/服务没起）
  · 保存写回 `AppSettings`

设计取舍
--------
* 协议本来就是 OpenAI 兼容，所以只给"预设 + 可改地址/模型"，
  **不硬绑一家**；检测到用户自定义地址时下拉显示「自定义」，绝不悄悄改回预设。
* 「测试连接」**必须走后台线程**（网络调用会阻塞 UI），用项目已有的
  `AsyncTaskManager`。
"""
import logging

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QVBoxLayout,
)

from beeoffice.async_task import AsyncTaskManager
from beeoffice.plugins.beeshow_ai_service import (
    AI_PROVIDER_PRESETS, detect_preset, probe_ai_connection,
)

#: 各预设推荐的模型（下拉可编辑，仅作建议）
MODEL_SUGGESTIONS = {
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "custom": ["gpt-4o-mini", "qwen-plus", "glm-4-flash"],
    "ollama": ["qwen2.5", "llama3.1", "gemma2"],
}

_PRESET_ORDER = ["deepseek", "custom", "ollama"]


class AISettingsDialog(QDialog):
    """AI 服务设置（服务商 / Key / 地址 / 模型 / 测试连接）。"""

    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        from beeoffice.settings import AppSettings

        self.settings = settings if settings is not None else AppSettings()
        self.setWindowTitle("🤖 AI 设置")
        self.resize(620, 340)
        self._build_ui()
        self._load_settings()

    # ------------------------------------------------------------------
    def _build_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.provider_combo = QComboBox()
        for key in _PRESET_ORDER:
            self.provider_combo.addItem(AI_PROVIDER_PRESETS[key]["label"], key)
        form.addRow("服务商", self.provider_combo)

        key_row = QHBoxLayout()
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("本地 Ollama 可留空")
        self.show_key_btn = QPushButton("显示")
        self.show_key_btn.setCheckable(True)
        self.show_key_btn.setFixedWidth(56)
        self.show_key_btn.toggled.connect(self._toggle_key_visibility)
        key_row.addWidget(self.key_edit)
        key_row.addWidget(self.show_key_btn)
        form.addRow("API Key", key_row)

        self.base_edit = QLineEdit()
        self.base_edit.setPlaceholderText("https://api.deepseek.com/v1")
        form.addRow("接口地址", self.base_edit)

        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        form.addRow("模型名", self.model_combo)

        layout.addLayout(form)

        self.hint_label = QLabel("")
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet("color:#666;font-size:12px;")
        layout.addWidget(self.hint_label)

        self.privacy_label = QLabel(
            "🔒 只把提示词发给你选择的这个服务；蜜蜂办公不收集任何数据。"
            "想完全离线可用「本地 Ollama」。"
        )
        self.privacy_label.setWordWrap(True)
        self.privacy_label.setStyleSheet("color:#2E7D32;font-size:12px;")
        layout.addWidget(self.privacy_label)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addStretch()

        row = QHBoxLayout()
        self.test_btn = QPushButton("测试连接")
        self.test_btn.clicked.connect(self._test_connection)
        row.addWidget(self.test_btn)
        row.addStretch()

        buttons = QDialogButtonBox()
        save_btn = QPushButton("保存")
        save_btn.setDefault(True)
        cancel_btn = QPushButton("取消")
        buttons.addButton(save_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(cancel_btn, QDialogButtonBox.ButtonRole.RejectRole)
        row.addWidget(buttons)
        layout.addLayout(row)

        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        save_btn.clicked.connect(self._save)
        cancel_btn.clicked.connect(self.reject)

    # ------------------------------------------------------------------
    def _toggle_key_visibility(self, shown):
        self.key_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if shown
            else QLineEdit.EchoMode.Password
        )

    def current_preset_key(self) -> str:
        data = self.provider_combo.currentData()
        return data if data in AI_PROVIDER_PRESETS else "deepseek"

    def _load_settings(self):
        """把已保存的配置填进界面（并反查属于哪个预设）。"""
        api_base = getattr(self.settings, "ai_api_base", "") or ""
        model = getattr(self.settings, "ai_model", "") or ""
        preset = detect_preset(api_base, model)
        index = self.provider_combo.findData(preset)
        self.provider_combo.setCurrentIndex(index if index >= 0 else 0)

        self.key_edit.setText(getattr(self.settings, "ai_api_key", "") or "")
        # 地址/模型为空时用预设兜底，避免界面一片空白让用户无从下手
        default = AI_PROVIDER_PRESETS[preset]
        self.base_edit.setText(api_base or default["api_base"])
        self.model_combo.setCurrentText(model or default["model"])
        self._refresh_models(preset)
        self._refresh_hint(preset)

    def _refresh_models(self, preset):
        current = self.model_combo.currentText()
        self.model_combo.clear()
        self.model_combo.addItems(MODEL_SUGGESTIONS.get(preset, []))
        if current:
            self.model_combo.setCurrentText(current)

    def _refresh_hint(self, preset):
        info = AI_PROVIDER_PRESETS[preset]
        self.hint_label.setText(info.get("hint", ""))
        needs_key = info.get("needs_key", True)
        self.key_edit.setEnabled(True)      # 始终可填，只是不强制
        self.key_edit.setPlaceholderText(
            "必填：去服务商申请" if needs_key else "本地 Ollama 可留空"
        )
        # ⚠️ 真机反馈（截图）：服务商选了「本地 Ollama（无需 Key）」，但 Key 框里
        # 仍留着上一次填的 Key —— 既没用又让人以为"必须填"，还会被误当成鉴权失败的原因。
        # 这里在切到"无需 Key"的服务商时把框**清空并置灰**（切回需要 Key 的会自动恢复）。
        if not needs_key:
            if self.key_edit.text():
                self.key_edit.clear()
            self.key_edit.setEnabled(False)
            self.key_edit.setToolTip(
                "本地 Ollama 不需要 API Key；Key 不会被发送（数据不出本机）"
            )
        else:
            self.key_edit.setToolTip("")

    def _on_provider_changed(self, _index):
        preset = self.current_preset_key()
        info = AI_PROVIDER_PRESETS[preset]
        if preset != "custom":
            # 非自定义：地址/模型跟着预设走（用户仍可再改）
            if info["api_base"]:
                self.base_edit.setText(info["api_base"])
            if info["model"]:
                self.model_combo.setCurrentText(info["model"])
        self._refresh_models(preset)
        self._refresh_hint(preset)

    # ------------------------------------------------------------------
    def current_config(self) -> dict:
        return {
            "api_key": self.key_edit.text().strip(),
            "api_base": self.base_edit.text().strip(),
            "model": self.model_combo.currentText().strip(),
        }

    def _test_connection(self):
        """
        测试连接（后台线程，避免卡界面）。

        测的是**界面上当前填的值**，不是已保存的值 —— 用户可以"先测再存"。
        """
        config = self.current_config()
        self.test_btn.setEnabled(False)
        self.status_label.setStyleSheet("color:#666;")
        self.status_label.setText("正在测试连接…")

        AsyncTaskManager.run(
            probe_ai_connection,
            config,
            on_result=self._on_test_result,
            on_error=self._on_test_error,
        )

    def _on_test_result(self, result):
        ok, message, latency = result
        self.test_btn.setEnabled(True)
        if ok:
            self.status_label.setStyleSheet("color:#2E7D32;")
            self.status_label.setText(
                f"✅ {message}" + (f"（{latency} ms）" if latency else "")
            )
        else:
            self.status_label.setStyleSheet("color:#C62828;")
            self.status_label.setText(f"❌ {message}")

    def _on_test_error(self, error):
        self.test_btn.setEnabled(True)
        self.status_label.setStyleSheet("color:#C62828;")
        self.status_label.setText(f"❌ 测试失败：{error}")

    # ------------------------------------------------------------------
    def _save(self):
        config = self.current_config()
        preset = self.current_preset_key()
        info = AI_PROVIDER_PRESETS[preset]

        if info.get("needs_key", True) and not config["api_key"]:
            QMessageBox.warning(
                self, "还差一步",
                "这个服务商需要 API Key。\n\n"
                "· DeepSeek：去 platform.deepseek.com 申请\n"
                "· 或把服务商切到「本地 Ollama」（无需 Key、数据不出本机）",
            )
            return
        if not config["api_base"]:
            QMessageBox.warning(self, "还差一步", "请填写接口地址。")
            return
        if not config["model"]:
            QMessageBox.warning(self, "还差一步", "请填写模型名。")
            return

        try:
            self.settings.ai_api_key = config["api_key"]
            self.settings.ai_api_base = config["api_base"]
            self.settings.ai_model = config["model"]
            self.settings.save()
        except Exception as e:  # noqa: BLE001 - 保存失败要如实告知
            logging.error(f"[AI 设置] 保存失败: {e}")
            QMessageBox.warning(self, "保存失败", f"配置没能写入设置文件：{e}")
            return
        self.accept()


def show_ai_settings(parent=None, settings=None) -> bool:
    """显示 AI 设置对话框；返回是否保存了配置。"""
    dialog = AISettingsDialog(parent, settings=settings)
    result = dialog.exec()
    return result == QDialog.DialogCode.Accepted
