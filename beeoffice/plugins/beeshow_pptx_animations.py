"""把 BeeShow 元素进入动画写入 PPTX 基础 timing。"""
from __future__ import annotations

from lxml import etree
from pptx.oxml.ns import qn


def _el(parent, tag, **attrs):
    node = etree.SubElement(parent, qn(f"p:{tag}"))
    for k, v in attrs.items():
        node.set(k, str(v))
    return node


def _shape_ids(slide):
    return [shape.shape_id for shape in slide.shapes]


def _add_effect(parent, spid, effect, duration, nid):
    par = _el(parent, "par")
    outer = _el(par, "cTn", id=nid[0], fill="hold")
    nid[0] += 1
    st = _el(outer, "stCondLst")
    _el(st, "cond", delay="indefinite")
    children = _el(outer, "childTnLst")
    mid_par = _el(children, "par")
    mid_ctn = _el(mid_par, "cTn", id=nid[0], fill="hold")
    nid[0] += 1
    mid_st = _el(mid_ctn, "stCondLst")
    _el(mid_st, "cond", delay="0")
    mid_children = _el(mid_ctn, "childTnLst")
    inner_par = _el(mid_children, "par")
    effect_node = _el(
        inner_par, "cTn", id=nid[0], presetID="10",
        presetClass="entr", presetSubtype="0", fill="hold",
        grpId="0", nodeType="clickEffect",
    )
    nid[0] += 1
    est = _el(effect_node, "stCondLst")
    _el(est, "cond", delay="0")
    ecl = _el(effect_node, "childTnLst")

    # visibility set
    set_node = _el(ecl, "set")
    bhvr = _el(set_node, "cBhvr")
    ct = _el(bhvr, "cTn", id=nid[0], dur="1", fill="hold")
    nid[0] += 1
    cs = _el(ct, "stCondLst")
    _el(cs, "cond", delay="0")
    target = _el(bhvr, "tgtEl")
    _el(target, "spTgt", spid=spid)
    names = _el(bhvr, "attrNameLst")
    name = _el(names, "attrName")
    name.text = "style.visibility"
    to = _el(set_node, "to")
    val = _el(to, "strVal", val="visible")

    # entrance effect
    anim = _el(ecl, "animEffect", transition="in", filter="fade")
    ab = _el(anim, "cBhvr")
    _el(ab, "cTn", id=nid[0], dur=str(max(100, int(duration))))
    nid[0] += 1
    tgt = _el(ab, "tgtEl")
    _el(tgt, "spTgt", spid=spid)
    return par


def apply_shape_animations(pptx_path: str, configs) -> int:
    """按页写入基础进入动画；返回写入效果数。"""
    from pptx import Presentation
    prs = Presentation(pptx_path)
    total = 0
    for slide, cfg in zip(prs.slides, configs or []):
        entries = (cfg or {}).get("entries") or []
        element = slide._element
        old = element.find(qn("p:timing"))
        if old is not None:
            element.remove(old)
        if not entries:
            continue
        ids = _shape_ids(slide)
        if not ids:
            continue
        timing = etree.SubElement(element, qn("p:timing"))
        tn = _el(timing, "tnLst")
        root_par = _el(tn, "par")
        root = _el(root_par, "cTn", id="1", dur="indefinite",
                   restart="never", nodeType="tmRoot")
        root_children = _el(root, "childTnLst")
        seq = _el(root_children, "seq", concurrent="1", nextAc="seek")
        seq_ctn = _el(seq, "cTn", id="2", dur="indefinite",
                      nodeType="mainSeq")
        seq_children = _el(seq_ctn, "childTnLst")
        nid = [3]
        for i, entry in enumerate(entries):
            effect = (entry or {}).get("effect", "fade_in")
            filt = "fade"
            if effect == "slide_in":
                filt = "slide(fromBottom)"
            elif effect == "zoom_in":
                filt = "zoom(in)"
            duration = (entry or {}).get("duration", 500)
            spid = ids[i % len(ids)]
            par = _add_effect(seq_children, spid, effect, duration, nid)
            # override filter on last effect's animEffect
            for anim in par.iter(qn("p:animEffect")):
                anim.set("filter", filt)
            total += 1
        prev = _el(seq, "prevCondLst")
        pc = _el(prev, "cond", evt="onPrev", delay="0")
        pt = _el(pc, "tgtEl")
        _el(pt, "sldTgt")
        nxt = _el(seq, "nextCondLst")
        nc = _el(nxt, "cond", evt="onNext", delay="0")
        nt = _el(nc, "tgtEl")
        _el(nt, "sldTgt")
        bld = _el(timing, "bldLst")
        for i, entry in enumerate(entries):
            spid = ids[i % len(ids)]
            _el(bld, "bldP", spid=spid, grpId="0")
        prs.save(pptx_path)
    return total
