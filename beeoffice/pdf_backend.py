# beeoffice/pdf_backend.py
"""PDF 后端适配层：把 PyMuPDF(fitz) 隔离在单一入口后面。

目标（S0/S1）：
  - 上层只依赖 `PdfBackend`，不再直接 `import fitz`；
  - 阶段 1：`FitzBackend` 保持现有行为；
  - 阶段 2：`PypdfBackend` 用 pypdfium2 + pypdf + reportlab 替换；
  - 最终删除 fitz 依赖。

迁移映射见 docs/PDF后端迁移映射-2026-11-03.md。
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path


class PdfBackendError(RuntimeError):
    pass


class PdfBackend(ABC):
    """PDF 能力抽象；方法签名与 pdf_tools 保持一致，便于逐步迁移。"""

    name = "base"

    # ---------- 查询/渲染 ----------
    @abstractmethod
    def page_count(self, src) -> int: ...

    @abstractmethod
    def render_page_png(self, src, page: int, out, scale: float = 2.0) -> dict: ...

    # ---------- 页面结构 ----------
    @abstractmethod
    def merge_pdfs(self, srcs, out) -> dict: ...

    @abstractmethod
    def split_pdf(self, src, outdir, ranges=None) -> dict: ...

    @abstractmethod
    def extract_pages(self, src, out, pages=None) -> dict: ...

    @abstractmethod
    def delete_pages(self, src, out, pages) -> dict: ...

    @abstractmethod
    def crop_pages(self, src, out, top_mm=0, bottom_mm=0,
                   left_mm=0, right_mm=0) -> dict: ...

    @abstractmethod
    def insert_pages(self, src, insert_src, out, at: int = 1) -> dict: ...

    @abstractmethod
    def replace_pages(self, src, replace_src, out, pages) -> dict: ...

    @abstractmethod
    def compress_pdf(self, src, out) -> dict: ...

    # ---------- 文档能力 ----------
    @abstractmethod
    def encrypt_pdf(self, src, out, user_password: str,
                    allow_print: bool = True, allow_copy: bool = True) -> dict: ...

    @abstractmethod
    def add_watermark(self, src, out, text: str,
                      opacity: float = 0.15, pages=None) -> dict: ...

    @abstractmethod
    def extract_text(self, src, out, pages=None) -> dict: ...

    @abstractmethod
    def extract_images(self, src, outdir, pages=None) -> dict: ...

    @abstractmethod
    def list_bookmarks(self, src) -> list[dict]: ...

    @abstractmethod
    def add_bookmark(self, src, out, title: str, page: int = 1) -> dict: ...

    @abstractmethod
    def delete_bookmark(self, src, out, index: int) -> dict: ...

    @abstractmethod
    def update_bookmark(self, src, out, index: int,
                        title: str | None = None,
                        page: int | None = None) -> dict: ...

    @abstractmethod
    def stamp_image(self, src, out, image_path, page: int = 1,
                    x: float = 0.6, y: float = 0.65,
                    width_ratio: float = 0.25,
                    opacity: float = 1.0) -> dict: ...


class FitzBackend(PdfBackend):
    """阶段 1 兼容后端：委托现有 pdf_tools（内部仍是 PyMuPDF）。"""

    name = "fitz"

    def _tools(self):
        from beeoffice import pdf_tools
        return pdf_tools

    def _fitz(self):
        import fitz
        return fitz

    def page_count(self, src) -> int:
        fitz = self._fitz()
        doc = fitz.open(str(src))
        try:
            return len(doc)
        finally:
            doc.close()

    def render_page_png(self, src, page: int, out, scale: float = 2.0) -> dict:
        fitz = self._fitz()
        doc = fitz.open(str(src))
        try:
            index = max(0, min(int(page) - 1, len(doc) - 1))
            mat = fitz.Matrix(scale, scale)
            pix = doc.load_page(index).get_pixmap(matrix=mat)
            out = Path(out)
            out.parent.mkdir(parents=True, exist_ok=True)
            pix.save(str(out))
            return {"out": str(out), "page": index + 1, "width": pix.width,
                    "height": pix.height}
        finally:
            doc.close()

    def merge_pdfs(self, srcs, out) -> dict:
        return self._tools().merge_pdfs(srcs, out)

    def split_pdf(self, src, outdir, ranges=None) -> dict:
        return self._tools().split_pdf(src, outdir, ranges)

    def extract_pages(self, src, out, pages=None) -> dict:
        return self._tools().extract_pages(src, out, pages)

    def delete_pages(self, src, out, pages) -> dict:
        return self._tools().delete_pages(src, out, pages)

    def crop_pages(self, src, out, top_mm=0, bottom_mm=0,
                   left_mm=0, right_mm=0) -> dict:
        return self._tools().crop_pages(
            src, out, top_mm=top_mm, bottom_mm=bottom_mm,
            left_mm=left_mm, right_mm=right_mm,
        )

    def insert_pages(self, src, insert_src, out, at: int = 1) -> dict:
        return self._tools().insert_pages(src, insert_src, out, at=at)

    def replace_pages(self, src, replace_src, out, pages) -> dict:
        return self._tools().replace_pages(src, replace_src, out, pages)

    def compress_pdf(self, src, out) -> dict:
        return self._tools().compress_pdf(src, out)

    def encrypt_pdf(self, src, out, user_password: str,
                    allow_print: bool = True, allow_copy: bool = True) -> dict:
        return self._tools().encrypt_pdf(
            src, out, user_password,
            allow_print=allow_print, allow_copy=allow_copy,
        )

    def add_watermark(self, src, out, text: str,
                      opacity: float = 0.15, pages=None) -> dict:
        return self._tools().add_watermark(
            src, out, text, opacity=opacity, pages=pages
        )

    def extract_text(self, src, out, pages=None) -> dict:
        return self._tools().extract_text(src, out, pages)

    def extract_images(self, src, outdir, pages=None) -> dict:
        return self._tools().extract_images(src, outdir, pages)

    def list_bookmarks(self, src) -> list[dict]:
        return self._tools().list_bookmarks(src)

    def add_bookmark(self, src, out, title: str, page: int = 1) -> dict:
        return self._tools().add_bookmark(src, out, title, page)

    def delete_bookmark(self, src, out, index: int) -> dict:
        return self._tools().delete_bookmark(src, out, index)

    def update_bookmark(self, src, out, index: int,
                        title: str | None = None,
                        page: int | None = None) -> dict:
        return self._tools().update_bookmark(
            src, out, index, title=title, page=page
        )

    def stamp_image(self, src, out, image_path, page: int = 1,
                    x: float = 0.6, y: float = 0.65,
                    width_ratio: float = 0.25,
                    opacity: float = 1.0) -> dict:
        return self._tools().stamp_image(
            src, out, image_path, page,
            x=x, y=y, width_ratio=width_ratio, opacity=opacity,
        )


class PypdfBackend(PdfBackend):
    """阶段 2 目标后端（骨架）。

    依赖：pypdfium2（渲染/文本）、pypdf（结构/加密/书签）、reportlab（水印/签名）。
    迁移期间按 docs/PDF后端迁移映射-2026-11-03.md 逐项替换。
    """

    name = "pypdf"

    def _todo(self, method: str):
        raise NotImplementedError(
            f"PypdfBackend.{method} 尚未迁移；"
            "见 docs/PDF后端迁移映射-2026-11-03.md"
        )

    def page_count(self, src) -> int:
        from pypdf import PdfReader
        return len(PdfReader(str(src)).pages)

    def render_page_png(self, src, page: int, out, scale: float = 2.0) -> dict:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(str(src))
        try:
            index = max(0, min(int(page) - 1, len(pdf) - 1))
            bitmap = pdf[index].render(scale=scale)
            image = bitmap.to_pil()
            out = Path(out)
            out.parent.mkdir(parents=True, exist_ok=True)
            image.save(str(out))
            return {"out": str(out), "page": index + 1,
                    "width": image.width, "height": image.height}
        finally:
            pdf.close()

    def merge_pdfs(self, srcs, out) -> dict:
        from pypdf import PdfWriter
        writer = PdfWriter()
        for src in srcs:
            writer.append(str(src))
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "wb") as f:
            writer.write(f)
        return {"out": str(out), "pages": len(writer.pages)}

    def split_pdf(self, src, outdir, ranges=None) -> dict:
        self._todo("split_pdf")

    def extract_pages(self, src, out, pages=None) -> dict:
        self._todo("extract_pages")

    def delete_pages(self, src, out, pages) -> dict:
        self._todo("delete_pages")

    def crop_pages(self, src, out, top_mm=0, bottom_mm=0,
                   left_mm=0, right_mm=0) -> dict:
        self._todo("crop_pages")

    def insert_pages(self, src, insert_src, out, at: int = 1) -> dict:
        self._todo("insert_pages")

    def replace_pages(self, src, replace_src, out, pages) -> dict:
        self._todo("replace_pages")

    def compress_pdf(self, src, out) -> dict:
        self._todo("compress_pdf")

    def encrypt_pdf(self, src, out, user_password: str,
                    allow_print: bool = True, allow_copy: bool = True) -> dict:
        self._todo("encrypt_pdf")

    def add_watermark(self, src, out, text: str,
                      opacity: float = 0.15, pages=None) -> dict:
        self._todo("add_watermark")

    def extract_text(self, src, out, pages=None) -> dict:
        self._todo("extract_text")

    def extract_images(self, src, outdir, pages=None) -> dict:
        self._todo("extract_images")

    def list_bookmarks(self, src) -> list[dict]:
        self._todo("list_bookmarks")

    def add_bookmark(self, src, out, title: str, page: int = 1) -> dict:
        self._todo("add_bookmark")

    def delete_bookmark(self, src, out, index: int) -> dict:
        self._todo("delete_bookmark")

    def update_bookmark(self, src, out, index: int,
                        title: str | None = None,
                        page: int | None = None) -> dict:
        self._todo("update_bookmark")

    def stamp_image(self, src, out, image_path, page: int = 1,
                    x: float = 0.6, y: float = 0.65,
                    width_ratio: float = 0.25,
                    opacity: float = 1.0) -> dict:
        self._todo("stamp_image")


_BACKENDS = {"fitz": FitzBackend, "pypdf": PypdfBackend}


def get_backend(name: str | None = None) -> PdfBackend:
    """按名称/环境变量获取后端；默认 fitz（迁移完成前）。"""
    name = (name or os.environ.get("BEEOFFICE_PDF_BACKEND") or "fitz").lower()
    if name not in _BACKENDS:
        raise PdfBackendError(f"未知 PDF 后端: {name}")
    return _BACKENDS[name]()


def backend_names() -> list[str]:
    return sorted(_BACKENDS)
