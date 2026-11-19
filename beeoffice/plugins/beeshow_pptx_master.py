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
                     "idx": int(ph.placeholder_format.idx) if ph.placeholder_format.idx is not None else 0,
                     "name": ph.name,
                     "text": ph.text_frame.text if getattr(ph, "has_text_frame", False) else "",
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
                     "idx": int(ph.placeholder_format.idx) if ph.placeholder_format.idx is not None else 0,
                     "name": ph.name,
                     "text": ph.text_frame.text if getattr(ph, "has_text_frame", False) else "",
                     "left": int(ph.left), "top": int(ph.top),
                     "width": int(ph.width), "height": int(ph.height)}
                    for ph in slide.placeholders
                ],
            })
        except Exception:
            slides.append({"layout": "", "background": "", "placeholders": []})
    return {"masters": masters, "slides": slides}


def apply_placeholders(pptx_path: str, style) -> int:
    """把源占位符重建为近似原生占位符形状（几何+文本）。

    说明：这是“占位符形状重建”，不是复制母版/版式 XML；
    只在导出页找到相同文本时替换，避免编辑后的旧文本覆盖新内容。
    """
    from pptx import Presentation
    from pptx.util import Emu
    from lxml import etree
    from pptx.oxml.ns import qn
    prs = Presentation(str(pptx_path))
    count = 0
    for slide, cfg in zip(prs.slides, (style or {}).get("slides", [])):
        placeholders = cfg.get("placeholders", []) or []
        for ph in placeholders:
            text = (ph.get("text") or "").strip()
            if not text:
                continue
            matches = []
            for shape in list(slide.shapes):
                try:
                    if getattr(shape, "has_text_frame", False) and shape.text_frame.text.strip() == text:
                        matches.append(shape)
                except Exception:
                    continue
            if not matches:
                continue
            for shape in matches:
                try:
                    shape._element.getparent().remove(shape._element)
                except Exception:
                    pass
            try:
                box = slide.shapes.add_textbox(
                    Emu(int(ph.get("left", 914400))), Emu(int(ph.get("top", 914400))),
                    Emu(int(ph.get("width", 4572000))), Emu(int(ph.get("height", 914400))),
                )
                box.text_frame.text = text
                nv = box._element.nvSpPr
                nvPr = nv.find(qn("p:nvPr"))
                if nvPr is None:
                    nvPr = etree.SubElement(nv, qn("p:nvPr"))
                ph_el = etree.SubElement(nvPr, qn("p:ph"))
                ph_el.set("type", "title" if "TITLE" in str(ph.get("type", "")).upper() else "body")
                if ph.get("idx") is not None:
                    ph_el.set("idx", str(ph.get("idx")))
                count += 1
            except Exception:
                pass
    prs.save(pptx_path)
    return count


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
