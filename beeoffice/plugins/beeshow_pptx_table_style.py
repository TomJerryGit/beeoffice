"""PPT 表格样式：持久化标记 + 写入 PPTX 原生表格。"""
from __future__ import annotations

import json
import re

MARKER_RE = re.compile(r"<!--\s*beeoffice-table-style:\s*(\{.*?\})\s*-->", re.DOTALL)


def parse_table_style(md: str):
    m = MARKER_RE.search(md or "")
    if not m:
        return None, md or ""
    try:
        data = json.loads(m.group(1))
        return data, MARKER_RE.sub("", md or "").strip()
    except Exception:
        return None, md or ""


def marker_for(style: dict) -> str:
    return "<!-- beeoffice-table-style: " + json.dumps(style, ensure_ascii=False, separators=(",", ":")) + " -->"


def _set_border(cell, color: str):
    from pptx.oxml.ns import qn
    from lxml import etree
    tcPr = cell._tc.get_or_add_tcPr()
    for tag in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
        old = tcPr.find(qn(tag))
        if old is not None:
            tcPr.remove(old)
        ln = etree.SubElement(tcPr, qn(tag), w="9525")
        fill = etree.SubElement(ln, qn("a:solidFill"))
        clr = etree.SubElement(fill, qn("a:srgbClr"), val=color.lstrip("#").upper())


def apply_table_styles(pptx_path: str, configs) -> int:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    prs = Presentation(pptx_path)
    count = 0
    for slide, style in zip(prs.slides, configs or []):
        if not style:
            continue
        for shape in slide.shapes:
            if not getattr(shape, "has_table", False):
                continue
            table = shape.table
            header = style.get("header", "#FFF3E0")
            border = style.get("border", "#DDDDDD")
            zebra = bool(style.get("zebra", False))
            for ri, row in enumerate(table.rows):
                for cell in row.cells:
                    bg = header if ri == 0 else ("#F7F7F7" if zebra and ri % 2 == 0 else None)
                    if bg:
                        try:
                            cell.fill.solid()
                            cell.fill.fore_color.rgb = RGBColor.from_string(bg.lstrip("#"))
                        except Exception:
                            pass
                    try:
                        _set_border(cell, border)
                    except Exception:
                        pass
            count += 1
    prs.save(pptx_path)
    return count
