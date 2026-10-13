# tools/ooxml_probe.py
"""
OOXML 特征探针 —— 保真度测试集的**测量仪器**（阶段 A）

它做什么
--------
读一个 `.docx` / `.xlsx` / `.pptx`，数出里面**有意义的结构特征**：

    DOCX: 段落/文字数/带样式的段落/标题/表格/合并单元格/图片/超链接/
          书签/域/修订/分节/页边距/页眉页脚部件/批注
    XLSX: 工作表/非空单元格/公式/合并区域/数字格式/条件格式/数据验证/
          冻结窗格/定义名称/图表/表格对象
    PPTX: 幻灯片/形状/图片/表格/文本 run/文字数/备注页/版式/母版/超链接

然后**往返前后各探一次**，把差值列出来 —— 这就是"丢了多少"。

为什么不用 XML 直接 diff
------------------------
OOXML 往返后必然出现大量无意义差异（rId 重编号、rsid、时间戳、部件顺序），
直接 diff 会淹没真正的丢失。**特征计数**对这类问题更稳、更好读，也更容易
写成断言。需要深挖时再看部件清单（本模块也输出）。

测量仪器的可信度
----------------
`tests/fidelity/test_ooxml_probe.py` 里有**自检**：喂两个已知不同的文件，
探针必须报出差异。否则这套数字可能全是常数（"恒真的测试"是本项目的常见坑）。

用法
----
    python tools/ooxml_probe.py 文件或目录 [...]
"""

import sys
import zipfile
from pathlib import Path

try:
    from lxml import etree
except ImportError:  # pragma: no cover
    etree = None

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def _q(prefix, tag):
    return f"{{{NS[prefix]}}}{tag}"


def _read_xml(zf, name):
    try:
        data = zf.read(name)
    except KeyError:
        return None
    try:
        return etree.fromstring(data)
    except Exception:
        return None


def _count(root, xpath):
    if root is None:
        return 0
    return len(root.findall(xpath))


def _text_chars(root, xpath):
    if root is None:
        return 0
    return sum(len((el.text or "")) for el in root.findall(xpath))


def probe_docx(zf):
    """DOCX 特征。"""
    doc = _read_xml(zf, "word/document.xml")
    styles = _read_xml(zf, "word/styles.xml")

    parts = [n for n in zf.namelist() if not n.endswith("/")]
    headers = [n for n in parts if n.startswith("word/header")]
    footers = [n for n in parts if n.startswith("word/footer")]

    # 页边距（取第一个 sectPr）
    margins = ""
    if doc is not None:
        pgmar = doc.find(f".//{_q('w', 'pgMar')}")
        if pgmar is not None:
            keys = ("top", "right", "bottom", "left")
            margins = ",".join(pgmar.get(_q("w", k), "") for k in keys)

    # 样式化的段落数 & 标题数
    styled = 0
    headings = 0
    if doc is not None:
        for pstyle in doc.findall(f".//{_q('w', 'pStyle')}"):
            styled += 1
            val = (pstyle.get(_q("w", "val")) or "")
            low = val.lower()
            if low.startswith("heading") or "标题" in val:
                headings += 1

    features = {
        "sections": _count(doc, f".//{_q('w', 'sectPr')}"),
        "paragraphs": _count(doc, f".//{_q('w', 'p')}"),
        "text_chars": _text_chars(doc, f".//{_q('w', 't')}"),
        "style_defined": _count(styles, f".//{_q('w', 'style')}"),
        "styled_paragraphs": styled,
        "headings": headings,
        "tables": _count(doc, f".//{_q('w', 'tbl')}"),
        "table_rows": _count(doc, f".//{_q('w', 'tr')}"),
        "table_cells": _count(doc, f".//{_q('w', 'tc')}"),
        "merged_cells": (
            _count(doc, f".//{_q('w', 'gridSpan')}")
            + _count(doc, f".//{_q('w', 'vMerge')}")
        ),
        "images": _count(doc, f".//{_q('a', 'blip')}"),
        "hyperlinks": _count(doc, f".//{_q('w', 'hyperlink')}"),
        "bookmarks": _count(doc, f".//{_q('w', 'bookmarkStart')}"),
        "fields": (
            _count(doc, f".//{_q('w', 'fldSimple')}")
            + _count(doc, f".//{_q('w', 'instrText')}")
        ),
        "revisions": (
            _count(doc, f".//{_q('w', 'ins')}")
            + _count(doc, f".//{_q('w', 'del')}")
        ),
        "header_parts": len(headers),
        "footer_parts": len(footers),
        "has_comments": int("word/comments.xml" in parts),
        "has_numbering": int("word/numbering.xml" in parts),
        "page_margins": margins,
    }
    return {"format": "docx", "parts": parts, "features": features}


