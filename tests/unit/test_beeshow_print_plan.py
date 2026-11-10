"""BeeShow 打印排版计划纯数据补测。"""
from beeoffice.plugins.beeshow_print_mixin import (
    HANDOUT_LAYOUTS,
    MODE_HANDOUT,
    MODE_NOTES,
    MODE_OUTLINE,
    MODE_SLIDES,
    ShowPrintMixin,
)


def test_slides_plan():
    plan = ShowPrintMixin._build_print_plan(3)
    assert plan["mode"] == MODE_SLIDES
    assert plan["slide_count"] == 3
    assert plan["empty"] is False
    assert len(plan["pages"]) == 3
    assert len(plan["pages"][0]["items"]) == 1


def test_handout_plans():
    for per_page in HANDOUT_LAYOUTS:
        plan = ShowPrintMixin._build_print_plan(
            10, mode=MODE_HANDOUT, per_page=per_page
        )
        rows, cols = HANDOUT_LAYOUTS[per_page]
        assert plan["rows"] == rows and plan["cols"] == cols
        assert len(plan["pages"]) >= 1
        assert len(plan["pages"][0]["items"]) <= per_page


def test_notes_plan():
    plan = ShowPrintMixin._build_print_plan(
        2, mode=MODE_NOTES,
        titles=["标题一", "标题二"],
        notes=["备注一", ""],
    )
    assert plan["mode"] == MODE_NOTES
    assert len(plan["pages"]) == 2
    item = plan["pages"][0]["items"][0]
    assert item["title"] == "标题一"
    assert item["notes"] == "备注一"


def test_outline_plan():
    plan = ShowPrintMixin._build_print_plan(
        2, mode=MODE_OUTLINE,
        titles=["A", "B"], notes=["x", "y"],
    )
    assert plan["mode"] == MODE_OUTLINE
    lines = plan["pages"][0]["outline_lines"]
    assert lines[0]["title"] == "A"


def test_empty_and_invalid():
    plan = ShowPrintMixin._build_print_plan(0)
    assert plan["empty"] is True
    assert plan["pages"] == []
    plan2 = ShowPrintMixin._build_print_plan(3, mode="unknown")
    assert plan2["mode"] == "unknown"


def test_title_notes_count_helpers():
    obj = ShowPrintMixin()
    obj._slides_html = ["a", "b"]
    obj._speaker_notes = ["n1", None]
    obj._slides_md = ["# 标题一\n正文", "", "### 三"]
    assert obj._print_slide_count() == 2
    assert obj._print_notes(0) == "n1"
    assert obj._print_notes(1) == ""
    assert obj._print_notes(9) == ""
    assert obj._print_slide_title(0) == "标题一"
    assert obj._print_slide_title(1) == "第 2 张"
    assert obj._print_slide_title(2) == "三"
