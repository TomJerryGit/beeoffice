# tests/regression/v5/test_v505_md_table_empty_cells.py
"""
优化规划 §3.3 回归：Markdown 表格解析必须保留**空单元格**。

原缺陷
------
Markdown 表格的解析在本仓库有两套写法，规则不一致：

- `beewrite_utils.parse_md_table()`（规范实现）
      cells = [c.strip() for c in s.strip("|").split("|")]
  → **保留**空单元格

- `beewrite_rich_editor._insert_md_table()`（自己又写了一套）
      cells = [c.strip() for c in line.split('|') if c.strip()]
  → **丢弃**空单元格

后果是"值错位"：`| 1 |  | 3 |` 会被解析成 `["1", "3"]`，
于是 `3` 被放进第 2 列 —— 用户看到的是数据被挪位（与阶段 1 修的蜜算
"插入列覆盖已有单元格"属于同一类静默数据损坏）。

修复：`_insert_md_table()` 改为复用 `parse_md_table()`（规范实现），
不再自己拼分裂规则。
"""
import pytest

from beeoffice.plugins.beewrite_utils import parse_md_table, render_md_table


TABLE_WITH_EMPTY = [
    "| 名称 | 备注 | 数量 |",
    "|---|---|---|",
    "| 甲 |  | 3 |",
    "| 乙 | 有备注 |  |",
]


@pytest.fixture
def editor(beewrite_editor):
    beewrite_editor._switch_mode("rich_text")
    return beewrite_editor


def _read_qt_table(rich_editor):
    """
    把编辑器里的 QTextTable 读成二维文本。

    注意：frame 挂在**文档根 frame** 下（`doc.rootFrame().childFrames()`）；
    `QTextBlock` 没有 `childFrames()`（我第一版就是这么写错的）。
    """
    doc = rich_editor.document()
    table = None
    stack = list(doc.rootFrame().childFrames())
    while stack:
        frame = stack.pop()
        if hasattr(frame, "rows") and hasattr(frame, "columns"):
            table = frame
        stack.extend(frame.childFrames())
    if table is None:
        return None
    out = []
    for r in range(table.rows()):
        row = []
        for c in range(table.columns()):
            row.append(table.cellAt(r, c).firstCursorPosition().block().text())
        out.append(row)
    return out


# ==================== 规范实现：pararlse_md_table 的既有行为 ====================

def test_parse_md_table_keeps_empty_cells():
    """钉住规范实现的行为（本文件后续以它为准）。"""
    rows = parse_md_table(TABLE_WITH_EMPTY)
    assert rows == [
        ["名称", "备注", "数量"],
        ["甲", "", "3"],
        ["乙", "有备注", ""],
    ]


def test_render_md_table_roundtrip_keeps_empty_cells():
    rows = parse_md_table(TABLE_WITH_EMPTY)
    again = parse_md_table(render_md_table(rows).split("\n"))
    assert again == rows


# ==================== 编辑器插入：空单元格不得导致值错位 ====================

def test_insert_md_table_preserves_column_alignment(editor):
    """
    核心回归：`| 1 |  | 3 |` 里 `3` 必须在第 3 列，不能因为空单元格被丢弃
    而左移到第 2 列。
    """
    editor.rich_editor._insert_md_table(TABLE_WITH_EMPTY)

    table = _read_qt_table(editor.rich_editor)
    assert table is not None, "没有插入表格"

    expected = [
        ["名称", "备注", "数量"],
        ["甲", "", "3"],
        ["乙", "有备注", ""],
    ]
    assert table == expected, (
        f"表格内容与规范解析不一致（很可能空单元格被丢弃导致错位）:\n"
        f"实际: {table}\n期望: {expected}"
    )


def test_insert_md_table_column_count_matches_header(editor):
    editor.rich_editor._insert_md_table(TABLE_WITH_EMPTY)
    table = _read_qt_table(editor.rich_editor)
    assert len(table[0]) == 3
    for row in table:
        assert len(row) == 3, f"每行列数应与表头一致: {row}"


def test_insert_md_table_without_empty_cells_still_works(editor):
    """没有空单元格的普通表格行为不变。"""
    editor.rich_editor._insert_md_table([
        "| A | B |",
        "|---|---|",
        "| 1 | 2 |",
    ])
    table = _read_qt_table(editor.rich_editor)
    assert table == [["A", "B"], ["1", "2"]]


def test_insert_md_table_without_separator_row(editor):
    """没有分隔行时也应能插入（原实现有 ds 判定）。"""
    editor.rich_editor._insert_md_table([
        "| A | B |",
        "| 1 | 2 |",
    ])
    table = _read_qt_table(editor.rich_editor)
    assert table is not None
    assert table[0] == ["A", "B"]


def test_insert_md_table_too_few_lines_does_nothing(editor):
    editor.rich_editor._insert_md_table(["| A | B |"])
    assert _read_qt_table(editor.rich_editor) is None


def test_insert_md_table_trailing_empty_cell(editor):
    """行尾空单元格同样不能丢（否则列数变少）。"""
    editor.rich_editor._insert_md_table([
        "| A | B | C |",
        "|---|---|---|",
        "| 1 | 2 |  |",
    ])
    table = _read_qt_table(editor.rich_editor)
    assert table[1] == ["1", "2", ""], f"行尾空单元格丢失: {table[1]}"
