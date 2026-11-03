# beeoffice/pdf_tools.py
"""PDF 工具统一入口：全部经由 `pdf_backend` 适配层。

- 默认后端：fitz（迁移期兼容）；
- 目标后端：pypdf（pypdfium2 + pypdf + reportlab）；
- 本模块不再直接 import fitz，方便最终移除 PyMuPDF。
"""
from __future__ import annotations

from typing import Iterable, Optional

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
