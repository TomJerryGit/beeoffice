# -*- coding: utf-8 -*-
"""
PDF 页面操作（阶段四 P0-1）

对标 WPS 会员的"PDF 合并/拆分"，验证页面级操作的正确性：
页数、页面内容、范围解析、错误处理。

刻意不测 PDF→Office 转换——那不在本阶段范围。
"""
import pytest

fitz = pytest.importorskip("fitz")

from beeoffice.plugins import pdf_pages  # noqa: E402


def make_pdf(path, texts):
    """生成一个每页含指定文字的 PDF。"""
    doc = fitz.open()
    for text in texts:
        page = doc.new_page(width=300, height=400)
        page.insert_text((40, 80), text, fontsize=18)
    doc.save(str(path))
    doc.close()
    return path


def page_texts(path):
    doc = fitz.open(str(path))
    try:
        return [p.get_text().strip() for p in doc]
    finally:
        doc.close()


@pytest.fixture
def sample(tmp_path):
    return make_pdf(tmp_path / "src.pdf", ["page-A", "page-B", "page-C", "page-D"])


# ==================== 范围解析 ====================
def test_parse_simple_range():
    assert pdf_pages.parse_page_ranges("1-3", 5) == [1, 2, 3]


def test_parse_mixed_and_open_ended():
    assert pdf_pages.parse_page_ranges("1-2,4,", 5) == [1, 2, 4]
    assert pdf_pages.parse_page_ranges("3-", 5) == [3, 4, 5]


def test_parse_dedupes_and_keeps_order():
    assert pdf_pages.parse_page_ranges("2,1,2,1-2", 5) == [2, 1]


def test_parse_rejects_out_of_range():
    with pytest.raises(pdf_pages.PdfPageError, match="超出范围"):
        pdf_pages.parse_page_ranges("1-9", 5)


def test_parse_rejects_reversed_range():
    with pytest.raises(pdf_pages.PdfPageError, match="颠倒"):
        pdf_pages.parse_page_ranges("4-2", 5)


def test_parse_rejects_garbage():
    with pytest.raises(pdf_pages.PdfPageError, match="无法识别"):
        pdf_pages.parse_page_ranges("abc", 5)


def test_parse_rejects_zero_page():
    with pytest.raises(pdf_pages.PdfPageError, match="从 1 开始"):
        pdf_pages.parse_page_ranges("0-2", 5)


# ==================== 合并 ====================
def test_merge_keeps_order(tmp_path, sample):
    other = make_pdf(tmp_path / "other.pdf", ["page-E"])
    out = tmp_path / "merged.pdf"
    total = pdf_pages.merge_pdfs([sample, other], out)
    assert total == 5
    assert page_texts(out) == [
        "page-A", "page-B", "page-C", "page-D", "page-E"
    ]


def test_merge_requires_files(tmp_path):
    with pytest.raises(pdf_pages.PdfPageError, match="至少选择一个"):
        pdf_pages.merge_pdfs([], tmp_path / "x.pdf")


def test_merge_missing_file(tmp_path, sample):
    with pytest.raises(pdf_pages.PdfPageError, match="不存在"):
        pdf_pages.merge_pdfs([sample, tmp_path / "nope.pdf"], tmp_path / "x.pdf")


# ==================== 提取 ====================
def test_extract_pages(tmp_path, sample):
    out = tmp_path / "out.pdf"
    n = pdf_pages.extract_pages(sample, "2,4", out)
    assert n == 2
    assert page_texts(out) == ["page-B", "page-D"]


def test_extract_keeps_order_of_input(tmp_path, sample):
    out = tmp_path / "out.pdf"
    pdf_pages.extract_pages(sample, "4,1", out)
    assert page_texts(out) == ["page-D", "page-A"]


# ==================== 删除 ====================
def test_delete_pages(tmp_path, sample):
    out = tmp_path / "out.pdf"
    n = pdf_pages.delete_pages(sample, "2-3", out)
    assert n == 2
    assert page_texts(out) == ["page-A", "page-D"]


def test_delete_all_is_rejected(tmp_path, sample):
    with pytest.raises(pdf_pages.PdfPageError, match="不能删除全部"):
        pdf_pages.delete_pages(sample, "1-4", tmp_path / "out.pdf")


# ==================== 旋转 ====================
def test_rotate_pages(tmp_path, sample):
    out = tmp_path / "out.pdf"
    n = pdf_pages.rotate_pages(sample, "1", 90, out)
    assert n == 1
    doc = fitz.open(str(out))
    try:
        assert doc[0].rotation == 90
        assert doc[1].rotation == 0
    finally:
        doc.close()


def test_rotate_rejects_bad_angle(tmp_path, sample):
    with pytest.raises(pdf_pages.PdfPageError, match="90 的倍数"):
        pdf_pages.rotate_pages(sample, "1", 45, tmp_path / "out.pdf")


# ==================== 拆分 ====================
def test_split_each_page(tmp_path, sample):
    files = pdf_pages.split_pages(sample, tmp_path / "split")
    assert len(files) == 4
    assert page_texts(files[1]) == ["page-B"]


def test_split_every_n(tmp_path, sample):
    files = pdf_pages.split_every(sample, 3, tmp_path / "chunks")
    assert len(files) == 2
    assert len(page_texts(files[0])) == 3
    assert page_texts(files[1]) == ["page-D"]


def test_split_by_ranges(tmp_path, sample):
    files = pdf_pages.split_ranges(
        sample, ["1-2", "4"], tmp_path / "ranges"
    )
    assert len(files) == 2
    assert page_texts(files[0]) == ["page-A", "page-B"]
    assert page_texts(files[1]) == ["page-D"]


def test_split_every_rejects_zero(tmp_path, sample):
    with pytest.raises(pdf_pages.PdfPageError, match="大于 0"):
        pdf_pages.split_every(sample, 0, tmp_path / "x")


# ==================== 异常输入 ====================
def test_missing_source_file(tmp_path):
    with pytest.raises(pdf_pages.PdfPageError, match="不存在"):
        pdf_pages.page_count(tmp_path / "nope.pdf")


def test_non_pdf_file(tmp_path):
    bad = tmp_path / "not.pdf"
    bad.write_text("这不是 PDF", encoding="utf-8")
    with pytest.raises(pdf_pages.PdfPageError):
        pdf_pages.page_count(bad)
