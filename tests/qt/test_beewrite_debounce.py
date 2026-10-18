# -*- coding: utf-8 -*-
"""
蜜写内容变化信号防抖（P1-26）

缺陷：
    富文本编辑器每次按键都 emit `contentChanged`，
    下游收到信号会把整篇文档序列化一遍（富文本 → Markdown）。
    长文档连续打字时，这部分开销乘以按键数，肉眼可见地卡。

修复：
    300ms 防抖——连续输入只在停手后通知一次。
    `content()` 仍是按需计算，所以**不会丢数据**，只是把通知频率降下来。

本文件锁定：
    1. 连续输入期间不立刻发信号
    2. 停手后只发一次（不是每次按键一次）
    3. 两种编辑模式都生效
"""
import pytest

pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture
def editor(qtbot):
    from beeoffice.plugins.beewrite import BeeWriteEditor

    ed = BeeWriteEditor()
    qtbot.addWidget(ed)
    yield ed
    try:
        ed.close()
    except Exception:
        pass


def test_markdown_typing_is_debounced(qtbot, editor):
    if editor._edit_mode != "markdown":
        editor._switch_mode("markdown")

    emits = []
    editor.contentChanged.connect(lambda: emits.append(1))

    editor.markdown_editor.insertPlainText("abcdef")
    # 刚输入完不应该立刻发信号
    assert emits == [], f"输入后立刻触发了 {len(emits)} 次信号"

    qtbot.wait(450)
    assert len(emits) == 1, f"停手 450ms 后应为 1 次，实际 {len(emits)} 次"


def test_rich_typing_is_debounced(qtbot, editor):
    editor._switch_mode("rich_text")

    emits = []
    editor.contentChanged.connect(lambda: emits.append(1))

    cursor = editor.rich_editor.textCursor()
    for ch in "12345":
        cursor.insertText(ch)

    assert emits == [], "富文本输入后不应立刻发信号"

    qtbot.wait(450)
    assert len(emits) == 1, f"停手后应为 1 次，实际 {len(emits)} 次"


def test_content_is_still_correct_after_debounce(qtbot, editor):
    """防抖只影响通知频率，内容必须立刻可取。"""
    editor._switch_mode("markdown")
    editor.markdown_editor.setPlainText("即时内容")
    assert "即时内容" in editor.content()
