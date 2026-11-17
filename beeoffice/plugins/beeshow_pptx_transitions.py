"""把 BeeShow 幻灯片切换效果写入 PPTX（基础过渡保留）。"""
from __future__ import annotations

from pptx.oxml.ns import qn
from lxml import etree


_TRANSITION_TAG = {
    "fade": "fade",
    "push": "push",
    "wipe": "wipe",
    "cover": "cover",
}


def apply_slide_transitions(pptx_path: str, configs) -> int:
    """按 configs 写入幻灯片切换；返回写入页数。"""
    from pptx import Presentation
    prs = Presentation(pptx_path)
    count = 0
    for slide, cfg in zip(prs.slides, configs or []):
        key = (cfg or {}).get("transition", "none")
        tag = _TRANSITION_TAG.get(key)
        element = slide._element
        old = element.find(qn("p:transition"))
        if old is not None:
            element.remove(old)
        if tag is None:
            continue
        transition = etree.SubElement(element, qn("p:transition"))
        child = etree.SubElement(transition, qn(f"p:{tag}"))
        if tag in ("push", "wipe", "cover"):
            child.set("dir", "u")
        count += 1
    prs.save(pptx_path)
    return count
