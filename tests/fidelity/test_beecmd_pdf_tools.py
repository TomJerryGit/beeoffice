# tests/fidelity/test_beecmd_pdf_tools.py
"""
beecmd v0.5：PDF 页面/权限工具回归（PyMuPDF，零 Qt）。

覆盖 WPS 会员里**唯一低成本可追平**的一类 PDF 能力：
合并 / 拆分 / 提取页 / 删除页 / 加密权限 / 水印 / 提取文本 / 提取图片。
所有操作都生成新文件、**不修改源文件**；坏输入给 `PdfToolError` 而不是崩溃。
"""
import sys
from pathlib import Path

import fitz
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from beeoffice.pdf_tools import (  # noqa: E402
    PdfToolError,
    add_watermark,
    delete_pages,
    encrypt_pdf,
    extract_images,
    extract_pages,
    extract_text,
    merge_pdfs,
    parse_page_spec,
    split_pdf,
)


def _make_pdf(path: Path, pages: int = 3, prefix: str = "P") -> Path:
    doc = fitz.open()
    for index in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"{prefix}{index + 1}")
    doc.save(str(path))
    doc.close()
    return path


# ==================== 页码表达式 ====================

class TestPageSpec:
    def test_single_and_ranges(self):
        assert parse_page_spec("2", 5) == [1]
        assert parse_page_spec("1-3", 5) == [0, 1, 2]
        assert parse_page_spec("3-", 5) == [2, 3, 4]
        assert parse_page_spec("-2", 5) == [0, 1]
        assert parse_page_spec("1,3-4", 5) == [0, 2, 3]
        assert parse_page_spec("all", 3) == [0, 1, 2]
        assert parse_page_spec("", 3) == [0, 1, 2]

    def test_invalid_or_out_of_range(self):
        with pytest.raises(PdfToolError):
            parse_page_spec("0", 3)
        with pytest.raises(PdfToolError):
            parse_page_spec("4", 3)
        with pytest.raises(PdfToolError):
            parse_page_spec("a-b", 3)


# ==================== 页面操作 ====================

def test_merge_pdfs(tmp_path):
    a = _make_pdf(tmp_path / "a.pdf", 2, "A")
    b = _make_pdf(tmp_path / "b.pdf", 3, "B")
    out = tmp_path / "merged.pdf"
    info = merge_pdfs([a, b], out)
    assert info["pages"] == 5
    assert out.is_file()
    with fitz.open(out) as doc:
        assert doc.page_count == 5
        assert "A1" in doc[0].get_text()
        assert "B1" in doc[2].get_text()


def test_split_pdf_every_page(tmp_path):
    src = _make_pdf(tmp_path / "s.pdf", 3)
    outdir = tmp_path / "out"
    info = split_pdf(src, outdir)
    assert info["pages"] == 3
    assert len(info["outputs"]) == 3
    assert all(Path(p).is_file() for p in info["outputs"])


def test_split_pdf_by_ranges(tmp_path):
    src = _make_pdf(tmp_path / "s.pdf", 5)
    outdir = tmp_path / "ranges"
    info = split_pdf(src, outdir, ranges="1-2;3-")
    assert len(info["outputs"]) == 2
    out_pages = []
    for path in info["outputs"]:
        with fitz.open(path) as doc:
            out_pages.append(doc.page_count)
    assert out_pages == [2, 3]


def test_extract_and_delete_pages(tmp_path):
    src = _make_pdf(tmp_path / "s.pdf", 4)
    extracted = tmp_path / "extract.pdf"
    info = extract_pages(src, extracted, "2-3")
    assert info["pages"] == 2
    with fitz.open(extracted) as doc:
        assert doc.page_count == 2

    deleted = tmp_path / "delete.pdf"
    info = delete_pages(src, deleted, "2,4")
    assert info["pages"] == 2
    with fitz.open(deleted) as doc:
        assert doc.page_count == 2


def test_source_pdf_never_modified(tmp_path):
    src = _make_pdf(tmp_path / "s.pdf", 2)
    before = src.read_bytes()
    merge_pdfs([src], tmp_path / "m.pdf")
    split_pdf(src, tmp_path / "d")
    add_watermark(src, tmp_path / "w.pdf", "DRAFT")
    assert src.read_bytes() == before, "源 PDF 被修改了"


# ==================== 加密 / 水印 / 文本 ====================

def test_encrypt_pdf_requires_password(tmp_path):
    src = _make_pdf(tmp_path / "s.pdf", 2)
    out = tmp_path / "locked.pdf"
    encrypt_pdf(src, out, user_password="s3cret", allow_print=False,
                allow_copy=False)
    with fitz.open(out) as doc:
        assert int(doc.needs_pass) > 0
        assert doc.authenticate("wrong") == 0
        assert doc.authenticate("s3cret") > 0
        assert doc.page_count == 2


def test_watermark_text_present(tmp_path):
    src = _make_pdf(tmp_path / "s.pdf", 2)
    out = tmp_path / "wm.pdf"
    info = add_watermark(src, out, "内部资料", opacity=0.2, pages="1")
    assert info["watermarked_pages"] == 1
    with fitz.open(out) as doc:
        assert "内部资料" in doc[0].get_text()


def test_extract_text(tmp_path):
    src = _make_pdf(tmp_path / "s.pdf", 3, "Content")
    out = tmp_path / "out.txt"
    info = extract_text(src, out)
    assert info["pages"] == 3
    text = out.read_text(encoding="utf-8")
    assert "Content1" in text and "Content3" in text
    assert "第 3 页" in text


def test_extract_images(tmp_path):
    from PIL import Image

    image_path = tmp_path / "pic.png"
    Image.new("RGB", (32, 32), "red").save(image_path)
    src = tmp_path / "img.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_image(fitz.Rect(72, 72, 172, 172), filename=str(image_path))
    doc.save(str(src))
    doc.close()

    outdir = tmp_path / "imgs"
    info = extract_images(src, outdir)
    assert info["count"] >= 1
    assert all(Path(p).is_file() for p in info["images"])


# ==================== CLI 集成 ====================

def test_cli_pdf_merge_and_version(tmp_path):
    from beeoffice import beecmd

    a = _make_pdf(tmp_path / "a.pdf", 1)
    b = _make_pdf(tmp_path / "b.pdf", 2)
    out = tmp_path / "cli_merged.pdf"
    assert beecmd.main(["pdf-merge", str(a), str(b), "-o", str(out)]) == 0
    with fitz.open(out) as doc:
        assert doc.page_count == 3

    assert beecmd.main(["version"]) == 0


def test_cli_pdf_watermark_and_encrypt(tmp_path):
    from beeoffice import beecmd

    src = _make_pdf(tmp_path / "s.pdf", 2)
    wm = tmp_path / "wm.pdf"
    assert beecmd.main([
        "pdf-watermark", str(src), "-o", str(wm), "--text", "复制无效"
    ]) == 0
    assert wm.is_file()

    locked = tmp_path / "locked.pdf"
    assert beecmd.main([
        "pdf-encrypt", str(src), "-o", str(locked),
        "--user-password", "pw123",
    ]) == 0
    with fitz.open(locked) as doc:
        assert int(doc.needs_pass) > 0
