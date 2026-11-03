"""pypdf 文档能力：书签、加密、水印、图片签名。"""
import fitz
from PIL import Image
from pypdf import PdfReader

from beeoffice.pdf_backend import PypdfBackend


def _make_pdf(path, pages=2, label="P"):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=300, height=400)
        page.insert_text((50, 50), f"{label}{i + 1}")
    doc.save(str(path))
    doc.close()


def test_pypdf_bookmarks_crud(tmp_path):
    src = tmp_path / "src.pdf"
    _make_pdf(src, 2)
    backend = PypdfBackend()

    added = tmp_path / "added.pdf"
    backend.add_bookmark(src, added, "第一章", 2)
    books = backend.list_bookmarks(added)
    assert books and books[0]["title"] == "第一章"

    updated = tmp_path / "updated.pdf"
    backend.update_bookmark(added, updated, 0, title="新一章", page=1)
    books = backend.list_bookmarks(updated)
    assert books[0]["title"] == "新一章" and books[0]["page"] == 1

    deleted = tmp_path / "deleted.pdf"
    backend.delete_bookmark(updated, deleted, 0)
    assert backend.list_bookmarks(deleted) == []


def test_pypdf_encrypt(tmp_path):
    src = tmp_path / "src.pdf"
    _make_pdf(src, 2)
    out = tmp_path / "enc.pdf"
    PypdfBackend().encrypt_pdf(src, out, "secret", allow_copy=False)
    reader = PdfReader(str(out))
    assert reader.is_encrypted
    assert reader.decrypt("secret") > 0
    assert len(reader.pages) == 2


def test_pypdf_watermark_and_stamp(tmp_path):
    src = tmp_path / "src.pdf"
    _make_pdf(src, 2)
    backend = PypdfBackend()

    wm = tmp_path / "wm.pdf"
    backend.add_watermark(src, wm, "内部资料", opacity=0.2)
    assert len(PdfReader(str(wm)).pages) == 2

    img = tmp_path / "sign.png"
    Image.new("RGBA", (100, 40), (255, 0, 0, 128)).save(img)
    stamped = tmp_path / "stamped.pdf"
    backend.stamp_image(src, stamped, img, page=1, width_ratio=0.2)
    assert len(PdfReader(str(stamped)).pages) == 2
