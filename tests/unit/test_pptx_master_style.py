"""PPTX 母版背景/占位符元数据保留。"""
from unittest.mock import patch
from pptx import Presentation
from pptx.dml.color import RGBColor
from beeoffice.plugins.beeshow import BeeShowView


def make_fixture(path):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "母版标题"
    fill = slide.background.fill
    fill.solid(); fill.fore_color.rgb = RGBColor(0x1E, 0x88, 0xE5)
    prs.save(str(path))


def test_master_style_and_placeholder_metadata(qtbot, tmp_path):
    src = tmp_path / "src.pptx"; make_fixture(src)
    s = BeeShowView(); qtbot.addWidget(s)
    with patch("PySide6.QtWidgets.QMessageBox.information", return_value=None), patch("PySide6.QtWidgets.QMessageBox.warning", return_value=None):
        assert s.open_pptx(str(src)) is True
    assert s._pptx_master_style["slides"][0]["background"] == "1E88E5"
    assert s._pptx_master_style["slides"][0]["placeholders"]
    out = tmp_path / "out.pptx"
    with patch("beeoffice.plugins.beeshow_export_mixin.QFileDialog.getSaveFileName", return_value=(str(out), "PowerPoint (*.pptx)")), patch("beeoffice.plugins.beeshow_export_mixin.QMessageBox.information", return_value=None), patch("beeoffice.plugins.beeshow_export_mixin.QMessageBox.warning", return_value=None):
        s._export_pptx()
    assert str(Presentation(str(out)).slides[0].background.fill.fore_color.rgb) == "1E88E5"
    shapes = list(Presentation(str(out)).slides[0].shapes)
    assert any(getattr(sh, "is_placeholder", False) for sh in shapes)
    assert any("母版标题" in (getattr(sh, "text", "") or "") for sh in shapes)