def probe_xlsx(zf):
    """XLSX 特征。"""
    parts = [n for n in zf.namelist() if not n.endswith("/")]
    workbook = _read_xml(zf, "xl/workbook.xml")
    styles = _read_xml(zf, "xl/styles.xml")

    sheet_parts = sorted(
        n for n in parts
        if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")
    )

    nonempty = formulas = merged = cond = validations = 0
    frozen = 0
    for name in sheet_parts:
        sh = _read_xml(zf, name)
        if sh is None:
            continue
        for c in sh.findall(f".//{_q('x', 'c')}"):
            if c.find(_q("x", "v")) is not None \
                    or c.find(_q("x", "is")) is not None \
                    or c.find(_q("x", "f")) is not None:
                nonempty += 1
        formulas += _count(sh, f".//{_q('x', 'f')}")
        merged += _count(sh, f".//{_q('x', 'mergeCell')}")
        cond += _count(sh, f".//{_q('x', 'conditionalFormatting')}")
        validations += _count(sh, f".//{_q('x', 'dataValidation')}")
        for pane in sh.findall(f".//{_q('x', 'pane')}"):
            if (pane.get("state") or "") in ("frozen", "frozenSplit"):
                frozen += 1

    features = {
        "sheets": len(sheet_parts),
        "nonempty_cells": nonempty,
        "formulas": formulas,
        "merged_ranges": merged,
        "conditional_formatting": cond,
        "data_validations": validations,
        "freeze_panes": frozen,
        "defined_names": _count(
            workbook, f".//{_q('x', 'definedName')}"
        ),
        "cell_xfs": _count(styles, f".//{_q('x', 'cellXfs')}/{_q('x', 'xf')}"),
        "charts": len([n for n in parts if n.startswith("xl/charts/chart")]),
        "table_objects": len(
            [n for n in parts if "/tables/table" in n]
        ),
    }
    return {"format": "xlsx", "parts": parts, "features": features}


def probe_pptx(zf):
    """PPTX 特征。"""
    parts = [n for n in zf.namelist() if not n.endswith("/")]
    slides = sorted(
        n for n in parts
        if n.startswith("ppt/slides/slide") and n.endswith(".xml")
    )

    shapes = pictures = tables = runs = chars = hyperlinks = 0
    for name in slides:
        s = _read_xml(zf, name)
        if s is None:
            continue
        shapes += _count(s, f".//{_q('p', 'sp')}")
        pictures += _count(s, f".//{_q('p', 'pic')}")
        tables += _count(s, f".//{_q('a', 'tbl')}")
        runs += _count(s, f".//{_q('a', 'r')}")
        chars += _text_chars(s, f".//{_q('a', 't')}")
        hyperlinks += _count(s, f".//{_q('a', 'hlinkClick')}")

    features = {
        "slides": len(slides),
        "shapes": shapes,
        "pictures": pictures,
        "tables": tables,
        "text_runs": runs,
        "text_chars": chars,
        "hyperlinks": hyperlinks,
        "notes_slides": len(
            [n for n in parts if n.startswith("ppt/notesSlides/notesSlide")]
        ),
        "slide_layouts": len(
            [n for n in parts if n.startswith("ppt/slideLayouts/slideLayout")]
        ),
        "slide_masters": len(
            [n for n in parts if n.startswith("ppt/slideMasters/slideMaster")]
        ),
        "media_files": len([n for n in parts if n.startswith("ppt/media/")]),
    }
    return {"format": "pptx", "parts": parts, "features": features}


def probe(path):
    """按扩展名探测一个 OOXML 文件。"""
    path = Path(path)
    if etree is None:
        raise RuntimeError("需要 lxml：pip install lxml")
    suffix = path.suffix.lower()
    factory = {
        ".docx": probe_docx, ".xlsx": probe_xlsx, ".pptx": probe_pptx,
    }.get(suffix)
    if factory is None:
        raise ValueError(f"不支持的格式: {path}")

    with zipfile.ZipFile(path) as zf:
        result = factory(zf)
    result["path"] = str(path)
    result["size"] = path.stat().st_size
    return result


def compare(before, after):
    """
    比较两次探测，返回逐特征的差异列表。

    :return: [{feature, before, after, delta, status}, ...]
             status ∈ {"same", "lost", "gained", "changed"}
    """
    fb = before["features"]
    fa = after["features"]
    rows = []
    for key in fb:
        b = fb[key]
        a = fa.get(key, None)
        if b == a:
            status = "same"
        elif isinstance(b, (int, float)) and isinstance(a, (int, float)):
            status = "lost" if a < b else "gained"
        else:
            status = "changed"
        rows.append({
            "feature": key, "before": b, "after": a,
            "delta": (a - b) if isinstance(b, int) and isinstance(a, int)
            else None,
            "status": status,
        })
    return rows


def format_report(before, after, title=""):
    """把 compare 结果排成可读表格。"""
    rows = compare(before, after)
    lost = [r for r in rows if r["status"] == "lost"]
    changed = [r for r in rows if r["status"] == "changed"]
    gained = [r for r in rows if r["status"] == "gained"]

    lines = []
    if title:
        lines.append(title)
    lines.append(f"  文件: {before['path']}  ({before['size']} B)")
    lines.append(f"  往返后: {after['path']}  ({after['size']} B)")
    lines.append(
        f"  丢失项 {len(lost)} / 变化项 {len(changed)} / 增加项 {len(gained)}"
    )
    lines.append(f"  {'特征':<24}{'往返前':>10}{'往返后':>10}")
    lines.append("  " + "-" * 46)
    for r in rows:
        if r["status"] == "same":
            continue
        mark = {"lost": "↓", "gained": "↑", "changed": "~"}[r["status"]]
        lines.append(
            f"  {mark} {r['feature']:<22}{str(r['before']):>10}"
            f"{str(r['after']):>10}"
        )
    return "\n".join(lines)


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    for arg in argv:
        p = Path(arg)
        targets = sorted(
            [p] if p.is_file()
            else [f for f in p.rglob("*")
                  if f.suffix.lower() in (".docx", ".xlsx", ".pptx")]
        )
        for target in targets:
            info = probe(target)
            print(f"\n=== {target} ({info['format']}) ===")
            for k, v in info["features"].items():
                print(f"  {k:<24}{v}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
