"""Wave 3 W10：PDF 页面管理器与 20 页往返。"""
from pypdf import PdfReader, PdfWriter

from beeoffice.plugins.pdf_annotator import PDFAnnotator
from beeoffice.plugins.pdf_page_manager import (
    PDFPageManagerDialog, build_reordered_pdf,
)


def make_pdf(path, pages=20):
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=300, height=400)
    w.write(str(path))


def test_build_reordered_pdf(tmp_path):
    src = tmp_path / "src.pdf"
    make_pdf(src, 5)
    out = tmp_path / "out.pdf"
    build_reordered_pdf(src, out, [4, 3, 2, 1, 0])
    assert PdfReader(str(out)).get_num_pages() == 5


def test_page_manager_list(tmp_path, qtbot):
    src = tmp_path / "src.pdf"
    make_pdf(src, 3)
    dlg = PDFPageManagerDialog(str(src))
    qtbot.addWidget(dlg)
    assert dlg._list.count() == 3
    dlg._list.setCurrentRow(0)
    dlg._delete_selected()
    assert dlg._list.count() == 2


def test_20_page_thumbnail_roundtrip(tmp_path, qtbot):
    src = tmp_path / "twenty.pdf"
    make_pdf(src, 20)
    a = PDFAnnotator()
    qtbot.addWidget(a)
    a.open_pdf(str(src))
    qtbot.wait(20)
    assert a._thumb_list.count() == 20
    out = tmp_path / "twenty_out.pdf"
    build_reordered_pdf(src, out, list(range(19, -1, -1)))
    a.open_pdf(str(out))
    qtbot.wait(20)
    assert a._thumb_list.count() == 20
    assert a._page_count == 20
