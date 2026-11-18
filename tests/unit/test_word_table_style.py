"""Word 表格样式：导入/导出。"""
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from beeoffice.plugins.bee_export import read_docx_table_styles
from beeoffice.plugins.beewrite import BeeWriteEditor


def make_styled_table(path):
    doc = Document()
    table = doc.add_table(rows=2, cols=2)
    table.style = "Table Grid"
    table.cell(0, 0).text = "A"
    table.cell(0, 1).text = "B"
    tcPr = table.cell(0, 0)._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd"); shd.set(qn("w:fill"), "FFE0B2"); tcPr.append(shd)
    tblPr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"), "single"); el.set(qn("w:sz"), "4")
        el.set(qn("w:space"), "0"); el.set(qn("w:color"), "1E88E5")
        borders.append(el)
    tblPr.append(borders)
    doc.save(path)


def test_read_table_styles(tmp_path):
    src = tmp_path / "src.docx"
    make_styled_table(src)
    styles = read_docx_table_styles(src)
    assert len(styles) == 1
    assert styles[0]["header_fill"].upper() == "#FFE0B2"
    assert styles[0]["border_color"].upper() == "#1E88E5"


def test_export_table_style(qtbot, tmp_path):
    e = BeeWriteEditor(); qtbot.addWidget(e); e.show(); e._edit_mode = "rich_text"
    cursor = e.rich_editor.textCursor()
    table = cursor.insertTable(2, 2)
    table.cellAt(0, 0).firstCursorPosition().insertText("A")
    table.cellAt(0, 1).firstCursorPosition().insertText("B")
    e._docx_table_styles = [{"header_fill": "#FFE0B2", "border_color": "#1E88E5", "zebra": False}]
    out = tmp_path / "out.docx"
    assert e._write_docx(str(out))
    doc = Document(str(out))
    assert doc.tables
    t = doc.tables[0]
    shd = t.cell(0, 0)._tc.get_or_add_tcPr().find(qn("w:shd"))
    assert shd is not None
    assert shd.get(qn("w:fill")) == "FFE0B2"
    assert t._tbl.tblPr.find(qn("w:tblBorders")) is not None
