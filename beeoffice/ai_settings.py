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
    AI_PROVIDER_PRESETS, detect_preset, list_local_models,
    probe_ai_connection,
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
        # 模型名行：右侧给一个「刷新」——选到本地 Ollama 时会**自动列出本机已装模型**，
        # 刚 `ollama pull` 完也能点它立刻刷新，不必重开对话框。
        model_row = QHBoxLayout()
        model_row.addWidget(self.model_combo, 1)
        self.refresh_models_btn = QPushButton("刷新本机模型")
        self.refresh_models_btn.setToolTip(
            "列出本机 Ollama 已安装的模型（自动填入模型名）"
        )
        self.refresh_models_btn.clicked.connect(self._refresh_model_list)
        model_row.addWidget(self.refresh_models_btn)
        form.addRow("模型名", model_row)

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
        # 打开时若已是"本地 Ollama"，顺手把本机已装模型列出来
        # （异步，不卡界面；拉完模型再打开就能直接选）
        if preset == "ollama":
            self._refresh_model_list()

    def _refresh_models(self, preset):
        current = self.model_combo.currentText()
        self.model_combo.clear()
        self.model_combo.addItems(MODEL_SUGGESTIONS.get(preset, []))
        if current:
            self.model_combo.setCurrentText(current)

    # ------------------------------------------------------------------
    # 本机模型清单（真机反馈驱动）
    # ------------------------------------------------------------------
    def _is_local_base(self, api_base: str = "") -> bool:
        """地址是否指向本机（只有本机才值得去问"装了哪些模型"）。"""
        base = (api_base or self.base_edit.text() or "").lower()
        return "localhost" in base or "127.0.0.1" in base

    def _refresh_model_list(self):
        """
        列出**本机已安装**的模型并填入下拉。

        ⚠️ 修的是真机反馈：预设里的模型建议是**写死的**
        （`qwen2.5`/`llama3.1`/`gemma2`），而用户机器上通常一个都没装 ——
        于是第一次点开就撞 `模型不存在（HTTP 404）`。
        现在直接问 Ollama 要清单：**装了什么就用什么**。

        三条触发路径：切到本地 Ollama / 打开对话框时已是本地 /
        点「刷新本机模型」（刚 `ollama pull` 完不用重开）。
        """
        if not self._is_local_base():
            return
        api_base = (self.base_edit.text() or "").strip()
        self.refresh_models_btn.setEnabled(False)
        AsyncTaskManager.run(
            lambda: list_local_models(api_base),
            on_result=self._on_models_loaded,
            on_error=lambda err: self._on_models_loaded((False, [], str(err))),
        )

    def _on_models_loaded(self, result):
        ok, names, message = result
        self.refresh_models_btn.setEnabled(True)
        if not ok or not names:
            # 拿不到就说清楚怎么做，**不编造模型名**
            self.hint_label.setText(
                "⚠️ 没能读到本机模型列表。请确认已运行 `ollama serve`，"
                "并先拉一个模型，例如 `ollama pull qwen2.5:7b`，"
                "然后点右侧「刷新本机模型」。"
            )
            return

        current = self.model_combo.currentText().strip()
        self.model_combo.clear()
        self.model_combo.addItems(names)
        if current in names:
            # 用户填的模型本机确实有 → 尊重他的选择
            self.model_combo.setCurrentText(current)
        else:
            # 本机没有他填的那个（常见：预设写死的 qwen2.5）→ **换成第一个可用的**
            # 并在提示里说明换过，避免"我明明填了 qwen2.5 怎么变了"的困惑
            chosen = names[0]
            self.model_combo.setCurrentText(chosen)
            preset_hint = AI_PROVIDER_PRESETS[
                self.current_preset_key()
            ].get("hint", "")
            self.hint_label.setText(
                f"✅ 已列出本机已安装的 {len(names)} 个模型，"
                f"并自动选中「{chosen}」"
                + (f"（原「{current}」本机没有）" if current else "")
                + f"\n{preset_hint}"
            )

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
        # 切到"本地 Ollama"就自动列出本机已装模型 —— 这正是本批修的核心场景：
        # 预设里写死的 qwen2.5 在用户机器上通常没装，一测就是 HTTP 404。
        if preset == "ollama":
            self._refresh_model_list()

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
