"""pypdf 页面结构后端：与 fitz 兼容实现的页面语义对齐。"""
import fitz
import pytest
from pypdf import PdfReader

from beeoffice.pdf_backend import PypdfBackend
from beeoffice.pdf_common import PdfToolError


def _make_pdf(path, pages=3, label="P"):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=300, height=400)
        page.insert_text((50, 50), f"{label}{i + 1}")
    doc.save(str(path))
    doc.close()


def _texts(path):
    reader = PdfReader(str(path))
    return [p.extract_text() or "" for p in reader.pages]


def _count(path):
    return len(PdfReader(str(path)).pages)


def test_merge_extract_delete_split(tmp_path):
    a, b = tmp_path / "a.pdf", tmp_path / "b.pdf"
    _make_pdf(a, 2, "A")
    _make_pdf(b, 1, "B")
    backend = PypdfBackend()

    merged = tmp_path / "merged.pdf"
    info = backend.merge_pdfs([a, b], merged)
    assert info["pages"] == 3 and _count(merged) == 3

    extracted = tmp_path / "extract.pdf"
    backend.extract_pages(a, extracted, "2")
    assert _count(extracted) == 1 and "A2" in _texts(extracted)[0]

    deleted = tmp_path / "deleted.pdf"
    backend.delete_pages(a, deleted, "1")
    assert _count(deleted) == 1 and "A2" in _texts(deleted)[0]

    outdir = tmp_path / "split"
    result = backend.split_pdf(a, outdir, "1;2")
    assert len(result["outputs"]) == 2
    assert all((outdir / f).is_file() for f in (
        "a_p1.pdf", "a_p2.pdf"))


def test_rotate_crop_insert_replace_compress(tmp_path):
    src, ins, repl = (tmp_path / "src.pdf", tmp_path / "ins.pdf",
                      tmp_path / "repl.pdf")
    _make_pdf(src, 3, "A")
    _make_pdf(ins, 1, "B")
    _make_pdf(repl, 1, "R")
    backend = PypdfBackend()

    rotated = tmp_path / "rotated.pdf"
    backend.rotate_pages(src, rotated, "1", 90)
    assert PdfReader(str(rotated)).pages[0].rotation == 90

    cropped = tmp_path / "cropped.pdf"
    backend.crop_pages(src, cropped, 10, 10, 10, 10)
    box = PdfReader(str(cropped)).pages[0].cropbox
    assert float(box.width) < 300 and float(box.height) < 400

    inserted = tmp_path / "inserted.pdf"
    backend.insert_pages(src, ins, inserted, at=2)
    assert _count(inserted) == 4
    assert "B1" in _texts(inserted)[1]

    replaced = tmp_path / "replaced.pdf"
    backend.replace_pages(src, repl, replaced, "2")
    texts = _texts(replaced)
    assert len(texts) == 3 and "R1" in texts[1]

    compressed = tmp_path / "compressed.pdf"
    backend.compress_pdf(src, compressed)
    assert _count(compressed) == 3


def test_invalid_spec_and_missing_file(tmp_path):
    backend = PypdfBackend()
    with pytest.raises(PdfToolError):
        backend.extract_pages(tmp_path / "missing.pdf", tmp_path / "x.pdf")
    src = tmp_path / "src.pdf"
    _make_pdf(src)
    with pytest.raises(PdfToolError):
        backend.delete_pages(src, tmp_path / "x.pdf", "99")
