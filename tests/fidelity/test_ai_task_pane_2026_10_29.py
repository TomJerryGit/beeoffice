# tests/fidelity/test_ai_task_pane_2026_10_29.py
"""S1：AI 任务窗格 MVP（不访问网络）。"""
from types import SimpleNamespace

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QTextEdit

from beeoffice.plugins.ai_task_pane import (
    AiTaskPane,
    build_action_prompt,
    build_qa_prompt,
)


class _FakeTabManager:
    def __init__(self, widget):
        self._widget = widget

    def currentWidget(self):
        return self._widget


class _FakeApp:
    def __init__(self, editor=None):
        self.tab_manager = _FakeTabManager(
            SimpleNamespace(rich_editor=editor) if editor is not None else None
        )
        self.settings = None


def test_prompt_builders():
    assert "改写" in build_action_prompt("rewrite", "原句")
    assert "英文" in build_action_prompt("translate", "原句")
    assert build_action_prompt("summarize", "正文").startswith("请用要点")
    prompt = build_qa_prompt("文档正文", "问题")
    assert "文档正文" in prompt and "问题" in prompt
    assert "只根据" in prompt


def test_selection_and_document_text(qtbot):
    editor = QTextEdit()
    qtbot.addWidget(editor)
    editor.setPlainText("第一段\n第二段")
    pane = AiTaskPane(_FakeApp(editor))
    qtbot.addWidget(pane)
    assert pane._document_text() == "第一段\n第二段"
    assert pane._selection_text() == ""
    cursor = editor.textCursor()
    cursor.select(QTextCursor.Document)
    editor.setTextCursor(cursor)
    assert "第一段" in pane._selection_text()


def test_action_without_selection_shows_hint(qtbot):
    pane = AiTaskPane(_FakeApp(QTextEdit()))
    qtbot.addWidget(pane)
    pane._run_action("rewrite")
    assert "请先在编辑器中选中" in pane.output.toPlainText()


def test_question_empty_shows_hint(qtbot):
    pane = AiTaskPane(_FakeApp(QTextEdit()))
    qtbot.addWidget(pane)
    pane._run_question()
    assert "请先输入问题" in pane.output.toPlainText()
