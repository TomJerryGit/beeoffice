"""BeeShow PPTX 引擎纯逻辑/生成补测。"""
from pathlib import Path

import pytest

from beeoffice.plugins.beeshow_pptx_engine import (
    ElementMeasurer,
    MeasuredElement,
    MeasuredSlide,
    PPTXEngine,
    PPTXGenerator,
    selector_matches,
)


def test_normalize_color_and_measure_result():
    m = ElementMeasurer()
    assert m._normalize_color("") == ""
    assert m._normalize_color("#AABBCC") == "#AABBCC"
    assert m._normalize_color("rgb(255, 0, 128)") == "#FF0080"
    assert m._normalize_color("rgba(1,2,3,0.5)") == "#010203"
    assert m._normalize_color("bad") == ""

    slide = m._parse_measure_result(
        [{"tag": "h1", "text": "标题", "x": 10, "y": 20,
          "width": 100, "height": 40, "font_size": "24",
          "color": "rgb(0,0,0)", "bold": True}],
        "rgb(255,255,255)",
    )
    assert isinstance(slide, MeasuredSlide)
    assert slide.bg_color == "#FFFFFF"
    assert len(slide.elements) == 1
    assert slide.elements[0].tag == "h1"
    assert slide.elements[0].font_size == 24.0
    assert slide.elements[0].bold is True


def test_selector_matches():
    el = MeasuredElement(tag="p", element_id="intro", class_name="lead big")
    assert selector_matches(el, "p")
    assert selector_matches(el, "#intro")
    assert selector_matches(el, ".lead")
    assert selector_matches(el, "p.lead")
    assert not selector_matches(el, "h1")
    assert not selector_matches(el, "")


def test_px_to_emu():
    g = PPTXGenerator()
    assert g._px_to_emu(1280) == 9144000
    assert g._px_to_emu(0) == 0


def test_generate_pptx(tmp_path):
    g = PPTXGenerator()
    slide = MeasuredSlide(
        elements=[
            MeasuredElement(tag="h1", text="标题", x=10, y=10,
                            width=300, height=60, font_size=28),
            MeasuredElement(tag="p", text="正文内容", x=10, y=90,
                            width=400, height=40, font_size=16),
            MeasuredElement(tag="rect", x=0, y=0, width=1280, height=20,
                            bg_color="#FFB300"),
        ],
        bg_color="#FFFFFF",
    )
    out = tmp_path / "out.pptx"
    assert g.generate([slide], str(out)) is True
    assert out.exists() and out.stat().st_size > 0
    # 打不开的路径
    assert g.generate([slide], str(tmp_path / "no_dir" / "x.pptx")) is False


def test_generate_with_transitions(tmp_path):
    g = PPTXGenerator()
    slide = MeasuredSlide(elements=[
        MeasuredElement(tag="p", text="x", x=1, y=1, width=10, height=10)
    ])
    out = tmp_path / "t.pptx"
    assert g.generate([slide], str(out), transitions=["fade", "push"]) is True


def test_wrap_html_and_base_href(tmp_path):
    engine = PPTXEngine()
    base = PPTXEngine._make_base_href(str(tmp_path), str(tmp_path / "x.pptx"))
    html = engine._wrap_html("<p>x</p>", "body{}", "#FFF", base)
    assert "<p>x</p>" in html
    assert "base" in html.lower()
