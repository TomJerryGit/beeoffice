# tests/test_p2_regression/test_p1_15_ai_fallback.py
"""
P1-15 回归：AI 续写/润色/总结 fallback 应作用于当前活动编辑器。

背景：
  beeoffice/plugins/beewrite_plugin.py 的 ai_continue / ai_polish /
  ai_summarize 三个 fallback 方法，原实现直接访问 editor.editor，
  而 editor.editor 属性始终返回 markdown_editor，
  导致富文本模式下 AI 功能作用在错误的控件上（往隐藏的
  Markdown 编辑器写入内容）。

修复：
  fallback 改用 editor._get_active_editor()，根据 _edit_mode
  返回正确的编辑器。

测试策略：
  1. 用 monkeypatch.delattr 从 AIMixin 移除 _ai_* 方法，
     强制 plugin 走 fallback 分支
  2. 构造真实 BeeWriteEditor，切到富文本模式
  3. 调 plugin.ai_continue() 等
  4. 断言：富文本编辑器内容变化，markdown 编辑器内容不变
"""
import pytest


# ==================== 辅助 ====================

def _make_plugin_with(editor):
    """构造一个 BeeWritePlugin，其 parent.tab_manager.currentWidget 返回 editor。"""
    from beeoffice.plugins.beewrite_plugin import BeeWritePlugin

    class _FakeTabManager:
        def currentWidget(self):
            return editor

    class _FakeParent:
        def __init__(self):
            self.tab_manager = _FakeTabManager()

        def set_global_status(self, *args, **kwargs):
            pass

    return BeeWritePlugin(parent=_FakeParent())


@pytest.fixture
def beewrite_in_rich_mode(beewrite_editor):
    """切到富文本模式的 BeeWriteEditor。"""
    from PySide6.QtGui import QTextCursor

    beewrite_editor._switch_mode("rich_text")
    beewrite_editor.rich_editor.setPlainText(
        "这是一段用于测试的文本内容。"
    )
    cursor = beewrite_editor.rich_editor.textCursor()
    cursor.movePosition(QTextCursor.End)
    beewrite_editor.rich_editor.setTextCursor(cursor)
    return beewrite_editor


# ==================== ai_continue ====================

def test_ai_continue_fallback_targets_rich_editor(
    beewrite_in_rich_mode, monkeypatch
):
    """P1-15：AI 续写 fallback 在富文本模式下应作用于 rich_editor。"""
    from beeoffice.plugins.beewrite_ai_mixin import AIMixin

    monkeypatch.delattr(AIMixin, "_ai_continue", raising=False)

    editor = beewrite_in_rich_mode
    plugin = _make_plugin_with(editor)

    rich_before = editor.rich_editor.toPlainText()
    md_before = editor.markdown_editor.toPlainText()

    plugin.ai_continue()

    rich_after = editor.rich_editor.toPlainText()
    md_after = editor.markdown_editor.toPlainText()

    assert rich_after != rich_before, (
        "P1-15：AI 续写 fallback 应作用于富文本编辑器（rich_editor），"
        "但富文本内容未变化"
    )
    assert md_after == md_before, (
        "P1-15：AI 续写 fallback 不应作用于 Markdown 编辑器。"
        "实际 markdown_editor 内容被修改了"
    )


# ==================== ai_polish ====================

def test_ai_polish_fallback_targets_rich_editor(
    beewrite_in_rich_mode, monkeypatch
):
    """P1-15：AI 润色 fallback 在富文本模式下应作用于 rich_editor。"""
    from beeoffice.plugins.beewrite_ai_mixin import AIMixin
    from PySide6.QtGui import QTextCursor

    monkeypatch.delattr(AIMixin, "_ai_polish", raising=False)

    editor = beewrite_in_rich_mode
    # 全选内容
    cursor = editor.rich_editor.textCursor()
    cursor.select(QTextCursor.Document)
    editor.rich_editor.setTextCursor(cursor)

    plugin = _make_plugin_with(editor)

    md_before = editor.markdown_editor.toPlainText()

    plugin.ai_polish()

    md_after = editor.markdown_editor.toPlainText()

    assert md_after == md_before, (
        "P1-15：AI 润色 fallback 不应作用于 Markdown 编辑器"
    )


# ==================== ai_summarize ====================

def test_ai_summarize_fallback_targets_rich_editor(
    beewrite_in_rich_mode, monkeypatch
):
    """P1-15：AI 总结 fallback 在富文本模式下应作用于 rich_editor。"""
    from beeoffice.plugins.beewrite_ai_mixin import AIMixin

    monkeypatch.delattr(AIMixin, "_ai_summarize", raising=False)

    editor = beewrite_in_rich_mode
    # 放足够长的内容以触发总结
    long_text = "这是一段测试文本。" * 20
    editor.rich_editor.setPlainText(long_text)

    plugin = _make_plugin_with(editor)

    rich_before = editor.rich_editor.toPlainText()
    md_before = editor.markdown_editor.toPlainText()

    plugin.ai_summarize()

    rich_after = editor.rich_editor.toPlainText()
    md_after = editor.markdown_editor.toPlainText()

    assert rich_after != rich_before, (
        "P1-15：AI 总结 fallback 应向富文本编辑器追加内容"
    )
    assert md_after == md_before, (
        "P1-15：AI 总结 fallback 不应作用于 Markdown 编辑器"
    )