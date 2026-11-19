"""PPTX 原生图表/表格导入导出保留。"""
from unittest.mock import patch
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.util import Inches
from beeoffice.plugins.beeshow import BeeShowView


def make_pptx(path):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    data = CategoryChartData()
    data.categories = ["一月", "二月", "三月"]
    data.add_series("销量", (10, 20, 30))
    slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(1), Inches(5), Inches(3), data)
    slide.shapes.add_table(2, 2, Inches(1), Inches(4.5), Inches(5), Inches(1.5))
    prs.save(str(path))


def test_native_chart_table_retained(qtbot, tmp_path):
    src = tmp_path / "src.pptx"
    make_pptx(src)
    s = BeeShowView(); qtbot.addWidget(s)
    with patch("PySide6.QtWidgets.QMessageBox.information", return_value=None), patch("PySide6.QtWidgets.QMessageBox.warning", return_value=None):
        assert s.open_pptx(str(src)) is True
    assert any(s._native_charts)
    assert any(s._native_tables)
    out = tmp_path / "out.pptx"
    with patch("beeoffice.plugins.beeshow_export_mixin.QFileDialog.getSaveFileName", return_value=(str(out), "PowerPoint (*.pptx)")), patch("beeoffice.plugins.beeshow_export_mixin.QMessageBox.information", return_value=None), patch("beeoffice.plugins.beeshow_export_mixin.QMessageBox.warning", return_value=None):
        s._export_pptx()
    prs = Presentation(str(out))
    charts = sum(1 for sh in prs.slides[0].shapes if sh.has_chart)
    tables = sum(1 for sh in prs.slides[0].shapes if sh.has_table)
    assert charts == 1
    assert tables == 1
