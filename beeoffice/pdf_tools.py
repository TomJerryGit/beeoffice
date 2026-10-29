# beeoffice/pdf_tools.py
"""
PDF 页面与权限工具（PyMuPDF，零 Qt）—— beecmd v0.5 / v5.0.18。

## 为什么做这一块
WPS 会员的付费墙里，PDF 的「页面管理 + 加密权限 + 水印 + 提取」是**唯一**
能用现有依赖低成本追平的一大类（PyMuPDF 早已是 BeeOffice 的必需依赖，
requirements.txt 用它做 PDF 批注渲染）。不做 PDF **转换 / OCR / 版面编辑**——
那些是云服务+模型能力，投入产出比不成立。

## 设计约束
- 所有函数**不修改源文件**：输出必须显式给路径（`merge/split/extract` 均生成新文件）；
- 页码统一 **1 基**，支持 `1-3,5,7-`（逗号分隔、`a-b` 区间、`a-` 到末页）；
- 加密只支持**写**（打开密码/权限），不做破解、不做签名验签；
- 错误统一 `PdfToolError`，由 beecmd 转成友好提示 + 非 0 退出码。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

try:
    import fitz  # PyMuPDF
except ImportError as _e:  # pragma: no cover - 发布包必然带 PyMuPDF
    fitz = None
    _FITZ_IMPORT_ERROR = _e


class PdfToolError(Exception):
    """PDF 工具的可预期失败（坏文件/页码越界/缺少依赖等）。"""


#: 允许给用户看的权限（fitz 的权限位）
PERM_PRINT = fitz.PDF_PERM_PRINT if fitz is not None else 0
PERM_COPY = fitz.PDF_PERM_COPY if fitz is not None else 0


def _require_fitz():
    if fitz is None:  # pragma: no cover
        raise PdfToolError(
            "PDF 功能需要 PyMuPDF：pip install PyMuPDF"
        )


def _open_doc(path) -> "fitz.Document":
    _require_fitz()
    path = Path(path)
    if not path.is_file():
        raise PdfToolError(f"PDF 文件不存在：{path}")
    try:
        doc = fitz.open(str(path))
    except Exception as e:  # noqa: BLE001
        raise PdfToolError(f"无法打开 PDF（可能已损坏/加密）：{path}（{e}）")
    if doc.needs_pass:
        doc.close()
        raise PdfToolError("PDF 已加密，需要先解密后再处理")
    if doc.page_count <= 0:
        doc.close()
        raise PdfToolError(f"PDF 没有页面：{path}")
    return doc


def _save(doc: "fitz.Document", out: Path):
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        doc.save(str(out), garbage=3, deflate=True)
    except Exception as e:  # noqa: BLE001
        raise PdfToolError(f"写入失败：{out}（{e}）")


def parse_page_spec(spec: Optional[str], total: int) -> List[int]:
    """
    解析 1 基页码表达式为 0 基索引列表（保持顺序、去重）。

    支持：``1`` / ``1-3`` / ``3-``（到末页） / ``-3``（1..3） / ``1,3-5,7-``。
    空串或 ``all`` = 全部页面。
    """
    total = int(total)
    if total <= 0:
        raise PdfToolError("PDF 没有页面")
    text = (spec or "").strip().lower()
    if not text or text == "all":
        return list(range(total))

    result: List[int] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        match = re.fullmatch(r"(\d*)\s*-\s*(\d*)", part)
        if match:
            start_s, end_s = match.group(1), match.group(2)
            if not start_s and not end_s:
                raise PdfToolError(f"非法页码：{part!r}")
            start = int(start_s) if start_s else 1
            end = int(end_s) if end_s else total
        elif part.isdigit():
            start = end = int(part)
        else:
            raise PdfToolError(f"非法页码：{part!r}（示例：1-3,5,7-）")
        if start < 1 or end < 1 or start > total or end > total:
            raise PdfToolError(
                f"页码越界：{part!r}（总页数 {total}，页码从 1 开始）"
            )
        if start > end:
            start, end = end, start
        for page in range(start, end + 1):
            if (page - 1) not in result:
                result.append(page - 1)
    if not result:
        raise PdfToolError("页码表达式没有选中任何页面")
    return result


def _result_dict(srcs: Sequence[Path], out: Path, **extra):
    data = {"sources": [str(p) for p in srcs], "output": str(out)}
    data.update(extra)
    return data


def merge_pdfs(srcs: Iterable, out) -> dict:
    """把多个 PDF 按顺序合并成一个新 PDF（不修改源文件）。"""
    _require_fitz()
    paths = [Path(s) for s in srcs]
    if len(paths) < 1:
        raise PdfToolError("至少需要 1 个 PDF")
    out = Path(out)
    result_doc = fitz.open()
    page_counts = []
    try:
        for path in paths:
            src = _open_doc(path)
            try:
                page_counts.append(src.page_count)
                result_doc.insert_pdf(src)
            finally:
                src.close()
        _save(result_doc, out)
    finally:
        result_doc.close()
    return _result_dict(paths, out, pages=sum(page_counts),
                        page_counts=page_counts)


def _copy_pages(src_path: Path, out: Path, indexes: Sequence[int],
                label: str) -> dict:
    src = _open_doc(src_path)
    out = Path(out)
    result = fitz.open()
    try:
        for index in indexes:
            result.insert_pdf(src, from_page=index, to_page=index)
        _save(result, out)
    finally:
        src.close()
        result.close()
    return _result_dict([src_path], out, pages=len(indexes),
                        page_indexes=[i + 1 for i in indexes], label=label)


def extract_pages(src, out, pages: Optional[str] = None) -> dict:
    """把指定页提取成一个新 PDF。"""
    src_path = Path(src)
    src = _open_doc(src_path)
    try:
        indexes = parse_page_spec(pages, src.page_count)
    finally:
        src.close()
    return _copy_pages(src_path, out, indexes, "extract")


def delete_pages(src, out, pages: str) -> dict:
    """删除指定页，其余页生成新 PDF（不修改源文件）。"""
    src_path = Path(src)
    src = _open_doc(src_path)
    try:
        remove = set(parse_page_spec(pages, src.page_count))
        keep = [i for i in range(src.page_count) if i not in remove]
    finally:
        src.close()
    if not keep:
        raise PdfToolError("不能删除全部页面（结果会为空）")
    return _copy_pages(src_path, out, keep, "delete")


def split_pdf(src, outdir, ranges: Optional[str] = None) -> dict:
    """
    拆分 PDF：默认每页一个文件；`ranges` 给定则每个区间一个文件。

    `ranges` 用 `;` 分隔多个输出区间，如 ``1-3;4-6;7-``。
    """
    src_path = Path(src)
    src = _open_doc(src_path)
    try:
        total = src.page_count
    finally:
        src.close()
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    outputs = []
    if ranges:
        specs = [s for s in ranges.split(";") if s.strip()]
        if not specs:
            raise PdfToolError("ranges 为空")
        for spec in specs:
            indexes = parse_page_spec(spec, total)
            name = f"{src_path.stem}_p{indexes[0] + 1}-{indexes[-1] + 1}.pdf"
            outputs.append(_copy_pages(src_path, outdir / name, indexes,
                                       "split")["output"])
    else:
        for index in range(total):
            name = f"{src_path.stem}_p{index + 1}.pdf"
            outputs.append(_copy_pages(src_path, outdir / name, [index],
                                       "split")["output"])
    return {"source": str(src_path), "output_dir": str(outdir),
            "pages": total, "outputs": outputs}


def encrypt_pdf(src, out, user_password: str,
                owner_password: Optional[str] = None,
                allow_print: bool = True,
                allow_copy: bool = True) -> dict:
    """给 PDF 加打开密码/权限（AES-256）；不修改源文件。"""
    _require_fitz()
    if not user_password:
        raise PdfToolError("必须提供 --user-password（打开密码）")
    src_path = Path(src)
    doc = _open_doc(src_path)
    out = Path(out)
    perms = fitz.PDF_PERM_ACCESSIBILITY
    if allow_print:
        perms |= fitz.PDF_PERM_PRINT | fitz.PDF_PERM_PRINT_HQ
    if allow_copy:
        perms |= fitz.PDF_PERM_COPY
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        doc.save(
            str(out),
            encryption=fitz.PDF_ENCRYPT_AES_256,
            owner_pw=owner_password or user_password,
            user_pw=user_password,
            permissions=perms,
            garbage=3,
            deflate=True,
        )
    except Exception as e:  # noqa: BLE001
        raise PdfToolError(f"加密保存失败：{out}（{e}）")
    finally:
        doc.close()
    return _result_dict(
        [src_path], out, encrypted=True,
        allow_print=allow_print, allow_copy=allow_copy,
    )


def add_watermark(src, out, text: str, opacity: float = 0.15,
                  fontsize: float = 48.0,
                  pages: Optional[str] = None) -> dict:
    """给每页叠加文字水印（半透明、居中；不修改源文件）。"""
    _require_fitz()
    if not (text or "").strip():
        raise PdfToolError("水印文字不能为空")
    opacity = max(0.0, min(1.0, float(opacity)))
    fontsize = float(fontsize)
    if fontsize <= 0:
        raise PdfToolError("fontsize 必须 > 0")
    src_path = Path(src)
    doc = _open_doc(src_path)
    out = Path(out)
    try:
        indexes = parse_page_spec(pages, doc.page_count)
        for index in indexes:
            page = doc[index]
            rect = page.rect
            box = fitz.Rect(
                rect.x0 + rect.width * 0.08,
                rect.y0 + rect.height * 0.40,
                rect.x1 - rect.width * 0.08,
                rect.y1 - rect.height * 0.40,
            )
            # 中文水印必须用 PyMuPDF 内置 CJK 字体，否则 helv 会渲染成 ????
            fontname = "china-s" if any(ord(ch) > 127 for ch in text) else "helv"
            page.insert_textbox(
                box, text,
                fontsize=fontsize, align=1,
                fontname=fontname,
                color=(0.45, 0.45, 0.45),
                fill_opacity=opacity,
                overlay=True,
            )
        _save(doc, out)
    finally:
        doc.close()
    return _result_dict([src_path], out, watermarked_pages=len(indexes),
                        opacity=opacity)


def extract_text(src, out, pages: Optional[str] = None) -> dict:
    """提取文本到 UTF-8 .txt（按页分隔）。"""
    src_path = Path(src)
    doc = _open_doc(src_path)
    out = Path(out)
    try:
        indexes = parse_page_spec(pages, doc.page_count)
        chunks = []
        for index in indexes:
            chunks.append(f"===== 第 {index + 1} 页 =====\n"
                          f"{doc[index].get_text()}")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(chunks), encoding="utf-8")
    finally:
        doc.close()
    return _result_dict([src_path], out, pages=len(indexes))


def extract_images(src, outdir, pages: Optional[str] = None) -> dict:
    """把页面里的图片导出到目录（png/jpg 等按原格式）。"""
    _require_fitz()
    src_path = Path(src)
    doc = _open_doc(src_path)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    saved = []
    try:
        indexes = parse_page_spec(pages, doc.page_count)
        for index in indexes:
            for image_number, info in enumerate(doc[index].get_images(full=True)):
                xref = info[0]
                try:
                    image = doc.extract_image(xref)
                except Exception:  # noqa: BLE001
                    continue
                ext = image.get("ext") or "png"
                name = f"{src_path.stem}_p{index + 1}_{image_number + 1}.{ext}"
                target = outdir / name
                target.write_bytes(image["image"])
                saved.append(str(target))
    finally:
        doc.close()
    return {"source": str(src_path), "output_dir": str(outdir),
            "count": len(saved), "images": saved}


# ==================== 书签 / 图片签名（S3） ====================

def list_bookmarks(src) -> list[dict]:
    """读取 PDF 书签（TOC），返回 [{level,title,page}]，page 为 1 基。"""
    src_path = Path(src)
    if not src_path.is_file():
        raise PdfToolError(f"文件不存在: {src_path}")
    doc = fitz.open(str(src_path))
    try:
        return [
            {"level": int(level), "title": str(title), "page": int(page)}
            for level, title, page in (doc.get_toc() or [])
        ]
    finally:
        doc.close()


def add_bookmark(src, out, title: str, page: int = 1) -> dict:
    """在末尾追加一个一级书签；不修改源文件。"""
    src_path, out_path = Path(src), Path(out)
    if not src_path.is_file():
        raise PdfToolError(f"文件不存在: {src_path}")
    if src_path.resolve() == out_path.resolve():
        raise PdfToolError("输出不能覆盖源文件")
    doc = fitz.open(str(src_path))
    try:
        if not 1 <= int(page) <= doc.page_count:
            raise PdfToolError(f"页码越界: {page}（共 {doc.page_count} 页）")
        toc = doc.get_toc() or []
        toc.append([1, str(title).strip() or "书签", int(page)])
        doc.set_toc(toc)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(out_path))
    finally:
        doc.close()
    return {"source": str(src_path), "output": str(out_path), "title": title, "page": int(page)}


def stamp_image(src, out, image_path, page: int = 1,
                x: float = 0.6, y: float = 0.65,
                width_ratio: float = 0.25, opacity: float = 1.0) -> dict:
    """把图片（手写签名/图章）叠加到指定页；坐标为相对页面宽高的左上角。"""
    src_path, out_path, img_path = Path(src), Path(out), Path(image_path)
    if not src_path.is_file():
        raise PdfToolError(f"文件不存在: {src_path}")
    if not img_path.is_file():
        raise PdfToolError(f"签名图片不存在: {img_path}")
    if src_path.resolve() == out_path.resolve():
        raise PdfToolError("输出不能覆盖源文件")
    doc = fitz.open(str(src_path))
    try:
        if not 1 <= int(page) <= doc.page_count:
            raise PdfToolError(f"页码越界: {page}（共 {doc.page_count} 页）")
        pdf_page = doc[int(page) - 1]
        rect = pdf_page.rect
        w = max(0.02, min(1.0, float(width_ratio))) * rect.width
        # 按图片宽高比计算高度
        try:
            from PIL import Image
            with Image.open(img_path) as im:
                aspect = im.height / max(1, im.width)
        except Exception:  # noqa: BLE001
            aspect = 0.4
        h = w * aspect
        left = max(0.0, min(1.0, float(x))) * rect.width
        top = max(0.0, min(1.0, float(y))) * rect.height
        clip = fitz.Rect(left, top, min(rect.width, left + w),
                         min(rect.height, top + h))
        pdf_page.insert_image(
            clip, filename=str(img_path), overlay=True,
            rotate=0, keep_proportion=True,
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(out_path))
    finally:
        doc.close()
    return {"source": str(src_path), "output": str(out_path),
            "image": str(img_path), "page": int(page)}
