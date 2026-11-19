"""PPTX 母版/版式与占位符元数据提取（基础保留）。"""
from __future__ import annotations

from pptx import Presentation
from pptx.dml.color import RGBColor


def _solid_rgb(fill):
    try:
        if fill.type is not None and fill.type == 1:  # MSO_FILL.SOLID
            return str(fill.fore_color.rgb)
    except Exception:
        pass
    return ""


def extract_master_style(path) -> dict:
    prs = Presentation(str(path))
    masters = []
    for master in prs.slide_masters:
        try:
            bg = _solid_rgb(master.background.fill)
        except Exception:
            bg = ""
        layouts = []
        for layout in master.slide_layouts:
            layouts.append({
                "name": layout.name,
                "placeholders": [
                    {"type": str(ph.placeholder_format.type),
                     "left": int(ph.left), "top": int(ph.top),
                     "width": int(ph.width), "height": int(ph.height)}
                    for ph in layout.placeholders
                ],
            })
        masters.append({"background": bg, "layouts": layouts})
    slides = []
    for slide in prs.slides:
        try:
            layout = slide.slide_layout
            bg = _solid_rgb(slide.background.fill)
            if not bg:
                bg = _solid_rgb(layout.background.fill)
            slides.append({
                "layout": layout.name,
                "background": bg,
                "placeholders": [
                    {"type": str(ph.placeholder_format.type),
                     "left": int(ph.left), "top": int(ph.top),
                     "width": int(ph.width), "height": int(ph.height)}
                    for ph in slide.placeholders
                ],
            })
        except Exception:
            slides.append({"layout": "", "background": "", "placeholders": []})
    return {"masters": masters, "slides": slides}


def apply_master_style(pptx_path: str, style) -> int:
    prs = Presentation(str(pptx_path))
    count = 0
    for slide, cfg in zip(prs.slides, (style or {}).get("slides", [])):
        bg = cfg.get("background", "")
        if not bg:
            continue
        try:
            fill = slide.background.fill
            fill.solid()
            fill.fore_color.rgb = RGBColor.from_string(bg)
            count += 1
        except Exception:
            pass
    prs.save(pptx_path)
    return count
