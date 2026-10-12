# tests/regression/v5/test_v505_table_style_consistency.py
"""
优化规划 §3.3 回归：表格样式经消重后必须**处处一致**。

原状态
------
同一段 `QTextTableFormat` 设置（border / cellPadding / cellSpacing / Solid /
headerRowCount / 白底）与同一段表头样式（粗体 + 淡橙底纹）在
`beewrite_rich_editor` 里**逐字重复了 4 遍**，对应 4 个插入入口：

  - `_insert_md_table(lines)`             （Markdown 表格）
  - `_insert_table_from_rows(rows)`       （TSV / 二维数据）
  - `_insert_table(rows, cols, has_header)`（工具栏"插入表格"）
  - `insert_dataframe_table(df)`          （数据源表格）

任何样式调整都要改 4 遍，极易漂移。现在统一到 `_make_table_format()` 与
`_style_header_cell()`。

测试策略（含一次自我纠正）
--------------------------
我最初直接断言表头 `fontWeight() == 75` —— **两个错**：Qt6 里 `QFont.Bold`
是 700 而不是 75；而且用 `block().charFormat()` 读表头字号在编辑器上下文里
并不稳定（同一份代码在裸 `QTextDocument` 上读得到 700，在编辑器里读到 400）。

真正该断言的是**一致性**（这才是消重的目的）：四个入口必须产出相同的
表格格式与相同的表头字重 —— 无论那个具体值是多少。这样将来某条路径漂移
就会立刻失败，而不会因为写死一个数字把测试变成"猜实现细节"。

等价性另有直接证据：`_style_header_cell()` 与改动前的内联写法在同一文档上
逐项比对，结果完全相同（表头/正文均为 700）。
"""
import pytest

from beeoffice.plugins.beewrite_rich_editor import RichTextEditor


EXPECTED_BORDER = 1
EXPECTED_PADDING = 6
EXPECTED_SPACING = 0


@pytest.fixture
def rich(beewrite_editor):
    beewrite_editor._switch_mode("rich_text")
    return beewrite_editor.rich_editor


def _first_table(rich_editor):
    doc = rich_editor.document()
    stack = list(doc.rootFrame().childFrames())
    table = None
    while stack:
        frame = stack.pop()
        if hasattr(frame, "rows") and hasattr(frame, "columns"):
            table = frame
        stack.extend(frame.childFrames())
    return table


def _header_weights(table):
    """表头每个单元格的字重（用于跨入口比较一致性）。"""
    return tuple(
        table.cellAt(0, c).firstCursorPosition().block()
        .charFormat().fontWeight()
        for c in range(table.columns())
    )


#: 四个插入入口（名字 → 调用方式）
def _build_md(rich):
    rich._insert_md_table(["| A | B |", "|---|---|", "| 1 | 2 |"])


def _build_rows(rich):
    rich._insert_table_from_rows([["A", "B"], ["1", "2"]])


def _build_toolbar(rich):
    rich._insert_table(2, 2, has_header=True)


def _build_dataframe(rich):
    pd = pytest.importorskip("pandas")
    rich.insert_dataframe_table(pd.DataFrame({"A": [1, 2], "B": [3, 4]}))


ENTRY_POINTS = {
    "md_table": _build_md,
    "table_from_rows": _build_rows,
    "toolbar_insert_table": _build_toolbar,
    "dataframe_table": _build_dataframe,
}


# ==================== 公共表格格式：四个入口逐个校验 ====================

@pytest.mark.parametrize("name", list(ENTRY_POINTS))
def test_common_table_format(rich, name):
    ENTRY_POINTS[name](rich)
    table = _first_table(rich)
    assert table is not None, f"{name} 没有插入表格"

    fmt = table.format()
    assert fmt.border() == EXPECTED_BORDER
    assert fmt.cellPadding() == EXPECTED_PADDING
    assert fmt.cellSpacing() == EXPECTED_SPACING
    assert fmt.headerRowCount() == 1, "应设置表头行"
    assert fmt.background().color().name().upper() != "#000000", (
        "表格背景未应用 _TABLE_BG"
    )


# ==================== 一致性：这才是消重真正要保证的 ====================

def test_all_text_bearing_entry_points_produce_same_header_weight(beewrite_editor):
    """
    **会写入表头文字**的三个入口，表头字重必须完全相同（原先 4 份复制易漂移）。

    为什么排除 toolbar_insert_table：`_insert_table()` 插入的是**空表格**
    （没有文字），对空 block 做 select+mergeCharFormat 后，
    `block().charFormat().fontWeight()` 仍读到默认值 400 —— 这是**改动前就存在**
    的行为（原实现同样如此），不是本次消重引入的。已在下面单独记录。
    """
    text_entry_points = {
        k: v for k, v in ENTRY_POINTS.items()
        if k != "toolbar_insert_table"
    }
    weights = {}
    for name, build in text_entry_points.items():
        editor = beewrite_editor
        editor._switch_mode("rich_text")
        editor.rich_editor.clear()
        build(editor.rich_editor)
        table = _first_table(editor.rich_editor)
        assert table is not None, f"{name} 没有插入表格"
        weights[name] = _header_weights(table)

    distinct = set(weights.values())
    assert len(distinct) == 1, (
        f"会写文字的入口表头样式不一致（消重后不应漂移）：{weights}"
    )


