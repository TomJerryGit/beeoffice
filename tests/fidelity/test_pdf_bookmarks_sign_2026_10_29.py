"""S3：PDF 书签 + 图片签名/图章。"""
import fitz
from PIL import Image

from beeoffice.pdf_tools import add_bookmark, list_bookmarks, stamp_image


def test_bookmark_roundtrip(tmp_path):
    src = tmp_path / "a.pdf"
    doc = fitz.open(); doc.new_page(); doc.new_page(); doc.save(src); doc.close()
    out = tmp_path / "b.pdf"
    add_bookmark(src, out, "第一章", 2)
    toc = list_bookmarks(out)
    assert toc and toc[0]["title"] == "第一章" and toc[0]["page"] == 2


def test_stamp_image(tmp_path):
    src = tmp_path / "a.pdf"
    doc = fitz.open(); doc.new_page(); doc.save(src); doc.close()
    img = tmp_path / "sign.png"
    Image.new("RGBA", (80, 40), (255, 0, 0, 180)).save(img)
    out = tmp_path / "signed.pdf"
    stamp_image(src, out, img, page=1, x=0.6, y=0.7)
    doc = fitz.open(out)
    try:
        assert doc.page_count == 1
        assert doc[0].get_images(full=True)
    finally:
        doc.close()
