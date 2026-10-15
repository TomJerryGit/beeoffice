# tests/fidelity/test_beesheet_print_fit.py
"""
R8：打印**缩放模式**（对齐 WPS 官方教程主推的"缩放到一页/适应 N 页"）。

## 验收标准（用户提出、可像素级验证）
选了「适应 1 页宽」后，**所有列的右边界都必须落在可打印区内**；
「缩放到 1 页」则**整表只有一页**。

## 怎么验（本环境无字体，所以不靠文字提取）
* **几何级**：`margin + sum(page["widths"]) <= margin + usable_w`
  —— 列宽本身就是设备像素，这条等价于"列没越界"；
* **设备级**：用真实 `QPrinter` 的几何（`_print_geometry`）算计划，
  断言每一带都能装进设备可用宽度；
* **不变量**：`PDF 实际页数 == 计划页数`（与字体无关，沿用既有做法）。

## 还有一条设计要点被测试钉住
"**等比缩放 ≠ 压列宽**"：`FIT_WIDTH` 走的是整体 `scale`
（列宽与行高一起缩），而不是把列宽单独挤扁 —— 后者会把文字挤坏。
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from beeoffice.plugins.beesheet_print_mixin import (                 # noqa: E402
    FIT_HEIGHT, FIT_LABELS, FIT_NONE, FIT_PAGE, FIT_WIDTH,
)

from test_beesheet_print import (                                    # noqa: E402
    _dataframe, _make_printer, _pdf_page_count, _render,
)


def _plan_with(view, fit, usable_w=186.0, usable_h=260.0, px=1.0,
               custom_scale=None):
    data = view._collect_print_data()
    return view._build_print_plan(
        data, usable_w, usable_h, px, fit=fit, custom_scale=custom_scale
    )


@pytest.fixture
def sheet(qtbot):
    from beeoffice.plugins.beesheet import BeeSheetView

    view = BeeSheetView()
    qtbot.addWidget(view)
    view.current_sheet_name = "测试表"
    view.model.set_full_dataframe(_dataframe(rows=120, cols=4))
    return view


# ==================== 1. 三种模式的基本行为 ====================

def test_fit_width_scales_columns_into_page(sheet):
    """**用户提出的验收标准**：适应 1 页宽后，所有列都在页内。"""
    plan = _plan_with(sheet, FIT_WIDTH)

    assert plan["scale"] <= 1.0
    assert sum(plan["widths"]) <= 186.0 + 1e-6, (
        f"列总宽 {sum(plan['widths']):.1f} 超出可用宽度 186.0"
    )
    # 每一页同样要在页内（横向分页时每页列不同）
    for page in plan["pages"]:
        assert sum(page["widths"]) <= 186.0 + 1e-6, page["page_no"]


def test_fit_page_puts_everything_on_one_page(sheet):
    """「缩放到 1 页」：整表（宽 + 高）只有一页。"""
    plan = _plan_with(sheet, FIT_PAGE)

    assert len(plan["pages"]) == 1, f"应为一页，实际 {len(plan['pages'])}"
    assert sum(plan["widths"]) <= 186.0 + 1e-6
    # 高度也要塞进去：表头 + 行 + 页脚 ≤ 可用高度
    needed = (plan["header_height"] + len(plan["pages"][0]["rows"])
              * plan["row_height"])
    assert needed <= 260.0 + 1e-6, f"内容高 {needed:.1f} 超出 260.0"


def test_fit_height_only_limits_height(sheet):
    plan = _plan_with(sheet, FIT_HEIGHT, usable_h=60.0)

    assert len(plan["pages"]) == 1, "适应 1 页高应把行压到一页"
    # 该模式不负责宽度 → 不做列缩放（scale 由高度决定，可能仍 < 1）
    assert plan["scale"] < 1.0


def test_fit_none_does_not_scale(sheet):
    """不缩放：列宽用自然宽度，`scale == 1`。"""
    plan = _plan_with(sheet, FIT_NONE, usable_w=1000.0)

    assert plan["scale"] == 1.0
    assert len(plan["bands"]) == 1


def test_custom_scale_is_applied(sheet):
    plan = _plan_with(sheet, FIT_WIDTH, custom_scale=0.5)

    assert plan["scale"] == pytest.approx(0.5)
    # ⚠️ 自然宽度**依赖 usable_w 的单位**（毫米 vs 设备像素），
    # 所以这里必须用同一个 usable_w 去算自然宽度，否则比较无意义。
    natural = sheet._natural_column_widths(
        sheet._collect_print_data(), usable_w=186.0
    )
    assert sum(plan["widths"]) == pytest.approx(sum(natural) * 0.5, rel=1e-6)


def test_custom_scale_is_clamped(sheet):
    """百分比要夹在合理范围（0.05–1.0），别让用户把内容缩成看不见。"""
    assert _plan_with(sheet, FIT_WIDTH, custom_scale=5.0)["scale"] == 1.0
    assert _plan_with(sheet, FIT_WIDTH, custom_scale=0.0)["scale"] == 0.05
    assert _plan_with(sheet, FIT_WIDTH, custom_scale="坏了")["scale"] == 1.0


def test_scaling_keeps_row_height_proportional(sheet):
    """**等比缩放**：行高要跟着缩 —— 只压列宽会把文字挤坏。"""
    normal = _plan_with(sheet, FIT_NONE, usable_w=1000.0)
    shrunk = _plan_with(sheet, FIT_PAGE)

    assert shrunk["scale"] < 1.0
    assert shrunk["row_height"] < normal["row_height"]
    assert shrunk["header_height"] < normal["header_height"]


# ==================== 2. 横向分页（"不缩放"下的正确定义）====================

def test_fit_none_splits_columns_across_pages(sheet):
    """
    列很宽又不缩放 → **按列横向分页**（而不是硬挤或丢列）。

    这是"不缩放"应有的行为：WPS 也是这么做的。
    """
    wide = _dataframe(rows=10, cols=30)
    sheet.model.set_full_dataframe(wide)

    plan = _plan_with(sheet, FIT_NONE, usable_w=120.0)

    assert len(plan["bands"]) > 1, plan["bands"]
    covered = [0] * len(wide.columns)
    for start, end in plan["bands"]:
        for index in range(start, end):
            covered[index] += 1
    assert all(count == 1 for count in covered), (
        f"列要**恰好**被覆盖一次，实际 {covered}"
    )


def test_every_band_fits_usable_width(sheet):
    wide = _dataframe(rows=10, cols=30)
    sheet.model.set_full_dataframe(wide)

    plan = _plan_with(sheet, FIT_NONE, usable_w=120.0)

    for page in plan["pages"]:
        assert sum(page["widths"]) <= 120.0 + 1e-6, (
            f"第 {page['page_no']} 页列宽 {sum(page['widths']):.1f} 越界"
        )


def test_banded_pages_carry_their_own_headers_and_cells(sheet):
    """横向分页后每页的**表头与单元格必须对应同一批列**（切错就全乱了）。"""
    wide = _dataframe(rows=10, cols=30)
    sheet.model.set_full_dataframe(wide)

    plan = _plan_with(sheet, FIT_NONE, usable_w=120.0)
    # 注意：打印表头是**列字母**（A/B/C…），不是 DataFrame 的列名 ——
    # 我第一版按列名断言，被测试当场纠正。
    all_headers = list(sheet._collect_print_data()["headers"])

    seen = []
    for page in plan["pages"]:
        start, end = page["col_start"], page["col_end"]
        assert page["headers"] == all_headers[start:end], page["page_no"]
        # 每页的行必须是 `(行号, [本页的单元格...])`
        for row in page["rows"]:
            number, values = row
            assert isinstance(number, int), row
            assert len(values) == end - start, (page["page_no"], row)
        seen.extend(range(start, end))
    assert sorted(seen) == list(range(len(all_headers)))


def test_banded_pages_footer_shows_column_range(sheet):
    """多带时页脚要写明"第几到第几列"，否则用户不知道这是续页。"""
    wide = _dataframe(rows=10, cols=30)
    sheet.model.set_full_dataframe(wide)

    plan = _plan_with(sheet, FIT_NONE, usable_w=120.0)

    assert any("列）" in p["footer_left"] for p in plan["pages"]), (
        [p["footer_left"] for p in plan["pages"]]
    )


def test_single_column_wider_than_page_still_fits(sheet):
    """某一列自己就比整页还宽时，也要能放进页内（否则永远放不下）。"""
    long_text = "很长的内容" * 60
    sheet.model.set_full_dataframe(pd.DataFrame({"超宽列": [long_text] * 5}))

    plan = _plan_with(sheet, FIT_NONE, usable_w=60.0)

    for page in plan["pages"]:
        assert sum(page["widths"]) <= 60.0 + 1e-6, page["page_no"]


# ==================== 3. 设备级验收（真实 QPrinter 几何）====================

@pytest.mark.parametrize("fit", [FIT_WIDTH, FIT_PAGE, FIT_HEIGHT, FIT_NONE])
def test_every_page_fits_device_geometry(sheet, fit):
    """
    **设备级**：用真实打印机的几何算计划，**每一页的列都不能越界**。

    这就是"选缩放到 1 页宽后所有列都在页内"的可测形式
    （单位都是设备像素，不需要字体）。
    """
    view_printer = _make_printer()

    from beeoffice.plugins.beesheet_print_mixin import SheetPrintMixin

    geom = sheet._print_geometry(view_printer)
    data = sheet._collect_print_data()
    plan = SheetPrintMixin._build_print_plan(
        data, geom["usable_w"], geom["body_h"], geom["px"], fit=fit
    )

    assert plan["pages"]
    for page in plan["pages"]:
        assert sum(page["widths"]) <= geom["usable_w"] + 1e-6, (
            f"fit={fit} 第 {page['page_no']} 页越界："
            f"{sum(page['widths']):.1f} > {geom['usable_w']:.1f}"
        )


@pytest.mark.parametrize("fit,expect_few", [
    (FIT_PAGE, True),        # 缩放到 1 页 → 页数应显著变少
    (FIT_NONE, False),
])
def test_pdf_page_count_matches_plan(qtbot, tmp_path, fit, expect_few):
    """
    **不变量**：PDF 实际页数 == 计划页数（与字体无关）。

    同时验证"缩放到 1 页"确实把页数压下来了（不是嘴上说说）。
    """
    from beeoffice.plugins.beesheet import BeeSheetView

    view = BeeSheetView()
    qtbot.addWidget(view)
    view.current_sheet_name = "大表"
    view.model.set_full_dataframe(_dataframe(rows=300, cols=4))
    view._print_fit = fit

    printer = _make_printer()
    geom = view._print_geometry(printer)
    plan = view._build_print_plan(
        view._collect_print_data(), geom["usable_w"], geom["body_h"],
        geom["px"], fit=fit,
    )

    path = tmp_path / f"fit_{fit}.pdf"
    _render(view, path)

    assert _pdf_page_count(path) == len(plan["pages"]), (
        f"计划 {len(plan['pages'])} 页，实际 "
        f"{_pdf_page_count(path)} 页"
    )
    view._print_fit = FIT_WIDTH
    normal = view._build_print_plan(
        view._collect_print_data(), geom["usable_w"], geom["body_h"],
        geom["px"], fit=FIT_WIDTH,
    )
    if expect_few:
        assert len(plan["pages"]) < len(normal["pages"]) or len(plan["pages"]) == 1
    view.close()


# ==================== 4. 界面接线 ====================

def test_fit_labels_cover_all_modes():
    keys = {key for key, _ in FIT_LABELS}
    assert keys == {FIT_PAGE, FIT_WIDTH, FIT_HEIGHT, FIT_NONE}
    assert FIT_WIDTH in keys


def test_render_uses_page_specific_widths(qtbot, tmp_path):
    """
    横向分页时渲染必须用**本页的列宽**（用整表列宽画会串列）。

    做法：给"很宽的 30 列"表用不缩放模式渲染，页数应 > 1 且与计划一致；
    并用"计划里每页列宽之和都 ≤ 可用宽度"约束住。
    """
    from beeoffice.plugins.beesheet import BeeSheetView

    view = BeeSheetView()
    qtbot.addWidget(view)
    view.current_sheet_name = "宽表"
    view.model.set_full_dataframe(_dataframe(rows=20, cols=30))
    view._print_fit = FIT_NONE

    path = tmp_path / "bands.pdf"
    _render(view, path, landscape=True)

    printer = _make_printer(landscape=True)
    geom = view._print_geometry(printer)
    plan = view._build_print_plan(
        view._collect_print_data(), geom["usable_w"], geom["body_h"],
        geom["px"], fit=FIT_NONE,
    )

    assert len(plan["bands"]) > 1, "30 列在 A4 横向下一页放不下，应当横向分页"
    assert _pdf_page_count(path) == len(plan["pages"])
    view._print_fit = FIT_WIDTH
    view.close()


def test_tiny_scale_is_disclosed_in_footer(sheet):
    """
    缩得太小要**在页脚说明**（"可能难以阅读"）—— 用户不该打印完才发现。

    （自动缩放不再夹 5% 下限，所以必须用提示来兜住"小到看不清"的情况。）
    """
    sheet.model.set_full_dataframe(_dataframe(rows=2000, cols=4))

    plan = _plan_with(sheet, FIT_PAGE)

    assert plan["scale"] < 0.35, plan["scale"]
    assert plan["tiny_scale"] is True
    assert any("可能难以阅读" in p["footer_left"] for p in plan["pages"]), (
        [p["footer_left"] for p in plan["pages"][:3]]
    )
