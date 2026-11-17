"""P0 硬化：真实文档往返与已知保真边界。

通过标准：核心内容（标题/段落/表格/数据/幻灯片文本）不丢。
标记 xfail：当前明确不保真的复杂结构，先记录不阻塞 Beta。
"""
import pandas as pd
import pytest
from docx import Document
from pptx import Presentation
from pptx.util import Inches

from beeoffice.plugins.bee_export import export_to_docx, import_from_docx
from beeoffice.plugins.beeshow import BeeShowView


def test_docx_heading_table_roundtrip(tmp_path):
    src = tmp_path / "src.docx"
    doc = Document()
    doc.add_heading("标题一", level=1)
    doc.add_paragraph("正文段落")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "A"
    table.cell(0, 1).text = "B"
    doc.save(str(src))

    md = import_from_docx(str(src))
    assert "# 标题一" in md
    assert "正文段落" in md
    assert "| A | B |" in md

    out = tmp_path / "out.docx"
    assert export_to_docx(md, str(out)) is True
    again = Document(str(out))
    texts = [p.text for p in again.paragraphs]
    assert "标题一" in texts
    assert "正文段落" in texts
    assert len(again.tables) == 1


@pytest.mark.xfail(reason="DOCX 页眉页脚尚未导入编辑器配置", strict=False)
def test_docx_header_footer_roundtrip(tmp_path):
    src = tmp_path / "src.docx"
    doc = Document()
    doc.add_paragraph("正文")
    doc.sections[0].header.paragraphs[0].text = "页眉"
    doc.save(str(src))
    md = import_from_docx(str(src))
    out = tmp_path / "out.docx"
    export_to_docx(md, str(out))
    assert Document(str(out)).sections[0].header.paragraphs[0].text == "页眉"


def test_pptx_text_roundtrip(qtbot, tmp_path):
    src = tmp_path / "src.pptx"
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = "标题"
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
    box.text = "正文"
    prs.save(str(src))

    view = BeeShowView()
    qtbot.addWidget(view)
    assert view.open_pptx(str(src)) is True
    assert "标题" in view._slides_md[0]
    assert "正文" in view._slides_md[0]


@pytest.mark.xfail(reason="XLSX 导出为 DataFrame，条件格式/打印设置不保真", strict=False)
def test_xlsx_print_settings_roundtrip(tmp_path):
    """记录当前边界：打印设置不随导出保留。"""
    # 这里只用于标记边界；真实导出仍会丢条件格式/打印设置。
    assert False
