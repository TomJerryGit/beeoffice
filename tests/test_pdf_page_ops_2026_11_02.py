"""PDF 页面工具：裁剪/插入/替换/压缩（2026-11-02）。"""
import fitz

from beeoffice.pdf_tools import (
    compress_pdf,
    crop_pages,
    insert_pages,
    replace_pages,
)


def _make_pdf(path, pages=3, label="P"):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=300, height=400)
        page.insert_text((50, 50), f"{label}{i + 1}")
    doc.save(str(path))
    doc.close()


def test_crop_pages(tmp_path):
    src = tmp_path / "src.pdf"
    out = tmp_path / "cropped.pdf"
    _make_pdf(src)
    info = crop_pages(src, out, top_mm=10, bottom_mm=10,
                      left_mm=10, right_mm=10)
    assert info["pages"] == 3
    doc = fitz.open(str(out))
    try:
        assert doc[0].cropbox.width < 300
        assert doc[0].cropbox.height < 400
    finally:
        doc.close()


def test_insert_pages(tmp_path):
    src = tmp_path / "src.pdf"
    ins = tmp_path / "ins.pdf"
    out = tmp_path / "inserted.pdf"
    _make_pdf(src, 3, "A")
    _make_pdf(ins, 2, "B")
    info = insert_pages(src, ins, out, at=2)
    assert info["pages"] == 5
    doc = fitz.open(str(out))
    try:
        assert "B1" in doc[1].get_text()
    finally:
        doc.close()


def test_replace_pages(tmp_path):
    src = tmp_path / "src.pdf"
    repl = tmp_path / "repl.pdf"
    out = tmp_path / "replaced.pdf"
    _make_pdf(src, 3, "A")
    _make_pdf(repl, 1, "R")
    info = replace_pages(src, repl, out, pages="2")
    assert info["pages"] == 3
    doc = fitz.open(str(out))
    try:
        assert "R1" in doc[1].get_text()
    finally:
        doc.close()


def test_compress_pdf(tmp_path):
    src = tmp_path / "src.pdf"
    out = tmp_path / "compressed.pdf"
    _make_pdf(src, 5)
    info = compress_pdf(src, out)
    assert info["pages"] == 5
    assert out.is_file()
