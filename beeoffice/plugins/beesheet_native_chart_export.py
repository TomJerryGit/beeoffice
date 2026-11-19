"""原生 Excel 图表导出：从规格创建 openpyxl Chart。"""
from __future__ import annotations

from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.utils import get_column_letter, range_boundaries


def _range_str(ws, start_col, start_row, end_col, end_row):
    return f"{get_column_letter(start_col)}{start_row}:{get_column_letter(end_col)}{end_row}"


def _update_chart_source(chart, ws, spec):
    """把现有 chart 的系列/分类引用更新到新范围。"""
    from openpyxl.utils import get_column_letter, range_boundaries
    rng = spec.get("range", "")
    if not rng:
        return False
    rng = rng.replace("$", "")
    if "!" in rng:
        rng = rng.rsplit("!", 1)[1]
    try:
        min_col, min_row, max_col, max_row = range_boundaries(rng)
    except Exception:
        return False
    data_row = min_row + 1 if spec.get("has_header", True) else min_row
    cat_ref = f"'{ws.title}'!${get_column_letter(min_col)}${data_row}:${get_column_letter(min_col)}${max_row}"
    series_list = list(chart.series)
    for i, ser in enumerate(series_list):
        col = min_col + 1 + i
        if col > max_col:
            break
        val_ref = f"'{ws.title}'!${get_column_letter(col)}${data_row}:${get_column_letter(col)}${max_row}"
        try:
            ser.val.numRef.f = val_ref
        except Exception:
            pass
        try:
            if getattr(ser, "cat", None) is not None:
                if getattr(ser.cat, "numRef", None) is not None:
                    ser.cat.numRef.f = cat_ref
                elif getattr(ser.cat, "strRef", None) is not None:
                    ser.cat.strRef.f = cat_ref
        except Exception:
            pass
    return True


def apply_native_chart_specs(path: str, specs) -> int:
    """新增图表 + 更新已有图表数据源；返回处理数量。"""
    from openpyxl import load_workbook
    if not specs:
        return 0
    wb = load_workbook(str(path))
    by_sheet = {}
    for ws in wb.worksheets:
        by_sheet[ws.title] = list(ws._charts)
    count = 0
    for spec in specs:
        sheet = spec.get("sheet", "")
        ws = wb[sheet] if sheet in wb.sheetnames else wb.active
        if not spec.get("created", True):
            if not spec.get("modified"):
                continue
            charts = by_sheet.get(ws.title, list(ws._charts))
            idx = int(spec.get("chart_index", 0))
            if 0 <= idx < len(charts):
                if _update_chart_source(charts[idx], ws, spec):
                    count += 1
            continue
        data_range = spec.get("range") or ""
        if not data_range:
            continue
        try:
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


def _ref_range(ref: str):
    """解析 openpyxl 引用为 (sheet, min_col, min_row, max_col, max_row)。"""
    from openpyxl.utils import range_boundaries
    if not ref:
        return None
    try:
        sheet = ""
        if "!" in ref:
            sheet, ref = ref.rsplit("!", 1)
            sheet = sheet.strip("'")
        ref = ref.replace("$", "")
        min_col, min_row, max_col, max_row = range_boundaries(ref)
        return sheet, min_col, min_row, max_col, max_row
    except Exception:
        return None


def read_native_chart_specs(path: str) -> list[dict]:
    """读取现有 xlsx 原生图表的数据源/类型/标题。"""
    from openpyxl import load_workbook
    try:
        wb = load_workbook(str(path))
    except Exception:
        return []
    specs = []
    for ws in wb.worksheets:
        for ci, chart in enumerate(ws._charts):
            kind = "pie" if "Pie" in type(chart).__name__ else "line" if "Line" in type(chart).__name__ else "bar"
            title = ""
            try:
                if chart.title is not None:
                    title = "".join(r.t for p in chart.title.tx.rich.p for r in p.r)
            except Exception:
                pass
            ranges = []
            try:
                for ser in chart.series:
                    for ref_attr in ("val", "cat"):
                        ref_obj = getattr(ser, ref_attr, None)
                        ref = ""
                        for sub in ("numRef", "strRef"):
                            node = getattr(ref_obj, sub, None) if ref_obj else None
                            if node is not None and getattr(node, "f", None):
                                ref = node.f
                                break
                        parsed = _ref_range(ref)
                        if parsed:
                            ranges.append(parsed)
            except Exception:
                pass
            data_range = ""
            if ranges:
                min_col = min(r[1] for r in ranges); min_row = min(r[2] for r in ranges)
                max_col = max(r[3] for r in ranges); max_row = max(r[4] for r in ranges)
                from openpyxl.utils import get_column_letter
                data_range = f"{get_column_letter(min_col)}{min_row}:{get_column_letter(max_col)}{max_row}"
            specs.append({"sheet": ws.title, "kind": kind, "title": title,
                          "range": data_range, "anchor": "G2", "created": False,
                          "modified": False, "chart_index": ci, "has_header": False})
    return specs
