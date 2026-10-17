# tests/qt/test_beewrite_ai_mixin.py
"""beewrite_ai_mixin.py 测试：蜜写 AI 辅助"""
import pytest
from PySide6.QtGui import QTextCursor


@pytest.fixture
def editor(beewrite_editor):
    return beewrite_editor


class TestAIMenu:
    def test_show_ai_menu_exists(self, editor):
        assert hasattr(editor, "_show_ai_menu")
        assert callable(editor._show_ai_menu)


class TestAIContinue:
    def test_continue_in_markdown(self, editor, monkeypatch):
        editor._switch_mode("markdown")
        editor.markdown_editor.setPlainText("人工智能正在改变世界。")
        cursor = editor.markdown_editor.textCursor()
        cursor.movePosition(QTextCursor.End)
        editor.markdown_editor.setTextCursor(cursor)
        before = editor.markdown_editor.toPlainText()
        editor._ai_continue()
        after = editor.markdown_editor.toPlainText()
        assert len(after) > len(before)

    def test_continue_empty(self, editor):
        editor._switch_mode("markdown")
        editor.markdown_editor.setPlainText("")
        editor._ai_continue()
        # 不应崩


class TestAIPolish:
    def test_polish_no_selection(self, editor, monkeypatch):
        from PySide6.QtWidgets import QMessageBox
        infos = []
        monkeypatch.setattr(
            QMessageBox, "information",
            staticmethod(lambda *a, **k: infos.append(a)),
        )
        editor._switch_mode("markdown")
        editor.markdown_editor.setPlainText("测试内容。")
        editor._ai_polish()
        assert infos, "无选中文字时应提示"

    def test_polish_with_selection(self, editor):
        editor._switch_mode("markdown")
        editor.markdown_editor.setPlainText("然后这个东西其实很好")
        from PySide6.QtGui import QTextCursor
        cursor = editor.markdown_editor.textCursor()
        cursor.select(QTextCursor.Document)
        editor.markdown_editor.setTextCursor(cursor)
        editor._ai_polish()
        # 不应崩


class TestAISummarize:
    def test_summarize_too_short(self, editor, monkeypatch):
        from PySide6.QtWidgets import QMessageBox
        infos = []
        monkeypatch.setattr(
            QMessageBox, "information",
            staticmethod(lambda *a, **k: infos.append(a)),
        )
        editor._switch_mode("markdown")
        editor.markdown_editor.setPlainText("短文本。")
        editor._ai_summarize()
        assert infos, "文本太短时应提示"

    def test_summarize_long(self, editor):
        editor._switch_mode("markdown")
        long_text = "这是一句话。" * 30
        editor.markdown_editor.setPlainText(long_text)
        before = editor.markdown_editor.toPlainText()
        editor._ai_summarize()
        after = editor.markdown_editor.toPlainText()
        assert len(after) >= len(before)


class TestAIKeywords:
    def test_keywords_too_short(self, editor, monkeypatch):
        from PySide6.QtWidgets import QMessageBox
        infos = []
        monkeypatch.setattr(
            QMessageBox, "information",
            staticmethod(lambda *a, **k: infos.append(a)),
        )
        editor._switch_mode("markdown")
        editor.markdown_editor.setPlainText("短。")
        editor._ai_keywords()
        assert infos

    def test_keywords_long(self, editor):
        editor._switch_mode("markdown")
        editor.markdown_editor.setPlainText(
            "蜜蜂办公是一款办公软件，办公软件需要稳定。" * 3
        )
        before = editor.markdown_editor.toPlainText()
        editor._ai_keywords()
        after = editor.markdown_editor.toPlainText()
        assert len(after) >= len(before)
