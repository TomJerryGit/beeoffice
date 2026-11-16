"""Wave 3 W9：PDF 统一 Ribbon + 页面缩略图。"""
import tempfile
from pathlib import Path

from pypdf import PdfWriter

from beeoffice.plugins.pdf_annotator import PDFAnnotator


def make_pdf(path, pages=2):
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=300, height=400)
    w.write(str(path))


def test_pdf_ribbon_tabs(qtbot):
    a = PDFAnnotator()
    qtbot.addWidget(a)
    names = a._ribbon.tab_names()
    for expected in ("开始", "标注", "页面", "保护", "转换"):
        assert expected in names


def test_pdf_thumbnails(qtbot, tmp_path):
    pdf = tmp_path / "sample.pdf"
    make_pdf(pdf, 2)
    a = PDFAnnotator()
    qtbot.addWidget(a)
    a.open_pdf(str(pdf))
    qtbot.wait(20)
    assert a._thumb_list.count() == 2
    assert "1/2" in a._page_label.text()
    a._thumb_list.setCurrentRow(1)
    qtbot.wait(20)
    assert a._current_page == 1
    assert "2/2" in a._page_label.text()
