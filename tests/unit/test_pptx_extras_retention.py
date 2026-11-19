"""PPTX 切换/时间轴/备注保留。"""
from unittest.mock import patch
from pptx import Presentation
from pptx.util import Inches
from beeoffice.plugins.beeshow import BeeShowView
from beeoffice.plugins.beeshow_pptx_transitions import apply_slide_transitions
from beeoffice.plugins.beeshow_pptx_animations import apply_shape_animations


def make_fixture(path):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1)).text = "动画对象"
    slide.notes_slide.notes_text_frame.text = "这是演讲备注"
    prs.save(str(path))
    apply_slide_transitions(str(path), [{"transition": "fade"}])
    apply_shape_animations(str(path), [{"entries": [{"effect": "fade_in", "duration": 400}]}])


def test_extras_retained(qtbot, tmp_path):
    src = tmp_path / "src.pptx"; make_fixture(src)
    s = BeeShowView(); qtbot.addWidget(s)
    with patch("PySide6.QtWidgets.QMessageBox.information", return_value=None), patch("PySide6.QtWidgets.QMessageBox.warning", return_value=None):
        assert s.open_pptx(str(src)) is True
    assert s._pptx_extras and s._pptx_extras[0]["transition"]
    assert s._pptx_extras[0]["timing"]
    assert s._speaker_notes[0] == "这是演讲备注"
    out = tmp_path / "out.pptx"
    with patch("beeoffice.plugins.beeshow_export_mixin.QFileDialog.getSaveFileName", return_value=(str(out), "PowerPoint (*.pptx)")), patch("beeoffice.plugins.beeshow_export_mixin.QMessageBox.information", return_value=None), patch("beeoffice.plugins.beeshow_export_mixin.QMessageBox.warning", return_value=None):
        s._export_pptx()
    prs = Presentation(str(out)); slide = prs.slides[0]
    ns = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
    assert slide.element.find(ns + "transition") is not None
    assert slide.element.find(ns + "timing") is not None
    assert slide.notes_slide.notes_text_frame.text.strip() == "这是演讲备注"
