# -*- coding: utf-8 -*-
"""
PDF 页面操作（阶段四 P0-1）

对标 WPS 会员的"PDF 合并 / 拆分 / 页面管理"，但只做**本地、无损**的页面级操作：
    · 合并多个 PDF
    · 提取指定页
    · 删除指定页
    · 旋转页面
    · 拆分（每页一个文件 / 每 N 页一个文件 / 按范围拆）

刻意不做 PDF → Word/Excel 转换：版式还原是另一类问题，硬做只会产出
"看起来成功、打开后乱版"的文件。

设计约束：
    · 纯逻辑，不 import Qt —— 便于单测，也便于将来做命令行批处理
    · 页号对外一律 1 起始（用户视角），内部转 0 起始
    · 加密 PDF 直接报错，不做静默失败
    · 输出路径已存在时覆盖（由调用方的文件对话框负责确认）
"""
import re
from pathlib import Path

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover - 缺依赖时由调用方提示安装
    fitz = None


class PdfPageError(Exception):
    """页面操作的业务错误（用户可读）。"""


def _require_fitz():
    if fitz is None:
        raise PdfPageError("未安装 PyMuPDF，无法处理 PDF")


def open_pdf(path):
    """打开 PDF 并做加密检查。"""
    _require_fitz()
    p = Path(path)
    if not p.exists():
        raise PdfPageError(f"文件不存在：{p}")
    try:
        doc = fitz.open(str(p))
    except Exception as e:
        raise PdfPageError(f"无法打开 PDF：{e}") from e
    if doc.needs_pass:
        doc.close()
        raise PdfPageError("该 PDF 已加密，请先解除密码保护")
    if doc.page_count == 0:
        doc.close()
        raise PdfPageError("该 PDF 没有页面")
    return doc


def page_count(path) -> int:
    doc = open_pdf(path)
    try:
        return doc.page_count
    finally:
        doc.close()


def parse_page_ranges(text: str, total: int) -> list:
    """
    把 "1-3,5,8-" 解析成 1 起始的页号列表（去重、保持输入顺序）。

    · 支持 "3"、"1-3"、"3-"（到末尾）
    · 忽略空格与中文逗号
    · 越界或格式错误抛 PdfPageError，并指出是哪一段
    """
    if total <= 0:
        raise PdfPageError("该 PDF 没有页面")
    raw = (text or "").replace("，", ",").strip()
    if not raw:
        raise PdfPageError("请输入页码范围，例如 1-3,5")

    pages = []
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        m = re.fullmatch(r"(\d+)\s*-\s*(\d*)", token)
        if m:
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else total
            if start <= 0:
                raise PdfPageError(f"页号从 1 开始：{token}")
            if end > total:
                raise PdfPageError(f"超出范围：{token}（共 {total} 页）")
            if start > end:
                raise PdfPageError(f"范围颠倒：{token}")
            pages.extend(range(start, end + 1))
            continue
        if token.isdigit():
            n = int(token)
            if n <= 0 or n > total:
                raise PdfPageError(f"超出范围：{token}（共 {total} 页）")
            pages.append(n)
            continue
        raise PdfPageError(f"无法识别：{token}")

    if not pages:
        raise PdfPageError("没有解析出任何页码")
    # 去重但保持顺序
    seen = set()
    ordered = []
    for n in pages:
        if n not in seen:
            seen.add(n)
            ordered.append(n)
    return ordered


def _new_doc():
    _require_fitz()
    return fitz.open()


def merge_pdfs(paths, output) -> int:
    """把多个 PDF 按给定顺序合并，返回总页数。"""
    paths = [Path(p) for p in paths]
    if not paths:
        raise PdfPageError("请至少选择一个 PDF")
    out = _new_doc()
    try:
        for p in paths:
            doc = open_pdf(p)
            try:
                out.insert_pdf(doc)
            finally:
                doc.close()
        total = out.page_count
        out.save(str(output))
        return total
    finally:
        out.close()


