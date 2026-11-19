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
