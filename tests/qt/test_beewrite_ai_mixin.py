# tests/qt/test_beewrite_ai_mixin.py
"""
蜜写 AI 辅助的行为契约（**已按"不静默糊弄"重写**）。

## 为什么重写
这个文件原先断言"没配 AI 时 `_ai_continue()` 也会让文本变长" ——
那正是**旧行为**：所谓"AI 续写"其实是 `random.choice(12 条句库)`，
却提示"✅ AI 续写完成"（审计里明确列为"静默糊弄"）。
本会话把它改成了诚实契约：

    AI 可用           → 真 LLM，如实标注来源
    AI 不可用/失败    → **先说明原因并征求同意（默认「否」）**
                        同意后才给本地规则结果，并标注"不是 AI"
                        拒绝 → **什么都不做**

旧断言在新契约下不仅错，还会**挂死**（走到模态 `QMessageBox.question`）——
本文件因此加了一个 autouse fixture 拦截模态框，避免任何用例把测试进程挂住。
"""
import pytest
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QMessageBox


@pytest.fixture
def editor(beewrite_editor):
    return beewrite_editor


@pytest.fixture(autouse=True)
def _no_modal(monkeypatch):
    """
    **必须**拦截模态框：`_ask_use_local` 走的是 `QMessageBox.question`，
    真弹出来会把测试永久挂住（本文件原先就是这样挂死的）。
    """
    asked = []

    def fake_question(*args, **kwargs):
        asked.append(args[1] if len(args) > 1 else "")
        return QMessageBox.StandardButton.No          # 默认：拒绝本地兜底

    monkeypatch.setattr(QMessageBox, "question", staticmethod(fake_question))
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: None))
    return asked


def _select_all(editor):
    cursor = editor.markdown_editor.textCursor()
    cursor.select(QTextCursor.Document)
    editor.markdown_editor.setTextCursor(cursor)


class TestAIMenu:
    def test_show_ai_menu_exists(self, editor):
        assert hasattr(editor, "_show_ai_menu")
        assert callable(editor._show_ai_menu)


class TestAIContinue:
    def test_continue_asks_before_local_fallback(self, editor, _no_modal):
        """**核心契约**：没配 AI 时必须先征求同意（拒绝 → 不改内容、不撒谎）。"""
        editor._switch_mode("markdown")
        editor.markdown_editor.setPlainText("人工智能正在改变世界。")
        cursor = editor.markdown_editor.textCursor()
        cursor.movePosition(QTextCursor.End)
        editor.markdown_editor.setTextCursor(cursor)
        before = editor.markdown_editor.toPlainText()

        editor._ai_continue()

        assert _no_modal, "没有可用 AI 时应当先征求同意"
        assert editor.markdown_editor.toPlainText() == before, (
            "用户拒绝本地兜底后，内容不该被悄悄改动"
        )

    def test_continue_empty_document_does_not_hang(self, editor):
        editor._switch_mode("markdown")
        editor.markdown_editor.setPlainText("")
        editor._ai_continue()          # 不崩、不挂即通过


class TestAIPolish:
    def test_polish_no_selection_prompts(self, editor, monkeypatch):
        infos = []
        monkeypatch.setattr(
            QMessageBox, "information",
            staticmethod(lambda *a, **k: infos.append(a)),
        )
        editor._switch_mode("markdown")
        editor.markdown_editor.setPlainText("测试内容。")
        editor._ai_polish()
        assert infos, "无选中文字时应提示"

    def test_polish_with_selection_asks(self, editor, _no_modal):
        editor._switch_mode("markdown")
        editor.markdown_editor.setPlainText("然后这个东西其实很好")
        _select_all(editor)
        before = editor.markdown_editor.toPlainText()

        editor._ai_polish()

        assert _no_modal, "没有可用 AI 时应当先征求同意"
        assert editor.markdown_editor.toPlainText() == before


class TestAISummarize:
    def test_summarize_too_short_prompts(self, editor, monkeypatch):
        infos = []
        monkeypatch.setattr(
            QMessageBox, "information",
            staticmethod(lambda *a, **k: infos.append(a)),
        )
        editor._switch_mode("markdown")
        editor.markdown_editor.setPlainText("短文本。")
        editor._ai_summarize()
        assert infos, "文本太短时应提示"

    def test_summarize_long_asks(self, editor, _no_modal):
        editor._switch_mode("markdown")
        editor.markdown_editor.setPlainText("这是一句话。" * 30)
        before = editor.markdown_editor.toPlainText()

        editor._ai_summarize()

        assert _no_modal
        assert editor.markdown_editor.toPlainText() == before


class TestAIKeywords:
    def test_keywords_too_short_prompts(self, editor, monkeypatch):
        infos = []
        monkeypatch.setattr(
            QMessageBox, "information",
            staticmethod(lambda *a, **k: infos.append(a)),
        )
        editor._switch_mode("markdown")
        editor.markdown_editor.setPlainText("短。")
        editor._ai_keywords()
        assert infos

    def test_keywords_long_asks(self, editor, _no_modal):
        editor._switch_mode("markdown")
        editor.markdown_editor.setPlainText(
            "蜜蜂办公是一款办公软件，办公软件需要稳定。" * 3
        )
        before = editor.markdown_editor.toPlainText()

        editor._ai_keywords()

        assert _no_modal
        assert editor.markdown_editor.toPlainText() == before
