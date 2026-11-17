# beeoffice/pdf_tools.py
"""PDF 工具统一入口：全部经由 `pdf_backend` 适配层。

- 默认后端：pypdf（pypdfium2 + pypdf + reportlab）；
- 目标后端：pypdf（pypdfium2 + pypdf + reportlab）；
- 本模块不再直接 import fitz，方便最终移除 PyMuPDF。
"""
from __future__ import annotations

from typing import Iterable, Optional
from pathlib import Path

from beeoffice.pdf_backend import get_backend
from beeoffice.pdf_common import PdfToolError, parse_page_spec

__all__ = [
    "PdfToolError", "parse_page_spec",
    "merge_pdfs", "split_pdf", "extract_pages", "delete_pages",
    "rotate_pages", "crop_pages", "insert_pages", "replace_pages",
    "compress_pdf", "encrypt_pdf", "add_watermark", "extract_text",
    "extract_images", "list_bookmarks", "add_bookmark",
    "delete_bookmark", "update_bookmark", "stamp_image",
    "burn_annotations",
]


def _b():
    return get_backend()


def merge_pdfs(srcs: Iterable, out) -> dict:
    return _b().merge_pdfs(srcs, out)


def split_pdf(src, outdir, ranges: Optional[str] = None) -> dict:
    return _b().split_pdf(src, outdir, ranges)


def extract_pages(src, out, pages: Optional[str] = None) -> dict:
    return _b().extract_pages(src, out, pages)


def delete_pages(src, out, pages: str) -> dict:
    return _b().delete_pages(src, out, pages)


def rotate_pages(src, out, pages: Optional[str] = None,
                 angle: int = 90) -> dict:
    return _b().rotate_pages(src, out, pages=pages, angle=angle)


def crop_pages(src, out, top_mm=0, bottom_mm=0,
               left_mm=0, right_mm=0) -> dict:
    return _b().crop_pages(src, out, top_mm=top_mm, bottom_mm=bottom_mm,
                           left_mm=left_mm, right_mm=right_mm)


def insert_pages(src, insert_src, out, at: int = 1) -> dict:
    return _b().insert_pages(src, insert_src, out, at=at)


def replace_pages(src, replace_src, out, pages: str) -> dict:
    return _b().replace_pages(src, replace_src, out, pages)


def compress_pdf(src, out) -> dict:
    return _b().compress_pdf(src, out)


def encrypt_pdf(src, out, user_password: str,
                owner_password: Optional[str] = None,
                allow_print: bool = True,
                allow_copy: bool = True) -> dict:
    return _b().encrypt_pdf(
        src, out, user_password,
        owner_password=owner_password,
        allow_print=allow_print, allow_copy=allow_copy,
    )


def add_watermark(src, out, text: str, opacity: float = 0.15,
                  fontsize: float = 48.0,
                  pages: Optional[str] = None) -> dict:
    return _b().add_watermark(
        src, out, text, opacity=opacity, fontsize=fontsize, pages=pages
    )


def extract_text(src, out, pages: Optional[str] = None) -> dict:
    return _b().extract_text(src, out, pages)


def extract_images(src, outdir, pages: Optional[str] = None) -> dict:
    return _b().extract_images(src, outdir, pages)


def list_bookmarks(src) -> list[dict]:
    return _b().list_bookmarks(src)


def add_bookmark(src, out, title: str, page: int = 1) -> dict:
    return _b().add_bookmark(src, out, title, page)


def delete_bookmark(src, out, index: int) -> dict:
    return _b().delete_bookmark(src, out, index)


def update_bookmark(src, out, index: int, title: str | None = None,
                    page: int | None = None) -> dict:
    return _b().update_bookmark(src, out, index, title=title, page=page)


def stamp_image(src, out, image_path, page: int = 1,
                x: float = 0.6, y: float = 0.65,
                width_ratio: float = 0.25, opacity: float = 1.0) -> dict:
    return _b().stamp_image(
        src, out, image_path, page,
        x=x, y=y, width_ratio=width_ratio, opacity=opacity,
    )


def burn_annotations(src, out, annotations) -> dict:
    return _b().burn_annotations(src, out, annotations)

# ==================== W12 基础转换 ====================
def pdf_to_images(src, outdir, pages=None, scale: float = 2.0) -> dict:
    """把 PDF 每页渲染为 PNG。"""
    from pathlib import Path
    from beeoffice.pdf_common import parse_page_spec
    b = _b()
    n = b.page_count(src)
    idxs = parse_page_spec(pages, n) if pages else list(range(n))
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    saved = []
    for i in idxs:
        target = outdir / f"page_{i + 1:03d}.png"
        b.render_page_png(src, i + 1, target, scale=scale)
        saved.append(str(target))
    return {"source": str(src), "output_dir": str(outdir),
            "count": len(saved), "images": saved}


