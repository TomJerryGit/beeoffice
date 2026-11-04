# beeoffice/pdf_common.py
"""PDF 工具的公共错误与页码解析（不依赖任何 PDF 引擎）。"""
from __future__ import annotations

import re
from typing import List, Optional


class PdfToolError(Exception):
    """PDF 工具的可预期失败（坏文件/页码越界/缺少依赖等）。"""


def parse_page_spec(spec: Optional[str], total: int) -> List[int]:
    """解析 1 基页码表达式为 0 基索引列表（保持顺序、去重）。"""
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
