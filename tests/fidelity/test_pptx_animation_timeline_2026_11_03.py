"""PPTX 动画时间轴：被 PowerPoint 识别为 MainSequence（2026-11-03）。"""
from pathlib import Path

from pptx import Presentation

from beeoffice.plugins.beeshow_pptx_engine import add_shape_animations_valid


def _slide():
    prs = Presentation()
    return prs, prs.slides.add_slide(prs.slide_layouts[6])


def test_valid_timing_has_bld_and_set():
    prs, slide = _slide()
    a = slide.shapes.add_textbox(10, 10, 200, 50)
    b = slide.shapes.add_textbox(10, 100, 200, 50)
    assert add_shape_animations_valid(slide, [
        (a, "fade_in", 600, 0),
        (b, "pulse", 300, 0),
    ])
    xml = slide._element.xml
    assert xml.count("<p:animEffect ") == 1
    assert "<p:animScale" in xml
    assert "<p:bldLst>" in xml
    assert 'grpId="0"' in xml
    assert 'nodeType="clickEffect"' in xml
    assert 'nodeType="afterEffect"' in xml
    assert xml.count("<p:set>") == 2


def test_click_each_separate_click_blocks():
    prs, slide = _slide()
    a = slide.shapes.add_textbox(10, 10, 200, 50)
    b = slide.shapes.add_textbox(10, 100, 200, 50)
    assert add_shape_animations_valid(
        slide, [(a, "fade_in", 400, 0), (b, "fade_out", 300, 0)],
        click_each=True,
    )
    xml = slide._element.xml
    assert xml.count('delay="indefinite"') == 2
    assert xml.count("<p:set>") == 2


def test_tool_script_structural(tmp_path):
    import subprocess
    import sys

    out = tmp_path / "gate.json"
    root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [sys.executable, str(root / "tools" / "verify_pptx_animations.py"),
         "--json", str(out)],
        cwd=str(root), capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert out.is_file()
