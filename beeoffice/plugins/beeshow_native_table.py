"""BeeShow 原生表格对象：持久化标记 + PPTX Table 导出。"""
from __future__ import annotations

import html
import json
import re

MARKER_RE = re.compile(r"<!--\s*beeoffice-tableobj:\s*(\{.*?\})\s*-->", re.DOTALL)


def parse_tables(md: str):
    m = MARKER_RE.search(md or "")
    if not m:
        return [], md or ""
    try:
        data = json.loads(m.group(1))
        return list(data.get("tables", [])), MARKER_RE.sub("", md or "").strip()
    except Exception:
        return [], md or ""


def marker_for(tables) -> str:
    return "<!-- beeoffice-tableobj: " + json.dumps(
        {"tables": list(tables)}, ensure_ascii=False, separators=(",", ":")
    ) + " -->"


def table_html(tables) -> str:
    if isinstance(tables, dict):
        tables = [tables]
    parts = []
    for cfg in tables or []:
        rows = cfg.get("rows", [])
        if not rows:
            continue
        body = []
        for ri, row in enumerate(rows):
            tag = "th" if ri == 0 else "td"
            body.append("<tr>" + "".join(f"<{tag}>{html.escape(str(c))}</{tag}>" for c in row) + "</tr>")
        parts.append('<table style="border-collapse:collapse;margin:10px auto;">' + "".join(body) + "</table>")
    return "".join(parts)


def apply_native_tables(pptx_path: str, configs) -> int:
    from pptx import Presentation
    from pptx.util import Emu, Pt

    prs = Presentation(pptx_path)
    count = 0
    for slide, tables in zip(prs.slides, configs or []):
        if isinstance(tables, dict):
            tables = [tables]
        for cfg in tables or []:
            rows = cfg.get("rows", [])
            if not rows:
                continue
            cols = max(len(r) for r in rows)
            left = Emu(int(cfg.get("left", 914400)))
            top = Emu(int(cfg.get("top", 914400)))
            width = Emu(int(cfg.get("width", 5486400)))
            height = Emu(int(cfg.get("height", 2743200)))
            gf = slide.shapes.add_table(len(rows), cols, left, top, width, height)
            table = gf.table
            for ri, row in enumerate(rows):
                for ci in range(cols):
                    val = str(row[ci]) if ci < len(row) else ""
                    cell = table.cell(ri, ci)
                    cell.text = val
                    for para in cell.text_frame.paragraphs:
                        for run in para.runs:
                            run.font.size = Pt(12)
            count += 1
    prs.save(pptx_path)
    return count
