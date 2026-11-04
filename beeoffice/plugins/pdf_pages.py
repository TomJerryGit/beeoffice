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

from beeoffice.pdf_backend import get_backend


class PdfPageError(Exception):
    """页面操作的业务错误（用户可读）。"""


def page_count(path) -> int:
    p = Path(path)
    if not p.exists():
        raise PdfPageError(f"文件不存在：{p}")
    try:
        return get_backend().page_count(p)
    except Exception as e:  # noqa: BLE001
        raise PdfPageError(f"无法打开 PDF：{e}") from e


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


def _spec(pages) -> str:
    return ",".join(str(n) for n in pages)


def merge_pdfs(paths, output) -> int:
    paths = [Path(p) for p in paths]
    if not paths:
        raise PdfPageError("请至少选择一个 PDF")
    for p in paths:
        if not p.exists():
            raise PdfPageError(f"文件不存在：{p}")
    try:
        info = get_backend().merge_pdfs(paths, output)
        return int(info.get("pages", 0))
    except Exception as e:  # noqa: BLE001
        raise PdfPageError(f"合并失败：{e}") from e


def extract_pages(src, ranges_text, output) -> int:
    total = page_count(src)
    pages = parse_page_ranges(ranges_text, total)
    try:
        get_backend().extract_pages(src, output, _spec(pages))
        return len(pages)
    except Exception as e:  # noqa: BLE001
        raise PdfPageError(f"提取失败：{e}") from e


def delete_pages(src, ranges_text, output) -> int:
    total = page_count(src)
    pages = parse_page_ranges(ranges_text, total)
    if len(pages) >= total:
        raise PdfPageError("不能删除全部页面，请保留至少一页")
    try:
        get_backend().delete_pages(src, output, _spec(pages))
        return total - len(pages)
    except Exception as e:  # noqa: BLE001
        raise PdfPageError(f"删除失败：{e}") from e


def rotate_pages(src, ranges_text, degrees, output) -> int:
    if degrees % 90 != 0:
        raise PdfPageError("旋转角度必须是 90 的倍数")
    total = page_count(src)
    pages = parse_page_ranges(ranges_text, total)
    try:
        get_backend().rotate_pages(src, output, pages=_spec(pages),
                                   angle=int(degrees))
        return len(pages)
    except Exception as e:  # noqa: BLE001
        raise PdfPageError(f"旋转失败：{e}") from e


def _out_path(out_dir, prefix, index, total):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{prefix}_{index:03d}.pdf"


def _extract_group(src, pages, out_dir, prefix, index, total):
    path = _out_path(out_dir, prefix, index, total)
    get_backend().extract_pages(src, path, _spec(pages))
    return str(path)


def split_pages(src, out_dir, prefix="page") -> list:
    total = page_count(src)
    return [_extract_group(src, [i + 1], out_dir, prefix, i + 1, total)
            for i in range(total)]


def split_every(src, chunk_size, out_dir, prefix="part") -> list:
    if chunk_size <= 0:
        raise PdfPageError("每份页数必须大于 0")
    total = page_count(src)
    results = []
    index = 1
    for start in range(1, total + 1, chunk_size):
        pages = list(range(start, min(start + chunk_size, total + 1)))
        results.append(_extract_group(src, pages, out_dir, prefix, index, total))
        index += 1
    return results


def split_ranges(src, ranges_list, out_dir, prefix="part") -> list:
    total = page_count(src)
    results = []
    for i, ranges_text in enumerate(ranges_list, 1):
        pages = parse_page_ranges(ranges_text, total)
        results.append(_extract_group(src, pages, out_dir, prefix, i, total))
    return results
