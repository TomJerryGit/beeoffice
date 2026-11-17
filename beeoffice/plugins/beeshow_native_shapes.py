"""BeeShow 原生形状模型 + PPTX 导出。"""
from __future__ import annotations

import json
import re

MARKER_RE = re.compile(r"<!--\s*beeoffice-shapes:\s*(\{.*?\})\s*-->", re.DOTALL)
DEFAULT_SHAPES = []


def parse_shapes(md: str):
    m = MARKER_RE.search(md or "")
    if not m:
        return [], md or ""
    try:
        data = json.loads(m.group(1))
        return list(data.get("shapes", [])), MARKER_RE.sub("", md).strip()
    except Exception:
        return [], md or ""


def marker_for(shapes) -> str:
    return "<!-- beeoffice-shapes: " + json.dumps(
        {"shapes": list(shapes)}, ensure_ascii=False, separators=(",", ":")
    ) + " -->"


def shapes_html(shapes) -> str:
    parts = []
    for s in shapes or []:
        kind = s.get("kind", "rect")
        x = float(s.get("x", 10)); y = float(s.get("y", 10))
        w = float(s.get("w", 30)); h = float(s.get("h", 15))
        fill = s.get("fill", "#FFF3E0"); line = s.get("line", "#E67E22")
        text = str(s.get("text", ""))
        rot = float(s.get("rotation", 0) or 0)
        base = (f"position:absolute;left:{x}%;top:{y}%;width:{w}%;height:{h}%;"
                f"box-sizing:border-box;border:2px solid {line};"
                f"transform:rotate({rot}deg);"
                f"display:flex;align-items:center;justify-content:center;")
        if kind == "ellipse":
            base += f"border-radius:50%;background:{fill};"
            parts.append(f'<div style="{base}">{text}</div>')
        elif kind == "text":
            base += f"background:transparent;border:1px dashed {line};color:{line};"
            parts.append(f'<div style="{base}">{text or "文本"}</div>')
        elif kind == "art":
            base += f"background:transparent;border:none;color:{line};"
            parts.append(f'<div style="{base}font-size:32px;font-weight:bold;">{text or "艺术字"}</div>')
        else:
            base += f"background:{fill};"
            parts.append(f'<div style="{base}">{text}</div>')
    return '<div class="native-shapes" style="position:absolute;inset:0;pointer-events:none;">' + "".join(parts) + "</div>"


def apply_native_shapes(pptx_path: str, configs) -> int:
    """把原生形状写入 PPTX。"""
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.dml.color import RGBColor
    from pptx.util import Inches
    from pptx.enum.text import PP_ALIGN

    prs = Presentation(pptx_path)
    sw = prs.slide_width; sh = prs.slide_height
    count = 0
    for slide, shapes in zip(prs.slides, configs or []):
        for s in shapes or []:
            kind = s.get("kind", "rect")
            x = float(s.get("x", 10)) / 100 * sw
            y = float(s.get("y", 10)) / 100 * sh
            w = float(s.get("w", 30)) / 100 * sw
            h = float(s.get("h", 15)) / 100 * sh
            mso = {"ellipse": MSO_SHAPE.OVAL, "arrow": MSO_SHAPE.RIGHT_ARROW}.get(
                kind, MSO_SHAPE.RECTANGLE
            )
            shape = slide.shapes.add_shape(mso, x, y, w, h)
            try:
                shape.fill.solid()
                hex_fill = str(s.get("fill", "#FFF3E0")).lstrip("#")
                shape.fill.fore_color.rgb = RGBColor.from_string(hex_fill)
                shape.line.color.rgb = RGBColor.from_string(
                    str(s.get("line", "#E67E22")).lstrip("#")
                )
            except Exception:
                pass
            if kind in ("text", "art"):
                shape.text = str(s.get("text", ""))
                shape.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
            try:
                shape.rotation = float(s.get("rotation", 0) or 0)
            except Exception:
                pass
            count += 1
    prs.save(pptx_path)
    return count
