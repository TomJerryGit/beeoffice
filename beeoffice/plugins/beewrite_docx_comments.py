"""把 BeeOffice 批注写入 DOCX 原生 comments.xml。"""
from __future__ import annotations

from datetime import datetime
from lxml import etree
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.packuri import PackURI
from docx.opc.part import Part

COMMENTS_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"


def _find_run_range(paragraph, excerpt):
    """定位段内 excerpt 覆盖的 run 下标；找不到返回 None。"""
    if not excerpt:
        return None
    runs = list(paragraph.runs)
    if not runs:
        return None
    target = paragraph.text.find(excerpt)
    if target < 0:
        return None
    end = target + len(excerpt)
    pos = 0
    first = last = None
    for i, run in enumerate(runs):
        start, stop = pos, pos + len(run.text)
        if stop > target and start < end:
            first = i if first is None else first
            last = i
        pos = stop
    return (first, last) if first is not None else None


def read_comments_from_docx(path):
    """读取 DOCX 原生批注（comments.xml + 正文锚点）。"""
    import zipfile
    from lxml import etree
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    try:
        with zipfile.ZipFile(str(path)) as z:
            if "word/comments.xml" not in z.namelist():
                return []
            croot = etree.fromstring(z.read("word/comments.xml"))
            body = etree.fromstring(z.read("word/document.xml"))
    except Exception:
        return []
    meta = {}
    for c in croot.findall(W + "comment"):
        cid = c.get(W + "id")
        text = "".join(c.itertext()).strip()
        meta[cid] = {"id": cid, "text": text, "author": c.get(W + "author", "")}
    excerpts = {}
    active = {}
    for el in body.iter():
        tag = el.tag
        if tag == W + "commentRangeStart":
            cid = el.get(W + "id")
            active[cid] = []
        elif tag == W + "t":
            for bucket in active.values():
                bucket.append(el.text or "")
        elif tag == W + "commentRangeEnd":
            cid = el.get(W + "id")
            excerpts[cid] = "".join(active.pop(cid, [])).strip()
    result = []
    for cid, item in meta.items():
        result.append({**item, "excerpt": excerpts.get(cid, "")})
    return result


def _find_run_range_at(paragraph, start, end):
    """按段内字符偏移定位 run 范围。"""
    pos = 0
    first = last = None
    for i, run in enumerate(paragraph.runs):
        rstart, rend = pos, pos + len(run.text)
        if rend > start and rstart < end:
            first = i if first is None else first
            last = i
        pos = rend
    return (first, last) if first is not None else None


def _comment_span(doc, c, source_text, search_from):
    """优先按 anchor 偏移定位，失败时按 excerpt 定位。"""
    excerpt = str(c.get("excerpt") or "")
    start = c.get("anchor_start")
    end = c.get("anchor_end")
    if isinstance(start, int) and isinstance(end, int) and source_text:
        if 0 <= start < end <= len(source_text):
            exact = source_text[start:end]
            if exact and "\n" not in exact:
                for p in doc.paragraphs:
                    idx = p.text.find(exact)
                    if idx >= 0:
                        return p, idx, idx + len(exact)
    best = None
    for p in doc.paragraphs:
        idx = p.text.find(excerpt, search_from if best is None else 0)
        if idx >= 0:
            cand = (p, idx, idx + len(excerpt))
            if best is None:
                best = cand
                break
    return best


def add_comments_to_document(doc, comments, source_text=None):
    """在文档中插入批注锚点与 comments.xml；返回写入数量。"""
    comments = [c for c in (comments or []) if isinstance(c, dict) and c.get("text")]
    if not comments:
        return 0
    root = OxmlElement("w:comments")
    body = doc.element.body
    used = 0
    fallback_paragraph = None
    for p in doc.paragraphs:
        if p.text.strip():
            fallback_paragraph = p
            break
    for cid, c in enumerate(comments):
        root_comment = OxmlElement("w:comment")
        root_comment.set(qn("w:id"), str(cid))
        root_comment.set(qn("w:author"), str(c.get("author") or "BeeOffice"))
        root_comment.set(qn("w:date"), datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"))
        p = OxmlElement("w:p")
        r = OxmlElement("w:r")
        t = OxmlElement("w:t")
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        t.text = str(c.get("text"))
        r.append(t); p.append(r); root_comment.append(p)
        root.append(root_comment)

        excerpt = str(c.get("excerpt") or "")
        found = _comment_span(doc, c, source_text, 0)
        if found:
            para, text_start, text_end = found
            span = _find_run_range_at(para, text_start, text_end)
        else:
            para = fallback_paragraph
            span = None
        if para is None:
            continue
        runs = list(para.runs)
        start_el = OxmlElement("w:commentRangeStart")
        start_el.set(qn("w:id"), str(cid))
        end_el = OxmlElement("w:commentRangeEnd")
        end_el.set(qn("w:id"), str(cid))
        ref_run = OxmlElement("w:r")
        ref = OxmlElement("w:commentReference")
        ref.set(qn("w:id"), str(cid))
        ref_run.append(ref)
        if span and runs:
            first, last = span
            runs[first]._r.addprevious(start_el)
            runs[last]._r.addnext(end_el)
            end_el.addnext(ref_run)
        else:
            # 无文本锚点：标在段落首部
            if runs:
                runs[0]._r.addprevious(start_el)
                start_el.addnext(end_el)
                end_el.addnext(ref_run)
            else:
                para._p.append(start_el)
                para._p.append(end_el)
                para._p.append(ref_run)
        used += 1
    if not used:
        return 0
    blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    part = Part(PackURI("/word/comments.xml"), COMMENTS_CT, blob, doc.part.package)
    doc.part.relate_to(part, RT.COMMENTS)
    return used
