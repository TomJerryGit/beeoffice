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
