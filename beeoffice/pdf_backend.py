# beeoffice/pdf_backend.py
"""PDF 后端适配层：上层只依赖 PdfBackend，不直接 import fitz。

- 阶段 1：FitzBackend（兼容现有行为）；
- 阶段 2：PypdfBackend（pypdfium2 + pypdf + reportlab）；
- 迁移映射见 docs/PDF后端迁移映射-2026-11-03.md。
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path

from beeoffice.pdf_common import PdfToolError, parse_page_spec


class PdfBackendError(RuntimeError):
    pass


class PdfBackend(ABC):
    """PDF 能力抽象；签名与 pdf_tools 对齐。"""

    name = "base"

    @abstractmethod
    def page_count(self, src) -> int: ...

    @abstractmethod
    def render_page_png(self, src, page: int, out, scale: float = 2.0) -> dict: ...

    @abstractmethod
    def merge_pdfs(self, srcs, out) -> dict: ...

    @abstractmethod
    def split_pdf(self, src, outdir, ranges=None) -> dict: ...

    @abstractmethod
    def extract_pages(self, src, out, pages=None) -> dict: ...

    @abstractmethod
    def delete_pages(self, src, out, pages) -> dict: ...

    @abstractmethod
    def rotate_pages(self, src, out, pages=None, angle: int = 90) -> dict: ...

    @abstractmethod
    def crop_pages(self, src, out, top_mm=0, bottom_mm=0,
                   left_mm=0, right_mm=0) -> dict: ...

    @abstractmethod
    def insert_pages(self, src, insert_src, out, at: int = 1) -> dict: ...

    @abstractmethod
    def replace_pages(self, src, replace_src, out, pages) -> dict: ...

    @abstractmethod
    def compress_pdf(self, src, out) -> dict: ...

    @abstractmethod
    def encrypt_pdf(self, src, out, user_password: str,
                    owner_password: str | None = None,
                    allow_print: bool = True,
                    allow_copy: bool = True) -> dict: ...

    @abstractmethod
    def add_watermark(self, src, out, text: str, opacity: float = 0.15,
                      fontsize: float = 48.0, pages=None) -> dict: ...

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
    """阶段 1 兼容后端：文档能力委托 pdf_tools_fitz，页面/渲染由 fitz 完成。"""

    name = "fitz"

    def _tools(self):
        from beeoffice import pdf_tools_fitz
        return pdf_tools_fitz

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
            pix = doc.load_page(index).get_pixmap(
                matrix=fitz.Matrix(scale, scale)
            )
            out = Path(out)
            out.parent.mkdir(parents=True, exist_ok=True)
            pix.save(str(out))
            return {"out": str(out), "page": index + 1,
                    "width": pix.width, "height": pix.height}
        finally:
            doc.close()

    # 页面结构交给兼容实现，保证阶段 1 行为不变
    def merge_pdfs(self, srcs, out) -> dict:
        return self._tools().merge_pdfs(srcs, out)

    def split_pdf(self, src, outdir, ranges=None) -> dict:
        return self._tools().split_pdf(src, outdir, ranges)

    def extract_pages(self, src, out, pages=None) -> dict:
        return self._tools().extract_pages(src, out, pages)

    def delete_pages(self, src, out, pages) -> dict:
        return self._tools().delete_pages(src, out, pages)

    def rotate_pages(self, src, out, pages=None, angle: int = 90) -> dict:
        fitz = self._fitz()
        doc = fitz.open(str(src))
        try:
            indexes = parse_page_spec(pages, len(doc))
            for i in indexes:
                doc[i].set_rotation((doc[i].rotation + int(angle)) % 360)
            out = Path(out)
            out.parent.mkdir(parents=True, exist_ok=True)
            doc.save(str(out), garbage=3, deflate=True)
            return {"source": str(src), "output": str(out),
                    "pages": len(indexes), "angle": int(angle)}
        finally:
            doc.close()

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
                    owner_password: str | None = None,
                    allow_print: bool = True,
                    allow_copy: bool = True) -> dict:
        return self._tools().encrypt_pdf(
            src, out, user_password, owner_password=owner_password,
            allow_print=allow_print, allow_copy=allow_copy,
        )

    def add_watermark(self, src, out, text: str, opacity: float = 0.15,
                      fontsize: float = 48.0, pages=None) -> dict:
        return self._tools().add_watermark(
            src, out, text, opacity=opacity, fontsize=fontsize, pages=pages
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
    """阶段 2 后端：pypdfium2 + pypdf + reportlab。"""

    name = "pypdf"

    # ---------- 基础 ----------
    def page_count(self, src) -> int:
        return len(self._reader(src).pages)

    def render_page_png(self, src, page: int, out, scale: float = 2.0) -> dict:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(str(src))
        try:
            index = max(0, min(int(page) - 1, len(pdf) - 1))
            image = pdf[index].render(scale=scale).to_pil()
            out = Path(out)
            out.parent.mkdir(parents=True, exist_ok=True)
            image.save(str(out))
            return {"out": str(out), "page": index + 1,
                    "width": image.width, "height": image.height}
        finally:
            pdf.close()

    def _reader(self, src):
        from pypdf import PdfReader
        src = Path(src)
        if not src.is_file():
            raise PdfToolError(f"PDF 文件不存在：{src}")
        try:
            reader = PdfReader(str(src))
        except Exception as e:  # noqa: BLE001
            raise PdfToolError(f"无法打开 PDF：{src}（{e}）") from e
        if reader.is_encrypted:
            raise PdfToolError("PDF 已加密，需要先解密后再处理")
        if len(reader.pages) <= 0:
            raise PdfToolError(f"PDF 没有页面：{src}")
        return reader

    def _write_pages(self, pages, out):
        from pypdf import PdfWriter
        writer = PdfWriter()
        for page in pages:
            writer.add_page(page)
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "wb") as f:
            writer.write(f)
        return len(pages)

    def _result(self, srcs, out, **extra):
        data = {"sources": [str(p) for p in srcs], "output": str(out)}
        data.update(extra)
        return data

    # ---------- 页面结构 ----------
    def merge_pdfs(self, srcs, out) -> dict:
        from pypdf import PdfWriter
        paths = [Path(s) for s in srcs]
        if not paths:
            raise PdfToolError("至少需要 1 个 PDF")
        writer = PdfWriter()
        counts = []
        for path in paths:
            reader = self._reader(path)
            counts.append(len(reader.pages))
            for page in reader.pages:
                writer.add_page(page)
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "wb") as f:
            writer.write(f)
        return self._result(paths, out, pages=sum(counts),
                            page_counts=counts)

    def split_pdf(self, src, outdir, ranges=None) -> dict:
        reader = self._reader(src)
        total = len(reader.pages)
        outdir = Path(outdir)
        outdir.mkdir(parents=True, exist_ok=True)
        outputs = []
        stem = Path(src).stem
        specs = ([s for s in ranges.split(";") if s.strip()]
                 if ranges else None)
        groups = ([parse_page_spec(s, total) for s in specs]
                  if specs else [[i] for i in range(total)])
        for indexes in groups:
            name = (f"{stem}_p{indexes[0] + 1}-{indexes[-1] + 1}.pdf"
                    if len(indexes) > 1 else f"{stem}_p{indexes[0] + 1}.pdf")
            target = outdir / name
            self._write_pages([reader.pages[i] for i in indexes], target)
            outputs.append(str(target))
        return {"source": str(src), "output_dir": str(outdir),
                "pages": total, "outputs": outputs}

    def extract_pages(self, src, out, pages=None) -> dict:
        reader = self._reader(src)
        indexes = parse_page_spec(pages, len(reader.pages))
        self._write_pages([reader.pages[i] for i in indexes], out)
        return self._result([Path(src)], out, pages=len(indexes),
                            page_indexes=[i + 1 for i in indexes],
                            label="extract")

    def delete_pages(self, src, out, pages) -> dict:
        reader = self._reader(src)
        remove = set(parse_page_spec(pages, len(reader.pages)))
        keep = [i for i in range(len(reader.pages)) if i not in remove]
        if not keep:
            raise PdfToolError("不能删除全部页面（结果会为空）")
        self._write_pages([reader.pages[i] for i in keep], out)
        return self._result([Path(src)], out, pages=len(keep),
                            page_indexes=[i + 1 for i in keep],
                            label="delete")

    def rotate_pages(self, src, out, pages=None, angle: int = 90) -> dict:
        reader = self._reader(src)
        indexes = set(parse_page_spec(pages, len(reader.pages)))
        out_pages = []
        for i, page in enumerate(reader.pages):
            if i in indexes:
                page.rotate(int(angle))
            out_pages.append(page)
        self._write_pages(out_pages, out)
        return self._result([Path(src)], out, pages=len(indexes),
                            angle=int(angle))

    def crop_pages(self, src, out, top_mm=0, bottom_mm=0,
                   left_mm=0, right_mm=0) -> dict:
        from pypdf.generic import RectangleObject
        reader = self._reader(src)
        if min(top_mm, bottom_mm, left_mm, right_mm) < 0:
            raise PdfToolError("边距不能为负")
        mm = 72.0 / 25.4
        pages = []
        for page in reader.pages:
            box = page.mediabox
            left = float(box.left) + left_mm * mm
            bottom = float(box.bottom) + bottom_mm * mm
            right = float(box.right) - right_mm * mm
            top = float(box.top) - top_mm * mm
            if right - left < 10 or top - bottom < 10:
                raise PdfToolError("裁剪边距过大，页面剩余区域过小")
            page.cropbox = RectangleObject([left, bottom, right, top])
            pages.append(page)
        self._write_pages(pages, out)
        return self._result([Path(src)], out, pages=len(pages),
                            operation="crop")

    def insert_pages(self, src, insert_src, out, at: int = 1) -> dict:
        reader = self._reader(src)
        other = self._reader(insert_src)
        at = max(1, min(int(at), len(reader.pages) + 1))
        order = (list(reader.pages[:at - 1]) + list(other.pages)
                 + list(reader.pages[at - 1:]))
        self._write_pages(order, out)
        return self._result([Path(src), Path(insert_src)], out,
                            pages=len(order), operation="insert", at=at)

    def replace_pages(self, src, replace_src, out, pages: str) -> dict:
        reader = self._reader(src)
        targets = parse_page_spec(pages, len(reader.pages))
        other = self._reader(replace_src)
        target_set = set(targets)
        start = targets[0]
        order = []
        for i, page in enumerate(reader.pages):
            if i == start:
                order.extend(other.pages)
            if i not in target_set:
                order.append(page)
        self._write_pages(order, out)
        return self._result([Path(src), Path(replace_src)], out,
                            pages=len(order), operation="replace",
                            replaced=len(targets))

    def compress_pdf(self, src, out) -> dict:
        from pypdf import PdfWriter
        reader = self._reader(src)
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
            writer.pages[-1].compress_content_streams()
        writer.compress_identical_objects()
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "wb") as f:
            writer.write(f)
        return self._result([Path(src)], out, pages=len(reader.pages),
                            operation="compress",
                            before_bytes=Path(src).stat().st_size,
                            after_bytes=out.stat().st_size)

    # ---------- 文档能力（后续迁移） ----------
    def _todo(self, method: str):
        raise NotImplementedError(
            f"PypdfBackend.{method} 尚未迁移；"
            "见 docs/PDF后端迁移映射-2026-11-03.md"
        )

    def encrypt_pdf(self, src, out, user_password: str,
                    owner_password: str | None = None,
                    allow_print: bool = True,
                    allow_copy: bool = True) -> dict:
        self._todo("encrypt_pdf")

    def add_watermark(self, src, out, text: str, opacity: float = 0.15,
                      fontsize: float = 48.0, pages=None) -> dict:
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
    name = (name or os.environ.get("BEEOFFICE_PDF_BACKEND") or "fitz").lower()
    if name not in _BACKENDS:
        raise PdfBackendError(f"未知 PDF 后端: {name}")
    return _BACKENDS[name]()


def backend_names() -> list[str]:
    return sorted(_BACKENDS)