def images_to_pdf(images, out) -> dict:
    """把 PNG/JPG 图片按顺序合成为 PDF。"""
    from pathlib import Path
    from PIL import Image
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out))
    count = 0
    for img_path in images:
        with Image.open(img_path) as im:
            w, h = im.size
            page_w = max(100.0, min(595.0, w * 0.75))
            page_h = max(100.0, min(842.0, h * 0.75))
            c.setPageSize((page_w, page_h))
            c.drawImage(ImageReader(str(img_path)), 0, 0,
                        width=page_w, height=page_h,
                        preserveAspectRatio=True, anchor="c")
            c.showPage()
            count += 1
    c.save()
    return {"output": str(out), "count": count}


def pdf_to_text(src, out, pages=None) -> dict:
    """PDF 文本导出。"""
    return _b().extract_text(src, out, pages=pages)


# ==================== Wave5 P1：插入/加工/对比 ====================
def insert_blank_page(src, out, before_page: int = 1) -> dict:
    """在第 before_page 页前插入一页空白页（1-based）。"""
    from pypdf import PdfReader, PdfWriter
    from pypdf._page import PageObject
    reader = PdfReader(str(src))
    writer = PdfWriter()
    inserted = False
    for i, page in enumerate(reader.pages):
        if not inserted and i + 1 >= int(before_page):
            writer.add_page(PageObject.create_blank_page(
                width=float(page.mediabox.width),
                height=float(page.mediabox.height),
            ))
            inserted = True
        writer.add_page(page)
    if not inserted:
        last = reader.pages[-1]
        writer.add_page(PageObject.create_blank_page(
            width=float(last.mediabox.width),
            height=float(last.mediabox.height),
        ))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        writer.write(f)
    return {"output": str(out), "pages": len(writer.pages)}


def reverse_pages(src, out) -> dict:
    from pypdf import PdfReader, PdfWriter
    reader = PdfReader(str(src))
    writer = PdfWriter()
    for page in reversed(reader.pages):
        writer.add_page(page)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        writer.write(f)
    return {"output": str(out), "pages": len(writer.pages)}


def _overlay_pdf(src, out, draw) -> int:
    from io import BytesIO
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas
    reader = PdfReader(str(src))
    writer = PdfWriter()
    for page in reader.pages:
        w = float(page.mediabox.width)
        h = float(page.mediabox.height)
        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=(w, h))
        draw(c, w, h)
        c.save()
        buf.seek(0)
        overlay_page = PdfReader(buf).pages[0]
        page.merge_page(overlay_page)
        writer.add_page(page)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        writer.write(f)
    return len(writer.pages)


def add_page_numbers(src, out, fmt="第 {page} 页", start=1,
                     position="bottom-center", fontsize=10) -> dict:
    def draw(c, w, h):
        total = len(__import__("pypdf").PdfReader(str(src)).pages)
        for idx in range(total):
            text = fmt.format(page=start + idx, total=start + total - 1, index=start + idx)
            # 每页在 _overlay 中单独绘制，按当前页序号
            break
    from pypdf import PdfReader
    total = len(PdfReader(str(src)).pages)

    def draw_page(c, w, h, page_index):
        text = fmt.format(page=start + page_index,
                          total=start + total - 1,
                          index=start + page_index)
        c.setFont("Helvetica", fontsize)
        x = w / 2
        y = 22
        if position.startswith("top"):
            y = h - 24
        if position.endswith("left"):
            x = 40
        elif position.endswith("right"):
            x = w - 40
        c.drawCentredString(x, y, text)

    from io import BytesIO
    from reportlab.pdfgen import canvas
    from pypdf import PdfWriter
    reader = PdfReader(str(src))
    writer = PdfWriter()
    for i, page in enumerate(reader.pages):
        w = float(page.mediabox.width); h = float(page.mediabox.height)
        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=(w, h))
        draw_page(c, w, h, i)
        c.save(); buf.seek(0)
        page.merge_page(PdfReader(buf).pages[0])
        writer.add_page(page)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        writer.write(f)
    return {"output": str(out), "pages": len(writer.pages)}


def add_header_footer(src, out, header="", footer="", fontsize=9) -> dict:
    from io import BytesIO
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas
    reader = PdfReader(str(src))
    writer = PdfWriter()
    for page in reader.pages:
        w = float(page.mediabox.width); h = float(page.mediabox.height)
        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=(w, h))
        c.setFont("Helvetica", fontsize)
        if header:
            c.drawCentredString(w / 2, h - 28, header)
        if footer:
            c.drawCentredString(w / 2, 24, footer)
        c.save(); buf.seek(0)
        page.merge_page(PdfReader(buf).pages[0])
        writer.add_page(page)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        writer.write(f)
    return {"output": str(out), "pages": len(writer.pages)}


def compare_pdf_text(a, b) -> dict:
    """文本级 PDF 对比，返回新增/删除/修改行数与报告。"""
    import difflib
    from beeoffice.pdf_backend import get_backend
    backend = get_backend()
    ta = "\n".join(backend.read_text_pages(a))
    tb = "\n".join(backend.read_text_pages(b))
    diff = list(difflib.unified_diff(
        ta.splitlines(), tb.splitlines(), fromfile=str(a), tofile=str(b), lineterm=""
    ))
    added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
    return {"additions": added, "deletions": removed, "diff": "\n".join(diff)}
