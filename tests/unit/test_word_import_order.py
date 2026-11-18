"""Word 导入顺序：段落/表格保持文档顺序。"""
from docx import Document
from beeoffice.plugins.bee_export import import_from_docx


def test_table_between_paragraphs(tmp_path):
    p = tmp_path / "order.docx"
    d = Document()
    d.add_heading("第一节", level=1)
    d.add_paragraph("表格前")
    t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text = "A"
    t.cell(0, 1).text = "B"
    d.add_paragraph("表格后")
    d.save(p)
    md = import_from_docx(str(p))
    assert "表格前" in md and "表格后" in md
    assert md.index("表格前") < md.index("| A | B |") < md.index("表格后")
