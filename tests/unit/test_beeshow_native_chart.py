"""P1：PPT 原生图表对象/表格样式。"""
from unittest.mock import patch
from pptx import Presentation
from beeoffice.plugins.beeshow import BeeShowView
from beeoffice.plugins.beeshow_table_mixin import TableEditorDialog


def test_native_chart_persist_and_export(qtbot, tmp_path):
    s = BeeShowView(); qtbot.addWidget(s); s.show()
    s._native_charts = [{"type": "bar", "title": "销售", "data": "一月,10\n二月,20"}]
    s._persist_native_charts_current()
    assert "beeoffice-chartobj" in s._editor.toPlainText()
    assert s._native_charts[0]
    out = tmp_path / "chart.pptx"
    with patch("beeoffice.plugins.beeshow_export_mixin.QFileDialog.getSaveFileName", return_value=(str(out), "PowerPoint (*.pptx)")), patch("beeoffice.plugins.beeshow_export_mixin.QMessageBox.information", return_value=None), patch("beeoffice.plugins.beeshow_export_mixin.QMessageBox.warning", return_value=None):
        s._export_pptx()
    prs = Presentation(str(out))
    assert any(sh.has_chart for sh in prs.slides[0].shapes)


def test_table_style_panel(qtbot):
    d = TableEditorDialog([["A", "B"], ["1", "2"]])
    qtbot.addWidget(d)
    d._use_style_check.setChecked(True)
    d._zebra_check.setChecked(True)
    html = d.get_output_table()
    assert html.startswith("<table")
    assert "background:" in html


def test_multi_series_chart(qtbot, tmp_path):
    from beeoffice.plugins.beeshow_chart import parse_chart_series
    labels, series = parse_chart_series("月份,A,B\n一月,10,20\n二月,30,40")
    assert labels == ["一月", "二月"]
    assert len(series) == 2 and series[1][1] == [20.0, 40.0]
    s = BeeShowView(); qtbot.addWidget(s); s.show()
    s._native_charts = [{"type": "bar", "title": "多系列", "data": "月份,A,B\n一月,10,20\n二月,30,40"}]
    s._persist_native_charts_current()
    out = tmp_path / "multi.pptx"
    with patch("beeoffice.plugins.beeshow_export_mixin.QFileDialog.getSaveFileName", return_value=(str(out), "PowerPoint (*.pptx)")), patch("beeoffice.plugins.beeshow_export_mixin.QMessageBox.information", return_value=None), patch("beeoffice.plugins.beeshow_export_mixin.QMessageBox.warning", return_value=None):
        s._export_pptx()
    prs = Presentation(str(out))
    chart_shape = [sh for sh in prs.slides[0].shapes if sh.has_chart][0]
    assert len(chart_shape.chart.plots[0].series) == 2


def test_table_style_export(tmp_path):
    from pptx import Presentation
    from pptx.util import Inches
    from beeoffice.plugins.beeshow_pptx_table_style import apply_table_styles
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.shapes.add_table(2, 2, Inches(1), Inches(1), Inches(4), Inches(2))
    path = tmp_path / "table.pptx"
    prs.save(str(path))
    assert apply_table_styles(str(path), [{"header": "#FFE0B2", "border": "#DDDDDD", "zebra": True}]) == 1
    prs2 = Presentation(str(path))
    table = [sh for sh in prs2.slides[0].shapes if sh.has_table][0].table
    assert str(table.cell(0, 0).fill.fore_color.rgb) == "FFE0B2"
