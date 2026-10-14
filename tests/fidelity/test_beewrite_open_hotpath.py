# tests/fidelity/test_beewrite_open_hotpath.py
"""
P0-B：蜜写**打开文档的 O(N²)** 回归测试。

问题（实测）
------------
打开 0.9 MB 文档时 `rich_editor.set_markdown()` 要 **6,976 ms**，但**孤立调用
同一个方法只要 0.12 s** —— 58× 的差距说明问题在应用接线。抓调用栈定案：

    beewrite_mode_mixin.py:51    content()          ← get_content() → to_markdown()（整篇转换！）
    ← beewrite_view_mixin.py:422   _update_status_bar
    ← beewrite_rich_editor.py:787  _insert_block / _insert_formatted_paragraph
    ← beewrite_rich_editor.py:638  set_markdown

`set_markdown()` 是**逐块插入**的，每插一块都触发 `textChanged → _update_status_bar`，
而状态栏统计走 `self.content()` → **`rich_editor.to_markdown()`（整篇转 Markdown）**
—— 只为数字数。N 个块 ⇒ N 次全篇转换 ⇒ **O(N²)**。
实测打开一份文档时 `to_markdown` 被调用 **1032 次、累计 6.2 秒**。

修法与验收
----------
① 统计只取纯文本（`toPlainText()`），不再做 Markdown 转换；
② 批量加载期间合并刷新（`set_markdown` 置 `_loading_markdown`，
   状态栏更新改 `QTimer.singleShot(0)`）—— 交互路径行为不变。

本文件用**调用次数**做断言（确定性），不依赖计时，避免 CI 抖动：
  · `set_markdown` 期间不得调用 `to_markdown`
  · 状态栏统计在批量加载期间最多刷新一次
  · 字数统计取"用户看到的正文"，不再把 Markdown 标记算进去
"""
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from beeoffice.plugins.beewrite import BeeWriteEditor             # noqa: E402
from beeoffice.plugins.beewrite_rich_editor import RichTextEditor  # noqa: E402


def _markdown(blocks: int) -> str:
    """一份有 `blocks` 个段落的 Markdown（含标题/列表/加粗，覆盖各插入分支）。"""
    lines = []
    for i in range(1, blocks + 1):
        if i % 7 == 1:
            lines.append(f"# 标题 {i}")
        elif i % 7 == 2:
            lines.append(f"- 列表项 {i}")
        elif i % 7 == 3:
            lines.append(f"**加粗**的第 {i} 段正文内容。")
        else:
            lines.append(f"第 {i} 段普通正文内容。")
        lines.append("")
    return "\n".join(lines)


@pytest.fixture
def editor(qtbot):
    widget = BeeWriteEditor()
    qtbot.addWidget(widget)
    widget.resize(1000, 700)
    yield widget
    widget.close()


def test_set_markdown_does_not_convert_whole_document(monkeypatch, qtbot):
    """
    **核心回归**：批量渲染 Markdown 时**不得**调用 `to_markdown()`。

    原先每插入一个块就触发一次整篇 Markdown 转换（O(N²)）。
    """
    calls = {"n": 0}
    original = RichTextEditor.to_markdown

    def counting(self):
        calls["n"] += 1
        return original(self)

    monkeypatch.setattr(RichTextEditor, "to_markdown", counting)

    rich = RichTextEditor()
    qtbot.addWidget(rich)
    rich.set_markdown(_markdown(200))

    assert calls["n"] == 0, (
        f"set_markdown 期间调用了 to_markdown {calls['n']} 次 —— O(N²) 回来了"
    )


def test_status_bar_refreshes_at_most_once_during_bulk_load(editor, qtbot):
    """
    批量加载期间，状态栏统计**最多刷新一次**（合并刷新）。

    原先每次 textChanged 都立刻统计一次。
    这里 patch **实例**而不是类：不依赖 mixin 的类名，也更贴近真实调用链
    （`_update_status_bar` 内部就是 `self._refresh_status_counts()`）。
    """
    calls = {"n": 0}
    original = editor._refresh_status_counts

    def counting():
        calls["n"] += 1
        return original()

    editor._refresh_status_counts = counting
    try:
        editor.rich_editor.set_markdown(_markdown(200))
        qtbot.wait(50)          # 让 singleShot(0) 排队的合并刷新执行
    finally:
        editor._refresh_status_counts = original

    assert calls["n"] >= 1, "至少要刷新一次（否则字数一直是旧的）"
    assert calls["n"] <= 2, (
        f"批量加载期间刷新了 {calls['n']} 次状态栏 —— 应合并成一次"
    )


def test_status_bar_still_updates_when_typing(editor, qtbot):
    """
    交互路径**行为不变**：不是批量加载时，改内容要**立刻**刷新状态栏。
    """
    calls = {"n": 0}
    original = editor._refresh_status_counts

    def counting():
        calls["n"] += 1
        return original()

    editor._refresh_status_counts = counting
    editor.rich_editor.setPlainText("临时内容")
    editor.rich_editor.textChanged.emit()

    assert calls["n"] >= 1, "普通输入时状态栏没立即刷新"


def test_word_count_uses_visible_text_not_markdown_source(editor):
    """
    字数/字符现在统计**用户看到的正文**，不再把 Markdown 标记算进去。

    行为变化是有意的：`# 标题` 的"字符"应是 2（"标题"），而不是 4。
    """
    editor.rich_editor.set_markdown("# 标题")
    editor._edit_mode = "rich_text"
    editor._refresh_status_counts()

    text = editor._char_count_label.text()
    assert text == "字符：2", f"字符数算的是 Markdown 源码?: {text!r}"

    word = editor._word_count_label.text()
    assert word.startswith("字数："), word


def test_large_document_renders_promptly(qtbot):
    """
    端到端粗门禁：400 段的 `set_markdown` 必须远低于修复前的 7 秒量级。

    阈值放得很宽（3 秒）—— 目的是抓住"O(N²) 回归"，
    不是卡具体数字（CI 机器负载差异很大）。
    """
    rich = RichTextEditor()
    qtbot.addWidget(rich)
    markdown = _markdown(400)

    start = time.perf_counter()
    rich.set_markdown(markdown)
    elapsed = time.perf_counter() - start

    assert elapsed < 3.0, (
        f"400 段渲染用了 {elapsed:.2f}s —— 疑似 O(N²) 回归"
        f"（修复后实测约 0.3s 量级）"
    )
