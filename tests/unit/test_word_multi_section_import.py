"""Word 多节导入还原 + 每节独立设置。"""
from docx import Document
from docx.enum.section import WD_SECTION, WD_ORIENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm
from beeoffice.plugins.bee_export import import_from_docx, read_docx_sections
from beeoffice.plugins.beewrite import BeeWriteEditor


def make_two_sections(path):
    doc = Document()
    first = doc.sections[0]
    first.top_margin = Mm(10)
    doc.add_heading("第一节", level=1)
    doc.add_paragraph("第一节正文")
    second = doc.add_section(WD_SECTION.NEW_PAGE)
    second.orientation = WD_ORIENT.LANDSCAPE
    second.page_width, second.page_height = Mm(297), Mm(210)
    second.top_margin = Mm(20)
    sectPr = second._sectPr
    cols = sectPr.find(qn("w:cols"))
    if cols is None:
        cols = OxmlElement("w:cols"); sectPr.append(cols)
    cols.set(qn("w:num"), "2")
    pgb = OxmlElement("w:pgBorders")
    for side in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"), "single"); el.set(qn("w:sz"), "8")
        el.set(qn("w:space"), "24"); el.set(qn("w:color"), "1E88E5")
        pgb.append(el)
    sectPr.append(pgb)
    doc.add_heading("第二节", level=1)
    doc.add_paragraph("第二节正文")
    doc.save(path)


def test_read_sections(tmp_path):
    src = tmp_path / "src.docx"
    make_two_sections(src)
    sections = read_docx_sections(src)
    assert len(sections) == 2
    assert sections[0]["settings"]["columns"] == 1
    assert sections[1]["settings"]["columns"] == 2
    assert sections[1]["settings"]["page_border"] is True


def test_import_apply_and_export(qtbot, tmp_path):
    src = tmp_path / "src.docx"
    make_two_sections(src)
    sections = read_docx_sections(src)
    breaks = [s["paragraph_index"] for s in sections if s.get("paragraph_index") is not None]
    md = import_from_docx(str(src), section_breaks=breaks)
    assert "BEEOFFICE_SECTION_BREAK" in md
    e = BeeWriteEditor(); qtbot.addWidget(e); e.show(); e._edit_mode = "rich_text"
    e.set_content(md)
    e._switch_mode("rich_text")
    e._apply_imported_sections(sections)
    assert len(e._section_page_settings) == 2
    out = tmp_path / "out.docx"
    assert e._write_docx(str(out))
    doc = Document(str(out))
    assert len(doc.sections) == 2
    assert doc.sections[1]._sectPr.find(qn("w:cols")).get(qn("w:num")) == "2"
    assert doc.sections[1]._sectPr.find(qn("w:pgBorders")) is not None


def test_per_section_headers_export(qtbot, tmp_path):
    e = BeeWriteEditor(); qtbot.addWidget(e); e.show(); e._edit_mode = "rich_text"
    e.rich_editor.setPlainText("第一节")
    e._insert_section_break()
    cur = e.rich_editor.textCursor(); cur.movePosition(cur.MoveOperation.End); cur.insertText("第二节")
    e._section_page_settings = [
        {"header": "第一节页眉", "footer": "第一节页脚", "paper": "A4", "orientation": "portrait", "columns": 1},
        {"header": "第二节页眉", "footer": "第二节页脚", "paper": "A4", "orientation": "portrait", "columns": 2},
    ]
    e._header_text = "第一节页眉"; e._footer_text = "第一节页脚"
    out = tmp_path / "section-headers.docx"
    assert e._write_docx(str(out))
    doc = Document(str(out))
    assert len(doc.sections) == 2
    assert doc.sections[0].header.paragraphs[0].text == "第一节页眉"
    assert doc.sections[1].header.paragraphs[0].text == "第二节页眉"
    assert doc.sections[1].footer.paragraphs[0].text == "第二节页脚"
