"""Wave 3 W12：PDF 转换基础/保护回归/20 页批注往返。"""
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from beeoffice.pdf_tools import (
    add_watermark, burn_annotations, encrypt_pdf, images_to_pdf,
    pdf_to_images, pdf_to_text,
)


def make_pdf(path, pages=2):
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=300, height=400)
    w.write(str(path))


def test_pdf_to_images_and_back(tmp_path):
    src = tmp_path / "src.pdf"
    make_pdf(src, 2)
    outdir = tmp_path / "imgs"
    info = pdf_to_images(src, outdir)
    assert info["count"] == 2
    imgs = sorted(outdir.glob("*.png"))
    assert len(imgs) == 2
    out = tmp_path / "back.pdf"
    made = images_to_pdf(imgs, out)
    assert made["count"] == 2
    assert len(PdfReader(str(out)).pages) == 2


def test_pdf_to_text(tmp_path):
    src = tmp_path / "src.pdf"
    make_pdf(src, 1)
    out = tmp_path / "out.txt"
    pdf_to_text(src, out)
    assert out.exists()
    assert "第 1 页" in out.read_text(encoding="utf-8")


def test_watermark_and_encrypt(tmp_path):
    src = tmp_path / "src.pdf"
    make_pdf(src, 1)
    wm = tmp_path / "wm.pdf"
    add_watermark(src, wm, "内部资料")
    assert len(PdfReader(str(wm)).pages) == 1
    enc = tmp_path / "enc.pdf"
    encrypt_pdf(src, enc, "secret")
    reader = PdfReader(str(enc))
    assert reader.is_encrypted
    assert reader.decrypt("secret") > 0


def test_20_page_annotation_burn(tmp_path):
    src = tmp_path / "twenty.pdf"
    make_pdf(src, 20)
    annotations = [
        {"page": i, "rect": [10, 10, 80, 20], "type": "highlight",
         "text": "", "color": [1, 0.8, 0], "width": 2}
        for i in range(20)
    ]
    out = tmp_path / "burned.pdf"
    info = burn_annotations(src, out, annotations)
    assert info["annotations"] == 20
    assert len(PdfReader(str(out)).pages) == 20
