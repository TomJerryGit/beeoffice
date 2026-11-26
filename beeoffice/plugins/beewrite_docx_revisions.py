"""把基线 vs 当前文本的差异写成 Word 修订标记（简化版）。"""
from __future__ import annotations

import difflib
from datetime import datetime
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


def _ins_element(cid, author):
    el = OxmlElement("w:ins")
    el.set(qn("w:id"), str(cid))
    el.set(qn("w:author"), author)
    el.set(qn("w:date"), datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"))
    return el


def _mark_paragraph_inserted(paragraph, cid, author):
    p = paragraph._p
    runs = [child for child in p if child.tag in (qn("w:r"), qn("w:hyperlink"))]
    if not runs:
        return
    ins = _ins_element(cid, author)
    pPr = p.find(qn("w:pPr"))
    if pPr is not None:
        pPr.addnext(ins)
    else:
        p.insert(0, ins)
    for run in runs:
        p.remove(run)
        ins.append(run)


def _deleted_paragraph(text, cid, author):
    p = OxmlElement("w:p")
    d = OxmlElement("w:del")
    d.set(qn("w:id"), str(cid))
    d.set(qn("w:author"), author)
    d.set(qn("w:date"), datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"))
    r = OxmlElement("w:r")
    t = OxmlElement("w:delText")
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t.text = text
    r.append(t)
    d.append(r)
    p.append(d)
    return p


def add_revisions_to_document(doc, baseline_text, current_text, author="BeeOffice"):
    """把行级差异追加为 w:ins / w:del；返回标记数。"""
    if not baseline_text:
        return 0
    old_lines = baseline_text.splitlines()
    new_lines = current_text.splitlines()
    paragraphs = list(doc.paragraphs)
    # 只在段落映射大致一致时启用，避免表格/图片文档错位
    if len(paragraphs) != len(new_lines):
        return 0
    # 用实际段落文本重建 new_lines，防止空行差异
    new_lines = [p.text for p in paragraphs]
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    count = 0
    cid = 1000
    # 从后往前处理，避免插入导致索引漂移
    for tag, i1, i2, j1, j2 in reversed(matcher.get_opcodes()):
        if tag == "equal":
            continue
        if tag in ("insert", "replace"):
            for idx in range(j1, j2):
                if idx < len(paragraphs):
                    _mark_paragraph_inserted(paragraphs[idx], cid, author)
                    cid += 1
                    count += 1
        if tag in ("delete", "replace"):
            ref = paragraphs[j1] if j1 < len(paragraphs) else None
            for line in reversed(old_lines[i1:i2]):
                p = _deleted_paragraph(line, cid, author)
                cid += 1
                if ref is not None:
                    ref._p.addprevious(p)
                else:
                    doc.element.body.append(p)
                count += 1
    return count
