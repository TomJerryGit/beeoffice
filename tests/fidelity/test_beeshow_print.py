# tests/fidelity/test_beeshow_print.py
"""
蜜演打印（P1-B ★★）：幻灯片 / 讲义 / 备注页 / 大纲。

## 为什么测试里不实例化 BeeShowView
蜜演是 QtWebEngine 应用，**本沙箱下实例化会崩**（仓库里已有 9 个这样的
exit-crash 文件）。所以测试用一个只混入 `ShowPrintMixin` 的**轻量替身**，
覆盖除"WebEngine 取图"之外的全部逻辑 —— 这也正是当初把架构分三层的用意。

## 三层各怎么验证
1. **排版计划**（`_build_print_plan`）：纯数据，直接断言分页/网格位置/备注/页码。
2. **绘制**（`_paint_plan`）：喂**合成的彩色 QImage**，渲染成 PDF，
   再用 PyMuPDF **逐像素**回读 —— 于是"第 N 张幻灯片是否落在第 N 格"
   可以真的被证明（不是看代码猜）。
3. **栅格化**（`_rasterize_slides`）：用 PyMuPDF 造彩色 PDF，
   断言 QPdfDocument 取出的图颜色正确 —— 这一步**不需要 WebEngine 也不需要字体**。

**唯一无法在此验证的是 `_slides_pdf()`（WebEngine 渲染）**：
只测它的**优雅失败**（组件不可用时要返回 False，绝不能静默变成空白打印）。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

fitz = pytest.importorskip("fitz", reason="需要 PyMuPDF 做像素级验证")

from beeoffice.plugins.beeshow_print_mixin import (              # noqa: E402
    HANDOUT_LAYOUTS, MODE_HANDOUT, MODE_NOTES, MODE_OUTLINE,
    MODE_SLIDES, ShowPrintMixin,
)


class FakeShow(ShowPrintMixin):
    """只带打印所需状态的替身（不碰 WebEngine）。"""

    def __init__(self, slide_count=3, notes=None, md=None):
        self._slides_html = ["<div>slide</div>"] * slide_count
        self._slides_md = (
            md if md is not None
            else [f"# 标题{i + 1}\n正文内容" for i in range(slide_count)]
        )
        self._speaker_notes = (
            notes if notes is not None else [""] * slide_count
        )


def _titles(show):
    return [show._print_slide_title(i) for i in range(show._print_slide_count())]


def _notes(show):
    return [show._print_notes(i) for i in range(show._print_slide_count())]


def _plan(show, mode=MODE_SLIDES, per_page=1):
    return show._build_print_plan(
        show._print_slide_count(), mode=mode, per_page=per_page,
        titles=_titles(show), notes=_notes(show),
    )


def make_pdf(path, colors):
    """造一份"每页一个纯色"的 PDF（替代 WebEngine 的产物）。"""
    document = fitz.open()
    for color in colors:
        page = document.new_page(width=400, height=300)
        rgb = tuple(c / 255 for c in color)
        page.draw_rect(fitz.Rect(0, 0, 400, 300), color=rgb, fill=rgb)
    document.save(str(path))
    document.close()
    return path


def page_pixel(pdf_path, page_index, x_ratio, y_ratio):
    """取某页某相对位置的像素（RGB 0-255）—— 用来验证"哪张图落在哪格"。"""
    document = fitz.open(str(pdf_path))
    try:
        page = document[page_index]
        pixmap = page.get_pixmap(dpi=72)
        x = int(pixmap.width * x_ratio)
        y = int(pixmap.height * y_ratio)
        return pixmap.pixel(x, y)
    finally:
        document.close()


RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
YELLOW = (255, 255, 0)


def _near(actual, expected, tolerance=40):
    return all(abs(a - e) <= tolerance for a, e in zip(actual, expected))


def _solid_image(color, w=120, h=90):
    from PySide6.QtGui import QColor, QImage

    image = QImage(w, h, QImage.Format.Format_RGB32)
    image.fill(QColor(*color))
    return image


# ==================== 1. 排版计划 ====================

def test_slides_mode_one_slide_per_page():
    show = FakeShow(slide_count=5)
    plan = _plan(show, MODE_SLIDES)

    assert len(plan["pages"]) == 5
    for page in plan["pages"]:
        assert len(page["items"]) == 1
        assert page["items"][0]["row"] == 0
        assert page["items"][0]["col"] == 0
    assert [p["items"][0]["slide"] for p in plan["pages"]] == [0, 1, 2, 3, 4]


def test_handout_grid_positions_are_correct():
    """讲义 4 张/页 → (0,0) (0,1) (1,0) (1,1)。"""
    show = FakeShow(slide_count=4)
    plan = _plan(show, MODE_HANDOUT, per_page=4)

    assert len(plan["pages"]) == 1
    assert plan["rows"] == 2 and plan["cols"] == 2
    positions = [(i["slide"], i["row"], i["col"]) for i in plan["pages"][0]["items"]]
    assert positions == [(0, 0, 0), (1, 0, 1), (2, 1, 0), (3, 1, 1)]


@pytest.mark.parametrize("per_page,expected", [
    (2, (1, 2)), (3, (1, 3)), (4, (2, 2)), (6, (2, 3)), (9, (3, 3)),
])
def test_handout_layouts_match_declared_grid(per_page, expected):
    show = FakeShow(slide_count=12)
    plan = _plan(show, MODE_HANDOUT, per_page=per_page)

    assert (plan["rows"], plan["cols"]) == expected
    assert plan["rows"] * plan["cols"] == per_page
    assert len(plan["pages"]) == -(-12 // per_page)


def test_handout_last_page_can_be_partial():
    show = FakeShow(slide_count=5)
    plan = _plan(show, MODE_HANDOUT, per_page=4)

    assert len(plan["pages"]) == 2
    assert len(plan["pages"][0]["items"]) == 4
    assert len(plan["pages"][1]["items"]) == 1
    assert plan["pages"][1]["items"][0]["slide"] == 4


def test_handout_invalid_per_page_falls_back_to_4():
    """每页张数非法时退回 4，不能崩。"""
    show = FakeShow(slide_count=6)
    plan = _plan(show, MODE_HANDOUT, per_page=7)

    assert (plan["rows"], plan["cols"]) == HANDOUT_LAYOUTS[4]


def test_notes_mode_one_page_per_slide_with_notes_text():
    show = FakeShow(slide_count=3, notes=["备注一", "", "备注三"])
    plan = _plan(show, MODE_NOTES)

    assert len(plan["pages"]) == 3
    assert [p["items"][0]["notes"] for p in plan["pages"]] == [
        "备注一", "", "备注三"
    ]
    assert plan["pages"][1]["items"][0]["title"] == "标题2"


def test_outline_mode_lists_all_slides_in_order():
    show = FakeShow(slide_count=40)
    plan = _plan(show, MODE_OUTLINE)

    lines = [line for page in plan["pages"] for line in page["outline_lines"]]
    assert [line["slide"] for line in lines] == list(range(40))
    assert lines[0]["title"] == "标题1"


def test_every_page_has_page_number():
    for mode, per_page in ((MODE_SLIDES, 1), (MODE_HANDOUT, 4),
                           (MODE_NOTES, 1), (MODE_OUTLINE, 1)):
        show = FakeShow(slide_count=7)
        plan = _plan(show, mode, per_page)
        total = len(plan["pages"])
        for page in plan["pages"]:
            assert page["footer_right"] == f"第 {page['page_no']} / {total} 页", (
                f"{mode} 第 {page['page_no']} 页页码不对"
            )


def test_empty_deck_plan_is_marked_empty():
    show = FakeShow(slide_count=0)
    plan = _plan(show, MODE_SLIDES)

    assert plan["empty"] is True
    assert plan["pages"] == []


def test_slide_title_strips_markdown_prefixes():
    show = FakeShow(3, md=["## 二级标题", "- 列表项", "> 引用文字"])
    assert _titles(show) == ["二级标题", "列表项", "引用文字"]


def test_notes_accessor_is_bounds_safe():
    show = FakeShow(2, notes=["只有一条"])
    assert show._print_notes(0) == "只有一条"
    assert show._print_notes(1) == ""
    assert show._print_notes(99) == ""


# ==================== 2. 绘制：像素级验证网格 ====================

def _render_plan(qtbot, tmp_path, plan, images, landscape=True):
    from PySide6.QtGui import QPageLayout, QPageSize
    from PySide6.QtPrintSupport import QPrinter

    out = tmp_path / "out.pdf"
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(out))
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    printer.setPageOrientation(
        QPageLayout.Orientation.Landscape if landscape
        else QPageLayout.Orientation.Portrait
    )
    ShowPrintMixin._paint_plan(printer, plan, images)
    return out


def test_handout_places_correct_slide_in_correct_cell(qtbot, tmp_path):
    """
    **核心验证**：讲义 4 张/页时，第 1/2/3/4 张要分别落在左上/右上/左下/右下。

    做法：给 4 张不同颜色的合成图，渲染后**逐像素回读**四格中心。
    第 1 张图放红、第 2 绿、第 3 蓝、第 4 黄 —— 位置错了颜色就对不上。
    """
    show = FakeShow(slide_count=4)
    plan = _plan(show, MODE_HANDOUT, per_page=4)
    images = {
        0: _solid_image(RED), 1: _solid_image(GREEN),
        2: _solid_image(BLUE), 3: _solid_image(YELLOW),
    }
    out = _render_plan(qtbot, tmp_path, plan, images)

    quadrants = {
        "左上": (RED, 0.30, 0.30),
        "右上": (GREEN, 0.70, 0.30),
        "左下": (BLUE, 0.30, 0.66),
        "右下": (YELLOW, 0.70, 0.66),
    }
    for name, (expected, xr, yr) in quadrants.items():
        actual = page_pixel(out, 0, xr, yr)
        assert _near(actual, expected), (
            f"{name}格颜色 {actual} ≠ 期望 {expected}（幻灯片摆错位置了）"
        )


def test_slides_mode_renders_each_slide_on_its_own_page(qtbot, tmp_path):
    show = FakeShow(slide_count=3)
    plan = _plan(show, MODE_SLIDES)
    images = {0: _solid_image(RED), 1: _solid_image(GREEN),
              2: _solid_image(BLUE)}
    out = _render_plan(qtbot, tmp_path, plan, images)

    document = fitz.open(str(out))
    try:
        assert document.page_count == 3
    finally:
        document.close()
    assert _near(page_pixel(out, 0, 0.5, 0.5), RED)
    assert _near(page_pixel(out, 1, 0.5, 0.5), GREEN)
    assert _near(page_pixel(out, 2, 0.5, 0.5), BLUE)


def test_notes_page_puts_thumbnail_on_top(qtbot, tmp_path):
    """备注页：上半是幻灯片缩略图（应是该张的颜色），下半是备注区。"""
    show = FakeShow(slide_count=2, notes=["这是备注内容", "第二条备注"])
    plan = _plan(show, MODE_NOTES)
    images = {0: _solid_image(GREEN), 1: _solid_image(BLUE)}
    out = _render_plan(qtbot, tmp_path, plan, images)

    # 第 1 页缩略图区域（上部）应为绿色
    assert _near(page_pixel(out, 0, 0.5, 0.25), GREEN), (
        "备注页上半没有第 1 张幻灯片的画面"
    )
    # 第 2 页应为蓝色
    assert _near(page_pixel(out, 1, 0.5, 0.25), BLUE)


def test_missing_image_draws_placeholder_not_blank(qtbot, tmp_path):
    """
    取图失败时必须画占位框（可见的边框），**不能静默留白** ——
    否则用户会以为"这页本来就没内容"。
    """
    show = FakeShow(slide_count=1)
    plan = _plan(show, MODE_SLIDES)
    out = _render_plan(qtbot, tmp_path, plan, images={})

    # 边框是灰色；中心应为白底（未被图片覆盖），但页面上必须有非白像素（边框）
    document = fitz.open(str(out))
    try:
        pixmap = document[0].get_pixmap(dpi=72)
        non_white = 0
        for y in range(0, pixmap.height, 4):
            for x in range(0, pixmap.width, 4):
                pixel = pixmap.pixel(x, y)
                if not all(channel > 230 for channel in pixel):
                    non_white += 1
    finally:
        document.close()
    assert non_white > 50, "缺图时页面上什么都没有（占位框没画出来）"


def test_empty_deck_renders_notice_page(qtbot, tmp_path):
    show = FakeShow(slide_count=0)
    plan = _plan(show, MODE_SLIDES)
    out = _render_plan(qtbot, tmp_path, plan, images={})

    document = fitz.open(str(out))
    try:
        assert document.page_count >= 1
    finally:
        document.close()


# ==================== 3. 栅格化（不依赖 WebEngine/字体）====================

def test_rasterize_reads_each_page_with_right_color(tmp_path):
    """QPdfDocument 取图：页数与颜色都要对（这一步是讲义拼版的数据来源）。"""
    pdf = make_pdf(tmp_path / "slides.pdf", [RED, GREEN, BLUE])

    images = ShowPrintMixin._rasterize_slides(pdf, width=120)

    assert len(images) == 3, f"取到 {len(images)} 张，应为 3 张"
    for image, expected in zip(images, [RED, GREEN, BLUE]):
        assert not image.isNull()
        center = image.pixelColor(image.width() // 2, image.height() // 2)
        actual = (center.red(), center.green(), center.blue())
        assert _near(actual, expected), f"颜色 {actual} ≠ {expected}"


def test_rasterize_keeps_slide_aspect_ratio(tmp_path):
    """幻灯片是横向的，取出的图也应保持横向（否则讲义排版会变形）。"""
    pdf = make_pdf(tmp_path / "wide.pdf", [RED])

    image = ShowPrintMixin._rasterize_slides(pdf, width=200)[0]

    assert image.width() == 200
    assert image.height() < image.width(), "宽高比丢了（400×300 的页应比宽矮）"


def test_rasterize_bad_path_returns_empty(tmp_path):
    """坏路径不能抛异常（打印入口要给出自己的提示）。"""
    images = ShowPrintMixin._rasterize_slides(tmp_path / "不存在.pdf", width=80)

    assert images == []


# ==================== 4. WebEngine 层的优雅失败 ====================

def test_slides_pdf_returns_false_without_webengine(monkeypatch, tmp_path):
    """
    **唯一依赖 WebEngine 的一层**：组件不可用时必须返回 False，
    让调用方弹出明确提示 —— 绝不能静默变成空白打印。

    本沙箱装不了 WebEngine 渲染，所以这里模拟"导入失败"，
    验证的是**失败路径的行为**，而不是渲染本身。
    """
    import builtins

    show = FakeShow(slide_count=2)
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if "WebEngineWidgets" in name:
            raise ImportError("模拟：WebEngine 不可用")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert show._slides_pdf(tmp_path / "x.pdf") is False


def test_slides_pdf_returns_false_for_empty_deck(tmp_path):
    show = FakeShow(slide_count=0)
    assert show._slides_pdf(tmp_path / "x.pdf") is False


# ==================== 5. 打印选项解析 ====================

@pytest.mark.parametrize("choice,expected", [
    ("讲义（每页多张）：6 张", (MODE_HANDOUT, 6)),
    ("讲义（每页多张）：2 张", (MODE_HANDOUT, 2)),
    ("幻灯片（每页 1 张）", (MODE_SLIDES, 1)),
    ("备注页（幻灯片 + 备注）", (MODE_NOTES, 1)),
    ("大纲（仅文字）", (MODE_OUTLINE, 1)),
])
def test_ask_print_options_parsing(monkeypatch, choice, expected):
    from PySide6.QtWidgets import QInputDialog

    from beeoffice.plugins import beeshow_print_mixin as module

    monkeypatch.setattr(
        QInputDialog, "getItem",
        staticmethod(lambda *a, **k: (choice, True)),
    )
    assert module._ask_print_options(None) == expected


def test_ask_print_options_cancel_returns_none(monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    from beeoffice.plugins import beeshow_print_mixin as module

    monkeypatch.setattr(
        QInputDialog, "getItem", staticmethod(lambda *a, **k: ("", False))
    )
    assert module._ask_print_options(None) == (None, None)
