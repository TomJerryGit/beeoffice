"""保留 PPTX 的备注/切换/时间轴等页级附加信息。"""
from __future__ import annotations

import copy
from lxml import etree
from pptx import Presentation
from pptx.oxml.ns import qn

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


def extract_extras(path) -> list[dict]:
    prs = Presentation(str(path))
    result = []
    for slide in prs.slides:
        trans = slide.element.find(qn("p:transition"))
        timing = slide.element.find(qn("p:timing"))
        notes = ""
        try:
            if slide.has_notes_slide:
                notes = slide.notes_slide.notes_text_frame.text.strip()
        except Exception:
            pass
        result.append({
            "transition": etree.tostring(trans, encoding="unicode") if trans is not None else "",
            "timing": etree.tostring(timing, encoding="unicode") if timing is not None else "",
            "notes": notes,
        })
    return result


def apply_extras(pptx_path: str, extras) -> int:
    prs = Presentation(str(pptx_path))
    count = 0
    for slide, cfg in zip(prs.slides, extras or []):
        if not cfg:
            continue
        for key, tag in (("transition", "p:transition"), ("timing", "p:timing")):
            xml = cfg.get(key, "")
            old = slide.element.find(qn(tag))
            if old is not None:
                slide.element.remove(old)
            if xml:
                try:
                    slide.element.append(copy.deepcopy(etree.fromstring(xml.encode("utf-8"))))
                    count += 1
                except Exception:
                    pass
        notes = cfg.get("notes", "")
        if notes:
            try:
                slide.notes_slide.notes_text_frame.text = notes
            except Exception:
                pass
    prs.save(pptx_path)
    return count
