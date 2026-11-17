"""Wave5 W5：PPT 原生形状/母版视图基础。"""
from unittest.mock import patch
from pptx import Presentation
from beeoffice.plugins.beeshow import BeeShowView


def make_show(qtbot):
    s = BeeShowView(); qtbot.addWidget(s); s.show(); return s


def test_native_shape_add_and_marker(qtbot):
    s = make_show(qtbot)
    s._add_native_shape("rect")
    assert s._native_shapes[0]
    assert "beeoffice-shapes" in s._editor.toPlainText()


def test_native_shape_export(qtbot, tmp_path):
    s = make_show(qtbot)
    s._add_native_shape("ellipse")
    out = tmp_path / "shapes.pptx"
    with patch("beeoffice.plugins.beeshow_export_mixin.QFileDialog.getSaveFileName", return_value=(str(out), "PowerPoint (*.pptx)")), patch("beeoffice.plugins.beeshow_export_mixin.QMessageBox.information", return_value=None), patch("beeoffice.plugins.beeshow_export_mixin.QMessageBox.warning", return_value=None):
        s._export_pptx()
    prs = Presentation(str(out))
    assert len(prs.slides[0].shapes) >= 1


def test_view_mode_toggles(qtbot):
    s = make_show(qtbot)
    s._toggle_slide_sorter(); assert s._view_mode == "sorter"
    s._toggle_slide_sorter(); assert s._view_mode == "normal"
    s._toggle_notes_view()
    s._show_reading_view()
