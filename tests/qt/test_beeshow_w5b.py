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


def test_edit_native_shape_properties(qtbot):
    s = make_show(qtbot)
    s._add_native_shape("rect")
    assert s._update_native_shape(0, {"x": 40, "y": 30, "text": "改后", "rotation": 45})
    shape = s._native_shapes[0][0]
    assert shape["x"] == 40 and shape["rotation"] == 45
    assert "改后" in s._editor.toPlainText()
    s._delete_native_shape(0)
    assert s._native_shapes[0] == []


def test_native_shape_rotation_export(qtbot, tmp_path):
    s = make_show(qtbot)
    s._add_native_shape("ellipse")
    s._update_native_shape(0, {"rotation": 45})
    out = tmp_path / "rot.pptx"
    with patch("beeoffice.plugins.beeshow_export_mixin.QFileDialog.getSaveFileName", return_value=(str(out), "PowerPoint (*.pptx)")), patch("beeoffice.plugins.beeshow_export_mixin.QMessageBox.information", return_value=None), patch("beeoffice.plugins.beeshow_export_mixin.QMessageBox.warning", return_value=None):
        s._export_pptx()
    prs = Presentation(str(out))
    assert any(abs(sh.rotation - 45) < 0.1 for sh in prs.slides[0].shapes)
