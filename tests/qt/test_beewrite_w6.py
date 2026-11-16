"""Wave 2 W6：BeeWrite 页面设置/页眉页脚/20 页导出测试。"""
from docx import Document

from beeoffice.plugins.beewrite import BeeWriteEditor


def make_editor(qtbot):
    e = BeeWriteEditor()
    qtbot.addWidget(e)
    e.show()
    e._edit_mode = "rich_text"
    return e


def test_page_settings_columns_css(qtbot):
    e = make_editor(qtbot)
    e._page_settings["columns"] = 2
    e._page_settings["line_numbers"] = True
    html = e._apply_page_settings_to_content("<p>x</p>", e._page_settings)
    assert "column-count:2" in html


def test_header_footer_variants_export(qtbot, tmp_path):
    e = make_editor(qtbot)
    e.rich_editor.setPlainText("正文")
    e._header_text = "页眉"
    e._footer_text = "页脚"
    e._header_first_text = "首页页眉"
    e._header_even_text = "偶数页眉"
    e._different_first_page = True
    e._odd_even_pages = True
    out = tmp_path / "header.docx"
    assert e._write_docx(str(out)) is True
    doc = Document(str(out))
    sec = doc.sections[0]
    assert sec.different_first_page_header_footer is True
    assert doc.settings.odd_and_even_pages_header_footer is True
    assert sec.first_page_header.paragraphs[0].text == "首页页眉"
    assert sec.even_page_header.paragraphs[0].text == "偶数页眉"
    assert sec.header.paragraphs[0].text == "页眉"


def test_20_paragraph_export(qtbot, tmp_path):
    e = make_editor(qtbot)
    lines = [f"第 {i} 段内容" for i in range(1, 21)]
    e.rich_editor.setPlainText("\n".join(lines))
    out = tmp_path / "twentypage.docx"
    assert e._write_docx(str(out)) is True
    doc = Document(str(out))
    texts = [p.text for p in doc.paragraphs if p.text.strip()]
    assert len(texts) == 20
    assert "第 20 段内容" in texts
