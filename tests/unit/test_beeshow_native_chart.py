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
