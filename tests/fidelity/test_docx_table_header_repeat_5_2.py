# tests/fidelity/test_docx_table_header_repeat_5_2.py
"""5.2：Markdown 表格导出 DOCX 时首行跨页重复（w:tblHeader）。"""
from docx import Document
from docx.oxml.ns import qn

from beeoffice.plugins.bee_export import export_to_docx


def _table_header_flags(path):
    doc = Document(str(path))
    table = doc.tables[0]
    flags = []
    for row in table.rows:
        tr_pr = row._tr.trPr
        flags.append(bool(tr_pr is not None and tr_pr.find(qn("w:tblHeader")) is not None))
    return flags


def test_table_first_row_repeats_across_pages(tmp_path):
    md = "| 名称 | 数量 |\n|---|---|\n| 甲 | 1 |\n| 乙 | 2 |\n"
    out = tmp_path / "table.docx"
    assert export_to_docx(md, str(out)) is True
    flags = _table_header_flags(out)
    assert flags[0] is True, "首行未设置 w:tblHeader，跨页不会重复表头"
    assert all(not f for f in flags[1:]), "只有首行应重复表头"
