"""Word 保真：页面边框/分节符。"""
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from beeoffice.plugins.bee_export import read_docx_page_settings
from beeoffice.plugins.beewrite import BeeWriteEditor


def make_border_docx(path):
    d = Document()
    pgb = OxmlElement("w:pgBorders")
    pgb.set(qn("w:offsetFrom"), "page")
    for side in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "8")
        el.set(qn("w:space"), "24")
        el.set(qn("w:color"), "1E88E5")
        pgb.append(el)
    d.sections[0]._sectPr.append(pgb)
    d.add_paragraph("边框样本")
    d.save(path)


def test_page_border_roundtrip(qtbot, tmp_path):
    src = tmp_path / "src.docx"
    make_border_docx(src)
    meta = read_docx_page_settings(src)
    assert meta["page_border"] is True
    assert meta["page_border_color"].upper() == "#1E88E5"
    e = BeeWriteEditor(); qtbot.addWidget(e); e.show(); e._edit_mode = "rich_text"
    e.rich_editor.setPlainText("边框样本")
    e._page_settings.update(meta)
    out = tmp_path / "out.docx"
    assert e._write_docx(str(out))
    sectPr = Document(str(out)).sections[0]._sectPr
    pgb = sectPr.find(qn("w:pgBorders"))
    assert pgb is not None
    assert pgb.find(qn("w:top")).get(qn("w:color")) == "1E88E5"


def test_section_break_export(qtbot, tmp_path):
    e = BeeWriteEditor(); qtbot.addWidget(e); e.show(); e._edit_mode = "rich_text"
    e.rich_editor.setPlainText("第一节")
    e._insert_section_break()
    cur = e.rich_editor.textCursor()
    cur.movePosition(cur.MoveOperation.End)
    cur.insertText("第二节")
    out = tmp_path / "sections.docx"
    assert e._write_docx(str(out))
    assert len(Document(str(out)).sections) == 2


def test_section_page_settings_applied(qtbot, tmp_path):
    e = BeeWriteEditor(); qtbot.addWidget(e); e.show(); e._edit_mode = "rich_text"
    e.rich_editor.setPlainText("第一节")
    e._page_settings.update({"columns": 2, "page_border": True,
                             "page_border_color": "#E67E22", "page_border_width": 3})
    e._insert_section_break()
    e.rich_editor.textCursor().movePosition(e.rich_editor.textCursor().MoveOperation.End)
    e.rich_editor.textCursor().insertText("第二节")
    out = tmp_path / "sections-settings.docx"
    assert e._write_docx(str(out))
    doc = Document(str(out))
    assert len(doc.sections) == 2
    for sec in doc.sections:
        assert sec._sectPr.find(qn("w:cols")).get(qn("w:num")) == "2"
        assert sec._sectPr.find(qn("w:pgBorders")) is not None
