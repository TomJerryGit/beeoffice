"""Word 保真：页面/分栏/行号导入导出。"""
from docx import Document
from docx.enum.section import WD_ORIENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm
from beeoffice.plugins.bee_export import read_docx_page_settings
from beeoffice.plugins.beewrite import BeeWriteEditor


def make_docx(path):
    doc = Document()
    sec = doc.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE
    sec.page_width, sec.page_height = Mm(297), Mm(210)
    sec.top_margin = Mm(10)
    sec.bottom_margin = Mm(20)
    sec.left_margin = Mm(30)
    sec.right_margin = Mm(40)
    sectPr = sec._sectPr
    cols = sectPr.find(qn("w:cols"))
    if cols is None:
        cols = OxmlElement("w:cols")
        sectPr.append(cols)
    cols.set(qn("w:num"), "2")
    ln = OxmlElement("w:lnNumType")
    ln.set(qn("w:countBy"), "1")
    sectPr.append(ln)
    doc.add_heading("标题", level=1)
    doc.add_paragraph("正文")
    doc.save(path)
    return doc


def test_read_page_settings(tmp_path):
    src = tmp_path / "src.docx"
    make_docx(src)
    meta = read_docx_page_settings(src)
    assert meta["orientation"] == "landscape"
    assert meta["columns"] == 2
    assert meta["line_numbers"] is True
    assert abs(meta["margin_left"] - 30) < 1


def test_export_page_settings(qtbot, tmp_path):
    src = tmp_path / "src.docx"
    make_docx(src)
    meta = read_docx_page_settings(src)
    e = BeeWriteEditor(); qtbot.addWidget(e); e.show()
    e._edit_mode = "rich_text"
    e.rich_editor.setPlainText("标题\n正文")
    e._page_settings.update(meta)
    out = tmp_path / "out.docx"
    assert e._write_docx(str(out))
    sec = Document(str(out)).sections[0]
    assert sec.orientation == WD_ORIENT.LANDSCAPE
    assert sec._sectPr.find(qn("w:cols")).get(qn("w:num")) == "2"
    assert sec._sectPr.find(qn("w:lnNumType")) is not None
    assert abs(sec.left_margin.mm - 30) < 1
