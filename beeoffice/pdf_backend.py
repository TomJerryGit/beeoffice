# beeoffice/pdf_backend.py
"""PDF 后端适配层：上层只依赖 PdfBackend，不直接 import fitz。

- 当前后端：PypdfBackend（pypdfium2 + pypdf + reportlab）；
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
    def read_text_pages(self, src) -> list[str]: ...

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

    @abstractmethod
    def burn_annotations(self, src, out, annotations: list[dict]) -> dict: ...


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

    def _rebuild_with_outline(self, reader, entries, out):
        from pypdf import PdfWriter
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        try:
            if reader.metadata:
                writer.add_metadata(reader.metadata)
        except Exception:  # noqa: BLE001
            pass
        parents = {0: None}
        for level, title, page in entries:
            parent = parents.get(level - 1)
            node = writer.add_outline_item(title, max(0, page - 1),
                                           parent=parent)
            parents[level] = node
            for key in [k for k in parents if k > level]:
                parents.pop(key, None)
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "wb") as f:
            writer.write(f)
        return len(entries)

    def _flatten_outline(self, reader):
        result = []

        def walk(items, level):
            for item in items:
                if isinstance(item, list):
                    walk(item, level + 1)
                else:
                    try:
                        page = reader.get_destination_page_number(item) + 1
                    except Exception:  # noqa: BLE001
                        page = 1
                    result.append([level, str(item.title), int(page)])

        walk(reader.outline or [], 1)
        return result

    def encrypt_pdf(self, src, out, user_password: str,
                    owner_password: str | None = None,
                    allow_print: bool = True,
                    allow_copy: bool = True) -> dict:
        from pypdf import PdfWriter
        from pypdf.constants import UserAccessPermissions as U
        if not user_password:
            raise PdfToolError("必须提供打开密码")
        reader = self._reader(src)
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        perms = U.PRINT_TO_REPRESENTATION
        if allow_print:
            perms |= U.PRINT
        if allow_copy:
            perms |= U.EXTRACT | U.EXTRACT_TEXT_AND_GRAPHICS
        try:
            writer.encrypt(user_password=user_password,
                           owner_password=owner_password or user_password,
                           permissions_flag=perms)
        except TypeError:
            writer.encrypt(user_password, owner_password or user_password,
                           permissions_flag=perms)
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "wb") as f:
            writer.write(f)
        return self._result([Path(src)], out, encrypted=True,
                            allow_print=allow_print,
                            allow_copy=allow_copy)

    def _overlay_pdf(self, page, draw):
        import io
        from reportlab.pdfgen import canvas
        box = page.mediabox
        w, h = float(box.width), float(box.height)
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(w, h))
        draw(c, w, h)
        c.save()
        buf.seek(0)
        from pypdf import PdfReader
        return PdfReader(buf).pages[0]

    @staticmethod
    def _cjk_font() -> str:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from pathlib import Path
        for path in (r"C:\Windows\Fonts\msyh.ttc",
                     r"C:\Windows\Fonts\simsun.ttc",
                     r"C:\Windows\Fonts\simhei.ttf"):
            if Path(path).is_file():
                try:
                    pdfmetrics.registerFont(TTFont("BeeCJK", path))
                    return "BeeCJK"
                except Exception:  # noqa: BLE001
                    continue
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        return "STSong-Light"

    def add_watermark(self, src, out, text: str, opacity: float = 0.15,
                      fontsize: float = 48.0, pages=None) -> dict:
        from pypdf import PdfWriter
        if not (text or "").strip():
            raise PdfToolError("水印文字不能为空")
        opacity = max(0.0, min(1.0, float(opacity)))
        reader = self._reader(src)
        indexes = set(parse_page_spec(pages, len(reader.pages)))
        font = self._cjk_font()
        writer = PdfWriter()
        for i, page in enumerate(reader.pages):
            if i in indexes:
                def draw(c, w, h):
                    c.saveState()
                    c.setFillAlpha(opacity)
                    c.setFillColorRGB(0.45, 0.45, 0.45)
                    c.setFont(font, float(fontsize))
                    c.translate(w / 2, h / 2)
                    c.rotate(45)
                    c.drawCentredString(0, 0, text)
                    c.restoreState()

                page.merge_page(self._overlay_pdf(page, draw))
            writer.add_page(page)
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "wb") as f:
            writer.write(f)
        return self._result([Path(src)], out,
                            watermarked_pages=len(indexes),
                            opacity=opacity)

    def list_bookmarks(self, src) -> list[dict]:
        reader = self._reader(src)
        return [{"level": level, "title": title, "page": page}
                for level, title, page in self._flatten_outline(reader)]

    def add_bookmark(self, src, out, title: str, page: int = 1) -> dict:
        reader = self._reader(src)
        total = len(reader.pages)
        if not 1 <= int(page) <= total:
            raise PdfToolError(f"页码越界: {page}（共 {total} 页）")
        entries = self._flatten_outline(reader)
        entries.append([1, str(title).strip() or "书签", int(page)])
        self._rebuild_with_outline(reader, entries, out)
        return {"source": str(src), "output": str(out),
                "title": title, "page": int(page)}

    def delete_bookmark(self, src, out, index: int) -> dict:
        reader = self._reader(src)
        entries = self._flatten_outline(reader)
        if not 0 <= int(index) < len(entries):
            raise PdfToolError(f"书签序号越界: {index}（共 {len(entries)} 条）")
        removed = entries.pop(int(index))
        self._rebuild_with_outline(reader, entries, out)
        return {"source": str(src), "output": str(out),
                "removed": {"title": removed[1], "page": removed[2]}}

    def update_bookmark(self, src, out, index: int,
                        title: str | None = None,
                        page: int | None = None) -> dict:
        reader = self._reader(src)
        entries = self._flatten_outline(reader)
        if not 0 <= int(index) < len(entries):
            raise PdfToolError(f"书签序号越界: {index}（共 {len(entries)} 条）")
        entry = entries[int(index)]
        if title is not None:
            entry[1] = str(title).strip() or entry[1]
        if page is not None:
            if not 1 <= int(page) <= len(reader.pages):
                raise PdfToolError(f"页码越界: {page}（共 {len(reader.pages)} 页）")
            entry[2] = int(page)
        self._rebuild_with_outline(reader, entries, out)
        return {"source": str(src), "output": str(out),
                "title": entry[1], "page": entry[2]}

    def stamp_image(self, src, out, image_path, page: int = 1,
                    x: float = 0.6, y: float = 0.65,
                    width_ratio: float = 0.25,
                    opacity: float = 1.0) -> dict:
        from pypdf import PdfWriter
        img_path = Path(image_path)
        if not img_path.is_file():
            raise PdfToolError(f"签名图片不存在: {img_path}")
        reader = self._reader(src)
        if not 1 <= int(page) <= len(reader.pages):
            raise PdfToolError(f"页码越界: {page}（共 {len(reader.pages)} 页）")
        target = reader.pages[int(page) - 1]

        def draw(c, w, h):
            from PIL import Image
            with Image.open(img_path) as im:
                aspect = im.height / max(1, im.width)
            iw = max(0.02, min(1.0, float(width_ratio))) * w
            ih = iw * aspect
            left = max(0.0, min(1.0, float(x))) * w
            top = max(0.0, min(1.0, float(y))) * h
            c.drawImage(str(img_path), left, h - top - ih,
                        width=iw, height=ih, mask="auto")

        target.merge_page(self._overlay_pdf(target, draw))
        writer = PdfWriter()
        for p in reader.pages:
            writer.add_page(p)
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "wb") as f:
            writer.write(f)
        return {"source": str(src), "output": str(out),
                "image": str(img_path), "page": int(page)}

    def read_text_pages(self, src) -> list[str]:
        reader = self._reader(src)
        return [(page.extract_text() or "") for page in reader.pages]

    def extract_text(self, src, out, pages=None) -> dict:
        reader = self._reader(src)
        indexes = parse_page_spec(pages, len(reader.pages))
        chunks = []
        for i in indexes:
            text = reader.pages[i].extract_text() or ""
            chunks.append(f"===== 第 {i + 1} 页 =====\n{text}")
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(chunks), encoding="utf-8")
        return self._result([Path(src)], out, pages=len(indexes))

    def extract_images(self, src, outdir, pages=None) -> dict:
        reader = self._reader(src)
        indexes = parse_page_spec(pages, len(reader.pages))
        outdir = Path(outdir)
        outdir.mkdir(parents=True, exist_ok=True)
        stem = Path(src).stem
        saved = []
        for i in indexes:
            try:
                images = list(reader.pages[i].images)
            except Exception:  # noqa: BLE001
                continue
            for n, image in enumerate(images):
                try:
                    data = image.data
                except Exception:  # noqa: BLE001
                    continue
                suffix = Path(image.name).suffix.lstrip(".") or "png"
                target = outdir / f"{stem}_p{i + 1}_{n + 1}.{suffix}"
                target.write_bytes(data)
                saved.append(str(target))
        return {"source": str(src), "output_dir": str(outdir),
                "count": len(saved), "images": saved}


    def burn_annotations(self, src, out, annotations: list[dict]) -> dict:
        from pypdf import PdfWriter
        reader = self._reader(src)
        by_page = {}
        for data in annotations or []:
            by_page.setdefault(int(data.get("page", 0)), []).append(data)
        writer = PdfWriter()
        for i, page in enumerate(reader.pages):
            items = by_page.get(i)
            if items:
                h = float(page.mediabox.height)

                def draw(c, w, hh):
                    for data in items:
                        rect = data.get("rect") or [0, 0, 0, 0]
                        x0, y0, x1, y1 = [float(v) for v in rect]
                        color = data.get("color") or [1, 0.8, 0]
                        c.setFillColorRGB(*[float(v) for v in color])
                        c.setStrokeColorRGB(*[float(v) for v in color])
                        kind = data.get("type", "highlight")
                        if kind == "highlight":
                            c.setFillAlpha(0.3)
                            c.rect(x0, hh - y1, max(0, x1 - x0),
                                   max(0, y1 - y0), fill=1, stroke=0)
                        elif kind == "underline":
                            c.setLineWidth(1.5)
                            c.line(x0, hh - y1, x1, hh - y1)
                        elif kind == "strikethrough":
                            c.setLineWidth(1.5)
                            c.line(x0, hh - (y0 + y1) / 2, x1,
                                   hh - (y0 + y1) / 2)
                        elif kind == "text":
                            c.setFont(self._cjk_font(), 9)
                            c.drawString(x0, hh - y0, data.get("text", ""))
                        elif kind == "textbox":
                            c.setLineWidth(1)
                            c.rect(x0, hh - y1, max(0, x1 - x0),
                                   max(0, y1 - y0), fill=0, stroke=1)
                            c.setFont(self._cjk_font(), 9)
                            c.drawString(x0 + 2, hh - y0 - 11,
                                         data.get("text", ""))
                        elif kind == "signature":
                            c.setFont(self._cjk_font(), 14)
                            c.drawString(x0, hh - y0, data.get("text", ""))
                        elif kind == "rectangle":
                            c.setLineWidth(2)
                            c.rect(x0, hh - y1, max(0, x1 - x0),
                                   max(0, y1 - y0), fill=0, stroke=1)
                        elif kind == "circle":
                            c.setLineWidth(2)
                            c.ellipse(x0, hh - y1, x1, hh - y0,
                                      fill=0, stroke=1)
                        elif kind == "line":
                            c.setLineWidth(2)
                            c.line(x0, hh - y0, x1, hh - y1)
                        elif kind == "arrow":
                            import math
                            c.setLineWidth(2)
                            c.line(x0, hh - y0, x1, hh - y1)
                            dx, dy = x1 - x0, (hh - y1) - (hh - y0)
                            ln = math.hypot(dx, dy) or 1
                            ux, uy = dx / ln, dy / ln
                            size = 8
                            c.line(x1, hh - y1,
                                   x1 - size * ux + size * 0.5 * uy,
                                   (hh - y1) - size * uy - size * 0.5 * ux)
                            c.line(x1, hh - y1,
                                   x1 - size * ux - size * 0.5 * uy,
                                   (hh - y1) - size * uy + size * 0.5 * ux)

                page.merge_page(self._overlay_pdf(page, draw))
            writer.add_page(page)
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "wb") as f:
            writer.write(f)
        return {"source": str(src), "output": str(out),
                "annotations": len(annotations or [])}


_BACKENDS = {"pypdf": PypdfBackend}


def get_backend(name: str | None = None) -> PdfBackend:
    name = (name or os.environ.get("BEEOFFICE_PDF_BACKEND") or "pypdf").lower()
    if name not in _BACKENDS:
        raise PdfBackendError(f"未知 PDF 后端: {name}")
    return _BACKENDS[name]()


def backend_names() -> list[str]:
    return sorted(_BACKENDS)
