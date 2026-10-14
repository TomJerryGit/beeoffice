# tests/fidelity/test_beesheet_print.py
"""
蜜算打印（P1-B ★★★）。

背景：实机清点发现打印只实现在蜜写，**蜜算 0 处** —— 表格打印是办公刚需。

## 怎么验证打印（换了两次方法，值得记下来）

1. 原计划：渲染成 PDF 再用 PyMuPDF **提取文字**断言。
   → **行不通**：本环境 Qt **一个字体都没有**
     （`QFontDatabase.families()` 返回 **0**，`PySide6/lib/fonts` 不存在），
     PDF 与栅格输出**都画不出字** —— 连蜜写原有的 `QTextDocument.print_()`
     也一样，文字提取恒为空。**这是环境问题，不是打印代码的问题。**
2. 改为**架构上分离**：排版决策放进纯数据 `_build_print_plan()`
   （分页/重复标题行/页脚/截断/列宽/对齐），测试**直接断言这些数据**，
   完全不依赖字体。
3. 绘制与计划的一致性，用**与字体无关的不变量**锁住：
   **PDF 实际页数 == 计划页数**。

于是本文件的覆盖是：排版计划（详尽）+ 渲染不崩且页数一致（冒烟）。
**字形/字体的最终观感只能由人眼确认** —— 已在报告里如实写出。
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

fitz = pytest.importorskip("fitz", reason="需要 PyMuPDF 校验 PDF 页数")


@pytest.fixture
def sheet(qtbot):
    from beeoffice.plugins.beesheet import BeeSheetView

    view = BeeSheetView()
    qtbot.addWidget(view)
    view.resize(1100, 700)
    yield view
    view.close()


def _dataframe(rows=120, cols=4):
    return pd.DataFrame({
        f"列{i}": [f"值{r}-{i}" for r in range(1, rows + 1)]
        for i in range(1, cols + 1)
    })


def _make_printer(path=None, landscape=False):
    """
    造打印设备。

    ⚠️ 计划与渲染**必须用同一台**：我第一次给"算计划"用的打印机**没设 PDF 输出**，
    而渲染用的设了 —— 两者分辨率/可用区不同 → 每页行数不同 → 页数对不上。
    （PDF 设备与普通设备的 `resolution()` 不一样。）
    """
    from PySide6.QtGui import QPageLayout, QPageSize
    from PySide6.QtPrintSupport import QPrinter

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    printer.setPageOrientation(
        QPageLayout.Orientation.Landscape if landscape
        else QPageLayout.Orientation.Portrait
    )
    if path is not None:
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(path))
    return printer


def _plan(view, printer):
    """用**给定打印设备**的几何生成排版计划（与渲染同源）。"""
    geom = view._print_geometry(printer)
    data = view._collect_print_data()
    return view._build_print_plan(
        data, geom["usable_w"], geom["body_h"], geom["px"]
    )


def _default_plan(view):
    """不指定设备时的计划（用于纯排版断言）。"""
    return _plan(view, _make_printer())


def _render(view, path, landscape=False):
    printer = _make_printer(path, landscape=landscape)
    view._render_sheet_to(printer)
    return path


def _pdf_page_count(path):
    doc = fitz.open(str(path))
    try:
        return doc.page_count
    finally:
        doc.close()


# ==================== 1. 排版计划：分页 ====================

def test_plan_paginates_large_sheet(sheet):
    sheet.model.set_full_dataframe(_dataframe(rows=300))
    plan = _default_plan(sheet)

    assert len(plan["pages"]) >= 2, f"只排出 {len(plan['pages'])} 页"
    # 每页行数不能超过容量，且总和 = 数据行数
    total = sum(len(p["rows"]) for p in plan["pages"])
    assert total == 300, f"分页后总行数 {total} ≠ 300"


def test_plan_small_sheet_is_single_page(sheet):
    sheet.model.set_full_dataframe(_dataframe(rows=5))
    plan = _default_plan(sheet)

    assert len(plan["pages"]) == 1
    assert len(plan["pages"][0]["rows"]) == 5


def test_plan_row_numbers_are_1_based_and_continuous(sheet):
    """行号必须连续且从 1 开始 —— 打印稿靠它和屏幕对号。"""
    sheet.model.set_full_dataframe(_dataframe(rows=300))
    plan = _default_plan(sheet)

    numbers = [no for page in plan["pages"] for no, _ in page["rows"]]
    assert numbers == list(range(1, 301)), f"行号不连续: {numbers[:8]}…"


# ==================== 2. 排版计划：重复标题行 ====================

def test_plan_repeats_header_row_on_later_pages(sheet):
    """
    **跨页重复标题行**（表格打印最实用的一项）。

    非首页应当额外带 `repeat_header_row`，内容 = 数据区第一行。
    """
    sheet.model.set_full_dataframe(_dataframe(rows=300))
    plan = _default_plan(sheet)

    assert len(plan["pages"]) >= 2
    assert plan["pages"][0]["repeat_header_row"] is None, (
        "首页不该重复（它本来就含第一行）"
    )
    for page in plan["pages"][1:]:
        assert page["repeat_header_row"] is not None, (
            f"第 {page['page_no']} 页没有重复标题行"
        )
        row_no, values = page["repeat_header_row"]
        assert row_no == 1
        assert values[0] == "值1-1"


# ==================== 3. 排版计划：页眉页脚与列标 ====================

def test_plan_has_column_headers(sheet):
    sheet.current_sheet_name = "销售数据"
    sheet.model.set_full_dataframe(_dataframe(rows=10, cols=4))
    plan = _default_plan(sheet)

    assert plan["pages"][0]["headers"] == ["A", "B", "C", "D"]


def test_plan_has_page_numbers(sheet):
    sheet.model.set_full_dataframe(_dataframe(rows=300))
    plan = _default_plan(sheet)

    total = len(plan["pages"])
    for page in plan["pages"]:
        assert page["footer_right"] == f"第 {page['page_no']} / {total} 页"


def test_plan_title_only_on_first_page(sheet):
    sheet.current_sheet_name = "销售数据"
    sheet.model.set_full_dataframe(_dataframe(rows=300))
    plan = _default_plan(sheet)

    assert plan["pages"][0]["title"] == "销售数据"
    assert all(p["title"] == "" for p in plan["pages"][1:])


def test_plan_footer_mentions_truncation_on_last_page(sheet):
    from beeoffice.plugins.beesheet_print_mixin import MAX_PRINT_ROWS

    sheet.current_sheet_name = "大表"
    sheet.model.set_full_dataframe(_dataframe(rows=MAX_PRINT_ROWS + 25))
    plan = _default_plan(sheet)

    assert "已截断 25 行" in plan["pages"][-1]["footer_left"]
    assert all("已截断" not in p["footer_left"]
               for p in plan["pages"][:-1]), "截断说明只该出现在最后一页"


# ==================== 4. 取数：已用区域 / 选区 / 截断 ====================

def test_used_range_excludes_padding_rows(sheet):
    """
    **实测踩过的坑**：`set_full_dataframe` 会把数据**补齐到默认行数**，
    若直接拿 `len(df)` 当已用区域，一张 2 行的表会打印出上千行空白
    （我第一版实测导出 **24 页**）。
    """
    sheet.model.set_full_dataframe(_dataframe(rows=2, cols=2))
    data = sheet._collect_print_data()

    assert len(data["rows"]) == 2, (
        f"把补齐用的空行也当成数据了：{len(data['rows'])} 行"
    )
    assert len(data["headers"]) == 2


def test_only_selection_is_printed(sheet):
    """选中多格时只打印选区。"""
    from PySide6.QtCore import QItemSelection, QItemSelectionModel

    sheet.model.set_full_dataframe(_dataframe(rows=50, cols=4))
    model = sheet.model
    selection = QItemSelectionModel(model)
    selection.select(
        QItemSelection(model.index(9, 0), model.index(11, 1)),
        QItemSelectionModel.SelectionFlag.ClearAndSelect,
    )
    sheet.table_view.setSelectionModel(selection)

    data = sheet._collect_print_data()

    assert [no for no, _ in data["rows"]] == [10, 11, 12]
    assert len(data["headers"]) == 2, (
        f"选区只有 2 列，却取了 {data['headers']}"
    )


def test_single_cell_selection_prints_whole_used_range(sheet):
    """只选中一个格子时不该"只打印一个格子"，应按已用区域打印。"""
    from PySide6.QtCore import QItemSelection, QItemSelectionModel

    sheet.model.set_full_dataframe(_dataframe(rows=10, cols=3))
    model = sheet.model
    selection = QItemSelectionModel(model)
    selection.select(
        QItemSelection(model.index(2, 1), model.index(2, 1)),
        QItemSelectionModel.SelectionFlag.ClearAndSelect,
    )
    sheet.table_view.setSelectionModel(selection)

    data = sheet._collect_print_data()

    assert len(data["rows"]) == 10


def test_row_count_is_truncated_for_huge_sheet(sheet):
    from beeoffice.plugins.beesheet_print_mixin import MAX_PRINT_ROWS

    sheet.model.set_full_dataframe(_dataframe(rows=MAX_PRINT_ROWS + 30))
    data = sheet._collect_print_data()

    assert len(data["rows"]) == MAX_PRINT_ROWS
    assert data["truncated"] == 30


def test_empty_sheet_gives_empty_plan(sheet):
    sheet.model.set_full_dataframe(pd.DataFrame())
    plan = _default_plan(sheet)

    assert plan["empty"] is True
    assert plan["pages"] == [] or plan["pages"][0]["rows"] == []


# ==================== 5. 列宽与对齐 ====================

def test_column_widths_fit_usable_width(sheet):
    sheet.model.set_full_dataframe(_dataframe(rows=30, cols=30))

    data = sheet._collect_print_data()
    widths = sheet._compute_column_widths(data, usable_w=180.0)

    assert widths, "没算出列宽"
    assert sum(widths) <= 180.0 + 0.01, f"列宽总和 {sum(widths)} 超出可用宽度"


def test_column_widths_never_degenerate(sheet):
    """列宽必须为正 —— 否则 Qt 画矩形会报警且不可见。"""
    sheet.model.set_full_dataframe(_dataframe(rows=10, cols=60))
    plan = _default_plan(sheet)

    assert all(w > 0 for w in plan["widths"]), plan["widths"]


def test_numeric_detection_for_right_alignment(sheet):
    assert sheet._looks_numeric("1234.5")
    assert sheet._looks_numeric("1,234")
    assert sheet._looks_numeric("¥1,234.00")
    assert sheet._looks_numeric("12%")
    assert not sheet._looks_numeric("abc")
    assert not sheet._looks_numeric("")


# ==================== 6. 渲染：不崩 + 页数一致（与字体无关的不变量）====

def test_render_to_pdf_does_not_crash(sheet, tmp_path):
    sheet.model.set_full_dataframe(_dataframe(rows=20))
    out = _render(sheet, tmp_path / "a.pdf")

    assert out.exists() and out.stat().st_size > 500


def test_rendered_page_count_matches_plan(sheet, tmp_path):
    """
    **把绘制与计划锁在一起**：PDF 实际页数必须等于计划页数。

    这条不依赖字体，所以在本环境（0 字体）也能跑，
    能抓住"计划分 3 页、实际只画了 1 页"这类错误。

    ⚠️ 计划与渲染**必须用同一台打印设备**：PDF 设备与普通设备的
    `resolution()` 不同 → 可用区不同 → 每页行数不同。
    我第一次就是拿"没设 PDF 输出的打印机"算计划、"设了 PDF 输出的"渲染，
    于是 400 行 = 计划 10 页 vs 实际 11 页，被这条不变量抓出来。
    """
    sheet.model.set_full_dataframe(_dataframe(rows=400))
    out = tmp_path / "pages.pdf"
    printer = _make_printer(out)
    expected = len(_plan(sheet, printer)["pages"])

    sheet._render_sheet_to(printer)

    assert _pdf_page_count(out) == expected, (
        f"计划 {expected} 页，实际渲染 {_pdf_page_count(out)} 页"
    )


def test_empty_sheet_renders_one_page(sheet, tmp_path):
    sheet.model.set_full_dataframe(pd.DataFrame())
    out = _render(sheet, tmp_path / "empty.pdf")

    assert _pdf_page_count(out) >= 1


def test_wide_sheet_renders_landscape_without_crash(sheet, tmp_path):
    sheet.model.set_full_dataframe(_dataframe(rows=5, cols=25))
    out = _render(sheet, tmp_path / "wide.pdf", landscape=True)

    assert _pdf_page_count(out) >= 1
    # 横向页应该比纵向宽
    doc = fitz.open(str(out))
    try:
        rect = doc[0].rect
        assert rect.width > rect.height, f"横向页尺寸异常: {rect}"
    finally:
        doc.close()
