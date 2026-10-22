# tests/fidelity/test_docx_page_numbers_5_3.py
"""5.3：DOCX 页码体系（域 + 起始页 + 罗马数字 + 位置）。"""
from docx import Document
from docx.oxml.ns import qn

from beeoffice.plugins.bee_export import export_to_docx
from beeoffice.plugins.beewrite_page_extras import PageNumberDialog


def _sect_pg_num(doc):
    sect_pr = doc.sections[0]._sectPr
    return sect_pr.find(qn("w:pgNumType"))


def test_docx_page_number_field_and_start(tmp_path):
    out = tmp_path / "pn.docx"
    config = {
        "enabled": True,
        "position": "底部居中",
        "format": "第 1 页 / 共 N 页",
        "start": 3,
        "num_format": "lowerRoman",
        "fontsize": 10,
    }
    assert export_to_docx("# 标题\n\n正文\n", str(out), page_number=config) is True
    doc = Document(str(out))
    pg = _sect_pg_num(doc)
    assert pg is not None
    assert pg.get(qn("w:start")) == "3"
    assert pg.get(qn("w:fmt")) == "lowerRoman"

    xml = doc.sections[0].footer._element.xml
    assert "PAGE" in xml and "NUMPAGES" in xml, xml[:500]


def test_docx_page_number_top_right(tmp_path):
    out = tmp_path / "pn2.docx"
    config = {
        "enabled": True, "position": "顶部右侧", "format": "1",
        "start": 1, "num_format": "arabic",
    }
    assert export_to_docx("正文\n", str(out), page_number=config) is True
    doc = Document(str(out))
    xml = doc.sections[0].header._element.xml
    assert "PAGE" in xml
    assert "w:val=\"right\"" in xml


def test_dialog_exposes_num_format(qapp):
    dlg = PageNumberDialog({"enabled": True, "num_format": "upperRoman"})
    assert dlg.get_config()["num_format"] == "upperRoman"
    assert dlg.get_config()["enabled"] is True
