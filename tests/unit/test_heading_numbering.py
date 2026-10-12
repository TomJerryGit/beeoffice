# tests/unit/test_heading_numbering.py
"""
优化规划 §3.3 消重回归：标题编号统一为唯一实现。

原状态
------
同一段"多级计数器"算法在两个文件里**逐字重复**：

  - `beewrite_crossref.CrossRefManager.scan_headings()`
  - `beewrite_outline.OutlinePanel._scan_headings()`（Qt 分支）

两处都是 `counters = [0] * 6` → `counters[level-1] += 1` → 下级清零 →
`".".join(str(counters[i]) for i in range(level) if counters[i] > 0)`。
任何规则调整都要改两遍，且两处容易漂移（兜底分支就已经漂移成
`number` 恒为空串）。

现在统一到 `heading_numbering.HeadingNumberer`。
本文件既测纯函数边界，也测**两处调用点对同一层级序列产出一致**。
"""
import pytest

from beeoffice.plugins.heading_numbering import (
    MAX_HEADING_LEVEL,
    HeadingNumberer,
    numbers_for_levels,
)


# ==================== 编号规则 ====================

@pytest.mark.parametrize("levels,expected", [
    ([], []),
    ([1], ["1"]),
    ([1, 2], ["1", "1.1"]),
    ([1, 2, 3], ["1", "1.1", "1.1.1"]),
    ([1, 2, 2, 3], ["1", "1.1", "1.2", "1.2.1"]),
    # 同级递增
    ([1, 1], ["1", "2"]),
    ([1, 1, 1], ["1", "2", "3"]),
    # 回到上级后，下级计数清零
    ([1, 2, 1, 2], ["1", "1.1", "2", "2.1"]),
    ([1, 2, 3, 2], ["1", "1.1", "1.1.1", "1.2"]),
    # 跳到 2 级开始（没有 1 级）
    ([2], ["1"]),
    ([2, 2], ["1", "2"]),
    # 6 级上限
    ([1, 2, 3, 4, 5, 6],
     ["1", "1.1", "1.1.1", "1.1.1.1", "1.1.1.1.1", "1.1.1.1.1.1"]),
])
def test_numbering_rules(levels, expected):
    assert numbers_for_levels(levels) == expected


def test_illegal_levels_return_empty_string():
    """非法层级不计数、返回空串（调用方据此跳过）。"""
    assert numbers_for_levels([0]) == [""]
    assert numbers_for_levels([7]) == [""]
    assert numbers_for_levels([-1]) == [""]
    assert numbers_for_levels(["1"]) == [""]
    assert numbers_for_levels([None]) == [""]


def test_illegal_level_does_not_consume_counter():
    """非法层级不应影响后续合法层级的编号。"""
    assert numbers_for_levels([1, 99, 1]) == ["1", "", "2"]


def test_reset_restores_initial_state():
    n = HeadingNumberer()
    assert n.next_number(1) == "1"
    n.reset()
    assert n.next_number(1) == "1", "reset 后应重新从 1 开始"


def test_max_level_is_six():
    assert MAX_HEADING_LEVEL == 6


def test_custom_max_level():
    n = HeadingNumberer(max_level=3)
    assert n.next_number(3) == "1"
    assert n.next_number(4) == "", "超过自定义上限应返回空串"


# ==================== 两处调用点必须一致 ====================

def _crossref_numbers(levels):
    """用 CrossRefManager 的公开接口算编号（需要真实 QTextDocument）。"""
    from PySide6.QtGui import QTextBlockFormat, QTextCursor, QTextDocument

    from beeoffice.plugins.beewrite_crossref import CrossRefManager

    doc = QTextDocument()
    cursor = QTextCursor(doc)
    for level in levels:
        fmt = QTextBlockFormat()
        fmt.setHeadingLevel(level)
        cursor.setBlockFormat(fmt)
        cursor.insertText(f"标题{level}")
        cursor.insertBlock()
        cursor.setBlockFormat(QTextBlockFormat())

    class _FakeEditor:
        def __init__(self, d):
            self._d = d

        def document(self):
            return self._d

    return [
        h["number"]
        for h in CrossRefManager().scan_headings(_FakeEditor(doc))
    ]


