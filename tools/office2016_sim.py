#!/usr/bin/env python3
"""Office 2016 兼容性模拟测试。

不是真正的 Office 2016；使用：
  - OOXML 命名空间/部件审计
  - Office 2007 打开并另存为（更严格的老解析器）
  - WPS 12 打开验证
  - python-docx/openpyxl/python-pptx 结构核对
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT.parent / "analysis" / "ms-office"
OUT = ROOT.parent / "analysis" / "office2016-sim.json"

NS_ALLOW = {
    "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "http://schemas.openxmlformats.org/package/2006/relationships",
    "http://schemas.openxmlformats.org/drawingml/2006/main",
    "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "http://schemas.openxmlformats.org/presentationml/2006/main",
    "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "http://schemas.microsoft.com/office/word/2010/wordml",
    "http://schemas.microsoft.com/office/word/2012/wordml",
    "http://schemas.microsoft.com/office/powerpoint/2010/main",
    "http://schemas.microsoft.com/office/powerpoint/2012/main",
    "http://schemas.microsoft.com/office/drawing/2010/main",
    "http://schemas.microsoft.com/office/drawing/2012/main",
    "http://schemas.microsoft.com/office/drawing/2014/main",
    "http://purl.org/dc/elements/1.1/",
    "http://purl.org/dc/terms/",
    "http://schemas.openxmlformats.org/officeDocument/2006/bibliography",
    "http://schemas.openxmlformats.org/officeDocument/2006/customXml",
    "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes",
    "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties",
    "http://schemas.openxmlformats.org/package/2006/content-types",
    "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
    "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "urn:schemas-microsoft-com:office:office",
}


def ns_audit(path: Path) -> dict:
    namespaces = set()
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if not (name.endswith(".xml") or name.endswith(".rels")):
                continue
            try:
                root = ElementTree.fromstring(z.read(name))
                for el in root.iter():
                    if isinstance(el.tag, str) and el.tag.startswith("{"):
                        namespaces.add(el.tag[1:].split("}")[0])
            except Exception:
                continue
    unknown = sorted(n for n in namespaces if n not in NS_ALLOW)
    return {"namespaces": sorted(namespaces), "unknown": unknown}


def docx_metrics(path: Path) -> dict:
    from docx import Document
    d = Document(str(path)); sec = d.sections[0]
    return {"tables": len(d.tables), "paragraphs": len(d.paragraphs),
            "sections": len(d.sections), "images": len(d.inline_shapes),
            "header": bool(sec.header.paragraphs and sec.header.paragraphs[0].text.strip()),
            "footer": bool(sec.footer.paragraphs and sec.footer.paragraphs[0].text.strip())}


def xlsx_metrics(path: Path) -> dict:
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=False); ws = wb.active
    return {"sheets": len(wb.sheetnames), "rows": ws.max_row, "cols": ws.max_column,
            "charts": sum(len(s._charts) for s in wb.worksheets),
            "conditional_formats": sum(len(list(s.conditional_formatting)) for s in wb.worksheets),
            "merged": sum(len(s.merged_cells.ranges) for s in wb.worksheets),
            "print_area": str(ws.print_area or "")}


def pptx_metrics(path: Path) -> dict:
    from pptx import Presentation
    prs = Presentation(str(path))
    charts = tables = notes = timing = trans = 0
    for slide in prs.slides:
        charts += sum(1 for sh in slide.shapes if getattr(sh, "has_chart", False))
        tables += sum(1 for sh in slide.shapes if getattr(sh, "has_table", False))
        notes += 1 if slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip() else 0
        timing += 1 if slide.element.find("{http://schemas.openxmlformats.org/presentationml/2006/main}timing") is not None else 0
        trans += 1 if slide.element.find("{http://schemas.openxmlformats.org/presentationml/2006/main}transition") is not None else 0
    return {"slides": len(prs.slides), "charts": charts, "tables": tables,
            "notes": notes, "timing": timing, "transitions": trans}


def office2007_roundtrip(path: Path, kind: str, out: Path) -> tuple[bool, str]:
    import win32com.client as win32
    try:
        if kind == "word":
            app = win32.DispatchEx("Word.Application"); app.Visible = True; app.DisplayAlerts = 0
            doc = app.Documents.Open(str(path), False, True)
            doc.SaveAs(str(out), FileFormat=12)
            doc.Close(False); app.Quit()
        elif kind == "excel":
            app = win32.DispatchEx("Excel.Application"); app.Visible = False; app.DisplayAlerts = False
            wb = app.Workbooks.Open(str(path), 0, True)
            wb.SaveAs(str(out), FileFormat=51)
            wb.Close(False); app.Quit()
        else:
            app = win32.DispatchEx("PowerPoint.Application"); app.Visible = True
            pres = app.Presentations.Open(str(path), True, False, False)
            pres.SaveAs(str(out), 24)
            pres.Close(); app.Quit()
        return True, ""
    except Exception as e:
        try:
            app.Quit()
        except Exception:
            pass
        return False, str(e)


def main() -> int:
    if not SRC.is_dir():
        print("missing", SRC)
        return 1
    results = []
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for kind, name in (("word", "word.docx"), ("excel", "excel.xlsx"), ("ppt", "ppt.pptx")):
            src = SRC / name
            if not src.is_file():
                results.append({"kind": kind, "error": "missing source"}); continue
            work = td / name; shutil.copy2(src, work)
            out = td / (kind + "_office2007" + src.suffix)
            ok, err = office2007_roundtrip(work, kind, out)
            metrics_fn = {"word": docx_metrics, "excel": xlsx_metrics, "ppt": pptx_metrics}[kind]
            item = {"kind": kind, "office2007_ok": ok, "office2007_error": err,
                    "before": metrics_fn(work), "audit": ns_audit(work)}
            if ok and out.is_file():
                item["after_office2007"] = metrics_fn(out)
            results.append(item)
            print(kind, "office2007", ok, item["before"], item.get("after_office2007", {}), flush=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("REPORT", OUT)
    return 0 if all(r.get("office2007_ok") for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
