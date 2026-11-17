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


def test_native_shape_drag_handler(qtbot):
    s = make_show(qtbot)
    s._add_native_shape("rect")
    s._on_native_shape_edit({"index": 0, "x": 42, "y": 33, "w": 25, "h": 12, "rotation": 30})
    shape = s._native_shapes[0][0]
    assert shape["x"] == 42 and shape["rotation"] == 30
    assert "native-shape-edit" in s._native_shape_js_for(0)


def test_master_overlay_state(qtbot):
    s = make_show(qtbot)
    s._master_css = "h1{color:#123456;}"
    s._master_overlay_html = "<div>内部资料</div>"
    assert "123456" in s._master_css
    assert "内部资料" in s._master_overlay_html


def test_native_shape_resize_js(qtbot):
    s = make_show(qtbot)
    s._add_native_shape("rect")
    js = s._native_shape_js_for(0)
    assert "bee-shape-handle" in js
    assert "snap" in js


def test_master_config_parse_and_overlay(qtbot):
    from beeoffice.plugins.beeshow_master import marker_for, master_css, overlay_html
    cfg = {"title_font": "SimHei", "title_color": "#112233", "footer": "内部",
           "date": "2026-11-17", "show_date": True, "show_page": True}
    md = marker_for(cfg) + "\n# 标题"
    s = make_show(qtbot)
    s._editor.setPlainText(md)
    s._update_preview()
    assert s._master_config["footer"] == "内部"
    assert "SimHei" in master_css(s._master_config)
    html = overlay_html(s._master_config, 2)
    assert "内部" in html and "2026-11-17" in html


def test_layout_slot_binding(qtbot):
    from beeoffice.plugins.beeshow_layout_slots import bind_layout
    md = bind_layout("title_content", {"title": "汇报", "body": "要点 A\n要点 B"})
    assert "# 汇报" in md
    assert "- 要点 A" in md and "- 要点 B" in md
    img = bind_layout("image_caption", {"image": "chart.png", "caption": "图表说明"})
    assert "chart.png" in img and "图表说明" in img


def test_smart_guides_js(qtbot):
    s = make_show(qtbot)
    s._add_native_shape("rect")
    s._add_native_shape("ellipse")
    js = s._native_shape_js_for(0)
    assert "guideV" in js and "smart" in js and "others" in js