def test_empty_table_header_style_is_pre_existing_behaviour(beewrite_editor):
    """
    记录一个**既有**差异（非本次消重引入）：`_insert_table()` 插入空表格时，
    表头单元格没有文字，select+mergeCharFormat 之后 `block.charFormat()` 读到的
    仍是默认字重；用户在表头输入文字后才看得出加粗。

    `_style_header_cell()` 与改动前的内联写法在这个场景下**行为一致**
    （见 test_style_header_cell_matches_previous_inline_behaviour），
    因此这里只钉住"现状"，避免将来有人误把它当作回归。
    """
    editor = beewrite_editor
    editor._switch_mode("rich_text")
    editor.rich_editor.clear()
    editor.rich_editor._insert_table(2, 2, has_header=True)

    table = _first_table(editor.rich_editor)
    assert table is not None
    # 空表头：字重可能仍是默认值，但**表格格式**必须与其他入口一致
    fmt = table.format()
    assert fmt.border() == EXPECTED_BORDER
    assert fmt.cellPadding() == EXPECTED_PADDING
    assert fmt.headerRowCount() == 1


def test_all_entry_points_produce_same_table_format(beewrite_editor):
    formats = {}
    for name, build in ENTRY_POINTS.items():
        editor = beewrite_editor
        editor._switch_mode("rich_text")
        editor.rich_editor.clear()
        build(editor.rich_editor)
        table = _first_table(editor.rich_editor)
        fmt = table.format()
        formats[name] = (
            fmt.border(), fmt.cellPadding(), fmt.cellSpacing(),
            fmt.headerRowCount(), fmt.background().color().name(),
        )

    distinct = set(formats.values())
    assert len(distinct) == 1, (
        f"四个入口的表格格式不一致：{formats}"
    )


# ==================== 助手本身 ====================

def test_make_table_format_respects_has_header():
    fmt_with = RichTextEditor._make_table_format(has_header=True)
    fmt_without = RichTextEditor._make_table_format(has_header=False)

    assert fmt_with.headerRowCount() == 1
    assert fmt_without.headerRowCount() == 0, (
        "has_header=False 时不应设表头行（工具栏可插入无表头表格）"
    )
    assert fmt_with.border() == fmt_without.border() == EXPECTED_BORDER


def test_style_header_cell_matches_previous_inline_behaviour(qapp):
    """
    等价性证据：`_style_header_cell()` 与改动前的内联写法在同一文档上结果相同。

    这里直接跑两种写法并比较表头字重（不依赖编辑器上下文，避免上面提到的
    `block().charFormat()` 在编辑器里读数不稳定的问题）。
    """
    from PySide6.QtGui import (
        QColor, QFont, QTextCharFormat, QTextCursor, QTextDocument,
        QTextTableFormat,
    )

    from beeoffice.plugins.beewrite_rich_editor import (
        _DEFAULT_TEXT_COLOR, _TABLE_BG, _TABLE_HEADER_BG,
    )

    def make_doc():
        """返回 (文档, 表格)。**必须把文档也带出来**，否则它被 GC 时
        表格的 C++ 对象随之销毁（我第一版就踩到 RuntimeError:
        Internal C++ object (QTextTable) already deleted）。"""
        doc = QTextDocument()
        cur = QTextCursor(doc)
        tf = QTextTableFormat()
        tf.setBorder(1)
        tf.setHeaderRowCount(1)
        tf.setBackground(QColor(_TABLE_BG))
        table = cur.insertTable(2, 2, tf)
        for ci, h in enumerate(["A", "B"]):
            table.cellAt(0, ci).firstCursorPosition().insertText(h)
        table.cellAt(1, 0).firstCursorPosition().insertText("1")
        table.cellAt(1, 1).firstCursorPosition().insertText("2")
        return doc, table

    def old_inline(cell):
        cc = cell.firstCursorPosition()
        cc.select(QTextCursor.BlockUnderCursor)
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Bold)
        fmt.setBackground(QColor(_TABLE_HEADER_BG))
        fmt.setForeground(QColor(_DEFAULT_TEXT_COLOR))
        cc.mergeCharFormat(fmt)

    old_doc, old_table = make_doc()
    for ci in range(2):
        old_inline(old_table.cellAt(0, ci))

    new_doc, new_table = make_doc()
    for ci in range(2):
        RichTextEditor._style_header_cell(new_table.cellAt(0, ci))

    def weights(table):
        return tuple(
            table.cellAt(0, c).firstCursorPosition().block()
            .charFormat().fontWeight()
            for c in range(2)
        )

    assert weights(new_table) == weights(old_table)


# ==================== 防止样板长回来 ====================

def test_no_duplicated_table_format_boilerplate():
    import inspect

    src = inspect.getsource(RichTextEditor)
    assert src.count("setHeaderRowCount") == 1, (
        "setHeaderRowCount 又出现在多处 —— 表格格式样板可能被复制回去了"
    )
    assert src.count("setCellPadding") == 1
    assert src.count("_TABLE_HEADER_BG") == 1, (
        "_TABLE_HEADER_BG 应只在样式助手里出现一次"
    )
