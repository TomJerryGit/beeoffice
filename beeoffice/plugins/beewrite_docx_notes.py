"""把 [F1]/[E1] 标记转为 Word 原生脚注/尾注 XML。"""
from __future__ import annotations

import copy
from xml.sax.saxutils import escape

from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, qn

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _iter_paragraphs(doc):
    for p in doc.paragraphs:
        yield p
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    yield p
                for t in cell.tables:
                    for r in t.rows:
                        for c in r.cells:
                            yield from c.paragraphs


def _make_ref_run(marker: str) -> object:
    from docx.oxml import OxmlElement
    run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    va = OxmlElement("w:vertAlign")
    va.set(qn("w:val"), "superscript")
    rpr.append(va)
    run.append(rpr)
    if marker.startswith("F"):
        ref = OxmlElement("w:footnoteReference")
        ref.set(qn("w:id"), marker[1:])
    else:
        ref = OxmlElement("w:endnoteReference")
        ref.set(qn("w:id"), marker[1:])
    run.append(ref)
    return run


def _replace_marker_in_paragraph(p, marker, ref_run):
    for run in list(p.runs):
        text = run.text
        if marker not in text:
            continue
        parts = text.split(marker)
        parent = run._r.getparent()
        index = parent.index(run._r)
        parent.remove(run._r)
        offset = 0
        for i, part in enumerate(parts):
            if part:
                new_r = copy.deepcopy(run._r)
                for child in list(new_r):
                    if child.tag != qn("w:rPr"):
                        new_r.remove(child)
                t = new_r.makeelement(qn("w:t"), {})
                t.text = part
                t.set(qn("xml:space"), "preserve")
                new_r.append(t)
                parent.insert(index + offset, new_r)
                offset += 1
            if i < len(parts) - 1:
                ref = copy.deepcopy(ref_run)
                parent.insert(index + offset, ref)
                offset += 1


def _notes_xml(kind: str, notes: list[str]) -> bytes:
    if kind == "footnote":
        root_tag = "w:footnotes"
        note_tag = "w:footnote"
        ref_tag = "w:footnoteRef"
        sep_tag = "w:footnote"
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"
    else:
        root_tag = "w:endnotes"
        note_tag = "w:endnote"
        ref_tag = "w:endnoteRef"
        sep_tag = "w:endnote"
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.endnotes+xml"

    parts = [f'<{root_tag} {nsdecls("w")}>']
    parts.append(
        f'<{sep_tag} w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></{sep_tag}>'
    )
    parts.append(
        f'<{sep_tag} w:type="continuationSeparator" w:id="0"><w:p><w:r><w:continuationSeparator/></w:r></w:p></{sep_tag}>'
    )
    for i, text in enumerate(notes, 1):
        parts.append(
            f'<{note_tag} w:id="{i}"><w:p>'
            f'<w:r><w:rPr><w:vertAlign w:val="superscript"/></w:rPr><w:{ref_tag}/></w:r>'
            f'<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'
            f'</w:p></{note_tag}>'
        )
    parts.append(f"</{root_tag}>")
    return "".join(parts).encode("utf-8")


def add_docx_notes(doc, footnotes=None, endnotes=None) -> bool:
    """替换正文标记并注入 Word 脚注/尾注部分。"""
    footnotes = list(footnotes or [])
    endnotes = list(endnotes or [])
    if not footnotes and not endnotes:
        return False
    for i in range(1, len(footnotes) + 1):
        marker = f"[F{i}]"
        ref = _make_ref_run(f"F{i}")
        for p in _iter_paragraphs(doc):
            _replace_marker_in_paragraph(p, marker, ref)
    for i in range(1, len(endnotes) + 1):
        marker = f"[E{i}]"
        ref = _make_ref_run(f"E{i}")
        for p in _iter_paragraphs(doc):
            _replace_marker_in_paragraph(p, marker, ref)

    if footnotes:
        part = Part(
            PackURI("/word/footnotes.xml"),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml",
            _notes_xml("footnote", footnotes),
            doc.part.package,
        )
        doc.part.relate_to(part, RT.FOOTNOTES)
    if endnotes:
        part = Part(
            PackURI("/word/endnotes.xml"),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.endnotes+xml",
            _notes_xml("endnote", endnotes),
            doc.part.package,
        )
        doc.part.relate_to(part, RT.ENDNOTES)
    return True
