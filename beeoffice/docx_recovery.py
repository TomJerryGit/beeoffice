"""DOCX 打开失败时的可读文本兜底。"""
from __future__ import annotations

import zipfile
from lxml import etree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def recover_plain_text(path) -> str:
    """尽量从损坏/不兼容 DOCX 中提取可读文本。"""
    try:
        with zipfile.ZipFile(str(path)) as z:
            if "word/document.xml" not in z.namelist():
                return ""
            root = etree.fromstring(z.read("word/document.xml"))
    except Exception:
        return ""
    lines = []
    for p in root.iter(W + "p"):
        parts = []
        for t in p.iter(W + "t"):
            parts.append(t.text or "")
        if parts:
            lines.append("".join(parts))
    return "\n".join(lines)