def extract_pages(src, ranges_text, output) -> int:
    """把指定页提取成新文件，返回新文件页数。"""
    doc = open_pdf(src)
    try:
        pages = parse_page_ranges(ranges_text, doc.page_count)
        out = _new_doc()
        try:
            for n in pages:
                out.insert_pdf(doc, from_page=n - 1, to_page=n - 1)
            # 提取时保留原始页面尺寸与旋转
            out.save(str(output), garbage=3, deflate=True)
            return out.page_count
        finally:
            out.close()
    finally:
        doc.close()


def delete_pages(src, ranges_text, output) -> int:
    """删除指定页，返回剩余页数。"""
    doc = open_pdf(src)
    try:
        pages = parse_page_ranges(ranges_text, doc.page_count)
        if len(pages) >= doc.page_count:
            raise PdfPageError("不能删除全部页面，请保留至少一页")
        # 从后往前删，避免索引漂移
        for n in sorted(pages, reverse=True):
            doc.delete_page(n - 1)
        remaining = doc.page_count
        doc.save(str(output), garbage=3, deflate=True)
        return remaining
    finally:
        doc.close()


def rotate_pages(src, ranges_text, degrees, output) -> int:
    """旋转指定页（90/180/270），返回处理页数。"""
    if degrees % 90 != 0:
        raise PdfPageError("旋转角度必须是 90 的倍数")
    doc = open_pdf(src)
    try:
        pages = parse_page_ranges(ranges_text, doc.page_count)
        for n in pages:
            page = doc[n - 1]
            page.set_rotation((page.rotation + degrees) % 360)
        doc.save(str(output), garbage=3, deflate=True)
        return len(pages)
    finally:
        doc.close()


def _out_path(out_dir, prefix, index, total):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{prefix}_{index:03d}.pdf"


def split_pages(src, out_dir, prefix="page") -> list:
    """每页拆成一个文件，返回输出路径列表。"""
    doc = open_pdf(src)
    try:
        results = []
        for i in range(doc.page_count):
            out = _new_doc()
            try:
                out.insert_pdf(doc, from_page=i, to_page=i)
                path = _out_path(out_dir, prefix, i + 1, doc.page_count)
                out.save(str(path), garbage=3, deflate=True)
                results.append(str(path))
            finally:
                out.close()
        return results
    finally:
        doc.close()


def split_every(src, chunk_size, out_dir, prefix="part") -> list:
    """每 N 页拆成一个文件，返回输出路径列表。"""
    if chunk_size <= 0:
        raise PdfPageError("每份页数必须大于 0")
    doc = open_pdf(src)
    try:
        results = []
        total = doc.page_count
        index = 1
        start = 0
        while start < total:
            end = min(start + chunk_size - 1, total - 1)
            out = _new_doc()
            try:
                out.insert_pdf(doc, from_page=start, to_page=end)
                path = _out_path(out_dir, prefix, index, total)
                out.save(str(path), garbage=3, deflate=True)
                results.append(str(path))
            finally:
                out.close()
            index += 1
            start = end + 1
        return results
    finally:
        doc.close()


def split_ranges(src, ranges_list, out_dir, prefix="part") -> list:
    """
    按多段范围拆分，每段一个文件。

    :param ranges_list: 形如 ["1-3", "5", "8-"] 的字符串列表
    """
    doc = open_pdf(src)
    try:
        results = []
        for i, ranges_text in enumerate(ranges_list, 1):
            pages = parse_page_ranges(ranges_text, doc.page_count)
            out = _new_doc()
            try:
                for n in pages:
                    out.insert_pdf(doc, from_page=n - 1, to_page=n - 1)
                path = _out_path(out_dir, prefix, i, doc.page_count)
                out.save(str(path), garbage=3, deflate=True)
                results.append(str(path))
            finally:
                out.close()
        return results
    finally:
        doc.close()
