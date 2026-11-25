"""原生 Excel 图表：插入/数据源更新/导出。"""
from openpyxl import Workbook, load_workbook
from beeoffice.plugins.beesheet_native_chart_export import apply_native_chart_specs


def make_workbook(path):
    wb = Workbook(); ws = wb.active; ws.title = "数据"
    ws.append(["月份", "销量"])
    for i, (m, v) in enumerate([("一月", 10), ("二月", 20), ("三月", 30)], 2):
        ws.append([m, v])
    wb.save(path)


def test_native_chart_insert_and_update(tmp_path):
    p = tmp_path / "chart.xlsx"; make_workbook(p)
    spec = {"sheet": "数据", "kind": "bar", "title": "销量图",
            "range": "A1:B4", "anchor": "D2", "created": True}
    assert apply_native_chart_specs(p, [spec]) == 1
    wb = load_workbook(p); ws = wb["数据"]
    assert len(ws._charts) == 1
    chart = ws._charts[0]
    assert chart.title is not None
    # 数据源更新：改成 A2:B3
    spec["range"] = "A2:B3"
    assert apply_native_chart_specs(p, [spec]) == 1
    wb = load_workbook(p)
    assert len(wb["数据"]._charts) >= 1


def test_read_existing_chart_and_update_source(tmp_path):
    from openpyxl.chart import BarChart, Reference
    from beeoffice.plugins.beesheet_native_chart_export import read_native_chart_specs
    p = tmp_path / "existing.xlsx"; make_workbook(p)
    wb = load_workbook(p); ws = wb["数据"]
    chart = BarChart()
    chart.add_data(Reference(ws, min_col=2, min_row=1, max_row=4), titles_from_data=True)
    chart.set_categories(Reference(ws, min_col=1, min_row=2, max_row=4))
    ws.add_chart(chart, "D2")
    wb.save(p)
    specs = read_native_chart_specs(p)
    assert specs and specs[0]["created"] is False
    assert specs[0]["range"]
    specs[0]["range"] = "A1:B4"
    specs[0]["modified"] = True
    specs[0]["has_header"] = True
    assert apply_native_chart_specs(p, specs) == 1
    wb2 = load_workbook(p)
    charts = wb2["数据"]._charts
    assert len(charts) == 1
    ref = charts[0].series[0].val.numRef.f
    assert "B2:B4" in ref.replace("$", "")


def test_native_chart_style_axes(tmp_path):
    p = tmp_path / "styled.xlsx"; make_workbook(p)
    spec = {"sheet": "数据", "kind": "bar", "title": "销量图", "range": "A1:B4",
            "anchor": "D2", "created": True, "style": 12, "legend": "bottom",
            "x_label": "月份", "y_label": "销量", "width_cm": 12, "height_cm": 7}
    assert apply_native_chart_specs(p, [spec]) == 1
    chart = load_workbook(p)["数据"]._charts[0]
    # openpyxl 读取端不暴露 <style>，直接检查 chart XML
    import zipfile
    with zipfile.ZipFile(p) as z:
        xml = z.read([n for n in z.namelist() if n.startswith("xl/charts/chart")][0]).decode("utf-8")
    assert '<style val="12"/>' in xml
    assert '<legendPos val="b"/>' in xml
    assert chart.legend is not None and chart.legend.position == "b"
    assert chart.x_axis.title is not None
    assert chart.y_axis.title is not None


def test_combo_chart(tmp_path):
    import zipfile
    from openpyxl import Workbook
    from beeoffice.plugins.beesheet_native_chart_export import apply_native_chart_specs
    p = tmp_path / "combo.xlsx"
    wb = Workbook(); ws = wb.active; ws.title = "数据"
    ws.append(["月份", "销量", "增长率"])
    ws.append(["一月", 10, 0.1]); ws.append(["二月", 20, 0.2])
    wb.save(p)
    spec = {"sheet": "数据", "kind": "combo", "title": "组合图",
            "range": "A1:C3", "anchor": "E2", "created": True}
    assert apply_native_chart_specs(p, [spec]) == 1
    with zipfile.ZipFile(p) as z:
        xml = z.read([n for n in z.namelist() if n.startswith("xl/charts/chart")][0]).decode("utf-8")
    assert "barChart" in xml and "lineChart" in xml
    assert "<style" in xml
