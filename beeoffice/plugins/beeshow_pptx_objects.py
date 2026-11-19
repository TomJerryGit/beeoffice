"""从 PPTX 提取可保留的原生图表/表格对象。"""
from __future__ import annotations

from pathlib import Path


def _chart_type(chart) -> str:
    try:
        name = str(chart.chart_type).upper()
    except Exception:
        name = ""
    if "PIE" in name:
        return "pie"
    if "LINE" in name:
        return "line"
    return "bar"


def _chart_data(chart):
    try:
        plot = chart.plots[0]
        categories = [str(c) for c in plot.categories]
        series = list(plot.series)
        names = [getattr(s, "name", "") or f"系列 {i+1}" for i, s in enumerate(series)]
        values = []
        for s in series:
            try:
                values.append(list(s.values))
            except Exception:
                values.append([0] * len(categories))
        header = "标签," + ",".join(names)
        rows = [header]
        for i, label in enumerate(categories):
            rows.append(label + "," + ",".join(str(v[i]) if i < len(v) else "0" for v in values))
        return "\n".join(rows)
    except Exception:
        return ""


def extract_native_objects(path) -> tuple[list[list[dict]], list[list[dict]]]:
    from pptx import Presentation
    prs = Presentation(str(path))
    charts_by_slide, tables_by_slide = [], []
    sw, sh = prs.slide_width, prs.slide_height
    for slide in prs.slides:
        charts, tables = [], []
        for shape in slide.shapes:
            try:
                if getattr(shape, "has_chart", False):
                    cfgs = {"type": _chart_type(shape.chart), "title": "", "data": _chart_data(shape.chart),
                            "left": int(shape.left), "top": int(shape.top),
                            "width": int(shape.width), "height": int(shape.height)}
                    try:
                        if shape.chart.has_title:
                            cfgs["title"] = shape.chart.chart_title.text_frame.text
                    except Exception:
                        pass
                    charts.append(cfgs)
                elif getattr(shape, "has_table", False):
                    table = shape.table
                    rows = [[cell.text for cell in row.cells] for row in table.rows]
                    tables.append({"rows": rows, "left": int(shape.left), "top": int(shape.top),
                                   "width": int(shape.width), "height": int(shape.height)})
            except Exception:
                continue
        charts_by_slide.append(charts)
        tables_by_slide.append(tables)
    return charts_by_slide, tables_by_slide
