# beeoffice/plugins/ai_task_pane.py
"""AI 任务窗格 MVP（S1）。

能力：
- 对当前编辑器选区：改写 / 解释 / 翻译；
- 对当前文档：问答（取正文片段 + 问题）；
- 复用现有 AIClient（本地 Ollama / OpenAI 兼容），不在 UI 里读 Key。
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

ACTIONS = {
    "rewrite": "改写",
    "explain": "解释",
    "translate": "翻译成英文",
    "summarize": "摘要",
}


def build_action_prompt(action: str, text: str) -> str:
    text = text.strip()
    if action == "rewrite":
        return f"请改写以下文字，保持原意，语言简洁专业：\n\n{text}"
    if action == "explain":
        return f"请用通俗中文解释以下内容的含义：\n\n{text}"
    if action == "translate":
        return f"请把以下内容翻译成英文，保留原意：\n\n{text}"
    if action == "summarize":
        return f"请用要点总结以下内容：\n\n{text}"
    raise ValueError(f"未知 AI 动作: {action}")


def build_qa_prompt(document: str, question: str, limit: int = 6000) -> str:
    doc = (document or "").strip()[:limit]
    question = (question or "").strip()
    if not question:
        raise ValueError("问题不能为空")
    if not doc:
        return f"请回答这个问题：{question}"
    return (
        "请只根据下面文档内容回答问题；文档中没有的信息请明确说不知道。\n\n"
        f"【文档片段】\n{doc}\n\n【问题】\n{question}"
    )


class _AIWorker(QThread):
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, client, prompt: str, parent=None):
        super().__init__(parent)
        self._client = client
        self._prompt = prompt

    def run(self):
        try:
            reply = self._client.chat(
                self._prompt,
                system="你是 BeeOffice 的中文办公写作助手，回答直接、可执行。",
            )
            self.done.emit(str(reply or "").strip())
        except Exception as e:  # noqa: BLE001 - 错误展示给用户
            self.failed.emit(f"{type(e).__name__}: {e}")


class AiTaskPane(QWidget):
    """右侧 AI 助手面板。"""

    def __init__(self, app, client=None, parent=None):
        super().__init__(parent)
        self._app = app
        self._client = client
        self._worker = None

        title = QLabel("选中文字后点击操作；问答会读取当前文档片段。")
        title.setWordWrap(True)

        row = QHBoxLayout()
        self.buttons = {}
        for key, label in ACTIONS.items():
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, k=key: self._run_action(k))
            row.addWidget(btn)
            self.buttons[key] = btn
        row.addStretch()

        self.question_edit = QLineEdit()
        self.question_edit.setPlaceholderText("针对当前文档提问…")
        self.ask_btn = QPushButton("提问")
        self.ask_btn.clicked.connect(self._run_question)
        ask_row = QHBoxLayout()
        ask_row.addWidget(self.question_edit, 1)
        ask_row.addWidget(self.ask_btn)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("AI 结果会显示在这里")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(title)
        layout.addLayout(row)
        layout.addLayout(ask_row)
        layout.addWidget(self.output, 1)

    # ---------- 上下文 ----------
    def _current_widget(self):
        try:
            return self._app.tab_manager.currentWidget()
        except Exception:  # noqa: BLE001
            return None

    def _selection_text(self) -> str:
        widget = self._current_widget()
        for attr in ("rich_editor", "markdown_editor", "text_edit", "editor"):
            editor = getattr(widget, attr, None)
            if editor is not None and hasattr(editor, "textCursor"):
                text = editor.textCursor().selectedText().replace("\u2029", "\n")
                if text.strip():
                    return text
        return ""

    def _document_text(self) -> str:
        widget = self._current_widget()
        for attr in ("rich_editor", "markdown_editor", "text_edit", "editor"):
            editor = getattr(widget, attr, None)
            if editor is not None and hasattr(editor, "toPlainText"):
                text = editor.toPlainText().strip()
                if text:
                    return text
        return ""

    def _client_or_error(self):
        if self._client is not None:
            return self._client
        try:
            from beeoffice.plugins.ai_client import AIClient

            client = AIClient.from_settings(self._app.settings)
            if not client.available():
                self.output.setPlainText(
                    "AI 不可用：" + (client.unavailable_reason() or "请先在设置中配置 AI")
                )
                return None
            self._client = client
            return client
        except Exception as e:  # noqa: BLE001
            self.output.setPlainText(f"AI 初始化失败：{type(e).__name__}: {e}")
            return None

    # ---------- 执行 ----------
    def _run_action(self, action: str):
        text = self._selection_text()
        if not text:
            self.output.setPlainText("请先在编辑器中选中一段文字。")
            return
        self._start(build_action_prompt(action, text))

    def _run_question(self):
        question = self.question_edit.text().strip()
        if not question:
            self.output.setPlainText("请先输入问题。")
            return
        try:
            prompt = build_qa_prompt(self._document_text(), question)
        except ValueError as e:
            self.output.setPlainText(str(e))
            return
        self._start(prompt)

    def _start(self, prompt: str):
        client = self._client_or_error()
        if client is None:
            return
        self.output.setPlainText("AI 正在处理…")
        for btn in self.buttons.values():
            btn.setEnabled(False)
        self.ask_btn.setEnabled(False)
        self._worker = _AIWorker(client, prompt, self)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_done(self, text: str):
        self.output.setPlainText(text or "（AI 返回为空）")

    def _on_failed(self, error: str):
        self.output.setPlainText(f"AI 失败：{error}")

    def _on_finished(self):
        for btn in self.buttons.values():
            btn.setEnabled(True)
        self.ask_btn.setEnabled(True)
