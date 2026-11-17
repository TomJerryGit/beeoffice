"""Wave5 W4：PDF 插入/加工/对比。"""
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from beeoffice.pdf_tools import (
    add_header_footer, add_page_numbers, compare_pdf_text,
    insert_blank_page, reverse_pages,
)


def make_pdf(path, pages=2, text=""):
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=300, height=400)
    w.write(str(path))
    if text:
        c = canvas.Canvas(str(path))
        for i in range(pages):
            c.drawString(30, 300, f"{text}-{i + 1}")
            c.showPage()
        c.save()


def test_insert_reverse_and_overlays(tmp_path):
    src = tmp_path / "src.pdf"
    make_pdf(src, 2)
    assert insert_blank_page(src, tmp_path / "blank.pdf", 1)["pages"] == 3
    assert reverse_pages(src, tmp_path / "rev.pdf")["pages"] == 2
    assert add_page_numbers(src, tmp_path / "num.pdf")["pages"] == 2
    assert add_header_footer(src, tmp_path / "hf.pdf", "H", "F")["pages"] == 2


def test_compare_text(tmp_path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    make_pdf(a, 1, "alpha")
    make_pdf(b, 1, "beta")
    result = compare_pdf_text(a, b)
    assert result["additions"] >= 1
    assert result["deletions"] >= 1


def test_pdf_ribbon_has_insert(qtbot):
    from beeoffice.plugins.pdf_annotator import PDFAnnotator
    w = PDFAnnotator()
    qtbot.addWidget(w)
    assert "插入" in w._ribbon.tab_names()
