"""原生 Excel 图表导出：从规格创建 openpyxl Chart。"""
from __future__ import annotations

from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.utils import get_column_letter, range_boundaries


def _range_str(ws, start_col, start_row, end_col, end_row):
    return f"{get_column_letter(start_col)}{start_row}:{get_column_letter(end_col)}{end_row}"


def apply_native_chart_specs(path: str, specs) -> int:
    """把图表规格写入 xlsx；返回成功数量。"""
    from openpyxl import load_workbook
    if not specs:
        return 0
    wb = load_workbook(str(path))
    count = 0
    for spec in specs:
        if not spec.get("created", True):
            continue
        sheet = spec.get("sheet", "")
        ws = wb[sheet] if sheet in wb.sheetnames else wb.active
        data_range = spec.get("range") or ""
        if not data_range:
            continue
        try:
            # A1:C5 或 Sheet!A1:C5
            if "!" in data_range:
                data_range = data_range.rsplit("!", 1)[1]
            data_range = data_range.replace("$", "")
            min_col, min_row, max_col, max_row = range_boundaries(data_range)
        except Exception:
            continue
        data = Reference(ws, min_col=min_col, min_row=min_row, max_col=max_col, max_row=max_row)
        kind = spec.get("kind", "bar")
        chart = {"bar": BarChart, "line": LineChart, "pie": PieChart}.get(kind, BarChart)()
        chart.title = spec.get("title") or "BeeSheet 图表"
        chart.add_data(data, titles_from_data=True)
        try:
            if max_col > min_col:
                cats = Reference(ws, min_col=min_col, min_row=min_row + 1, max_row=max_row)
                chart.set_categories(cats)
        except Exception:
            pass
        ws.add_chart(chart, spec.get("anchor") or "G2")
        count += 1
    wb.save(str(path))
    return count


def read_native_chart_specs(path: str) -> list[dict]:
    """读取现有 xlsx 原生图表（基础信息，供展示/后续编辑）。"""
    from openpyxl import load_workbook
    try:
        wb = load_workbook(str(path))
    except Exception:
        return []
    specs = []
    for ws in wb.worksheets:
        for chart in ws._charts:
            title = ""
            try:
                if chart.title is not None:
                    title = "".join(r.t for p in chart.title.tx.rich.p for r in p.r)
            except Exception:
                pass
            specs.append({"sheet": ws.title, "kind": "pie" if "Pie" in type(chart).__name__ else "line" if "Line" in type(chart).__name__ else "bar",
                          "title": title, "range": "", "anchor": "G2", "created": False})
    return specs