def test_crossref_and_shared_module_agree(qapp):
    """crossref 的编号必须与共享模块完全一致（消重的核心保障）。"""
    levels = [1, 2, 2, 1, 2, 3]
    assert _crossref_numbers(levels) == numbers_for_levels(levels)


def test_outline_and_shared_module_agree(qapp):
    """
    outline 面板对 Markdown 文本的编号也必须与共享模块一致。

    同时这是一个**真实缺陷的回归**：Markdown 模式下 `QPlainTextEdit` 的
    `headingLevel()` 全为 0，改前这里会扫到 0 个标题（大纲面板空白）。
    """
    from PySide6.QtWidgets import QPlainTextEdit

    from beeoffice.plugins.beewrite_outline import OutlinePanel

    editor = QPlainTextEdit()
    editor.setPlainText("# 一\n\n## 一.一\n\n### 一.一.一\n\n正文\n\n## 一.二\n")

    panel = OutlinePanel()
    panel.set_editor(editor)
    headings = panel._scan_headings()

    assert len(headings) == 4, (
        f"Markdown 模式应扫到 4 个标题，实际 {len(headings)} —— "
        f"大纲面板在 Markdown 下为空是原缺陷"
    )
    assert [h["level"] for h in headings] == [1, 2, 3, 2]
    assert [h["number"] for h in headings] == numbers_for_levels([1, 2, 3, 2])
    assert [h["text"] for h in headings] == ["一", "一.一", "一.一.一", "一.二"]


def test_outline_positions_are_character_offsets(qapp):
    """
    `pos` 必须是**字符偏移**（与 Qt 分支的 block.position() 语义一致），
    否则点击大纲会跳到错误位置。原先兜底分支给的是行号。
    """
    from PySide6.QtWidgets import QPlainTextEdit

    from beeoffice.plugins.beewrite_outline import OutlinePanel

    text = "前言\n\n# 第一章\n\n正文\n\n# 第二章\n"
    editor = QPlainTextEdit()
    editor.setPlainText(text)

    panel = OutlinePanel()
    panel.set_editor(editor)
    headings = panel._scan_headings()

    assert len(headings) == 2
    for h in headings:
        # pos 指向标题**所在行的字符偏移**（含 `#` 标记），点击时跳到行首 ——
        # 与原 Qt 分支的 block.position() 语义一致。
        line = text[h["pos"]:].split("\n", 1)[0]
        assert line.lstrip("#").strip() == h["text"], (
            f"pos={h['pos']} 指向的行不是该标题所在行：{line!r}"
        )
        # 关键：必须是**字符偏移**而不是行号 —— 行号在这里会是 2 与 6
        assert text.index(line) == h["pos"], (
            f"pos={h['pos']} 不是该行的字符偏移（很可能是行号）"
        )


def test_outline_ignores_hash_inside_code_fence_marker(qapp):
    """不是标题的 `#`（行内井号、无空格）不应被当成标题。"""
    from PySide6.QtWidgets import QPlainTextEdit

    from beeoffice.plugins.beewrite_outline import OutlinePanel

    editor = QPlainTextEdit()
    editor.setPlainText("#真标题（无空格）\n\n# 真标题\n\n#### 四级\n")

    panel = OutlinePanel()
    panel.set_editor(editor)
    headings = panel._scan_headings()

    assert [h["text"] for h in headings] == ["真标题", "四级"]


def test_outline_with_no_headings(qapp):
    from PySide6.QtWidgets import QPlainTextEdit

    from beeoffice.plugins.beewrite_outline import OutlinePanel

    editor = QPlainTextEdit()
    editor.setPlainText("只有正文，没有标题\n第二行\n")
    panel = OutlinePanel()
    panel.set_editor(editor)
    assert panel._scan_headings() == []


def test_outline_without_editor(qapp):
    from beeoffice.plugins.beewrite_outline import OutlinePanel

    assert OutlinePanel()._scan_headings() == []
