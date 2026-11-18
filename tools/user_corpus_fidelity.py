#!/usr/bin/env python3
"""对用户提供的真实语料做一次当前版本保真往返检查。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MANIFEST = ROOT / "tests" / "corpus" / "user-provided-2026-11-18.json"
OUT = ROOT.parent / "analysis" / "user-corpus-report.json"


def docx_metrics(path):
    from docx import Document
    d = Document(str(path))
    return {
        "paragraphs": len([p for p in d.paragraphs if p.text.strip()]),
        "tables": len(d.tables),
        "sections": len(d.sections),
        "images": len(d.inline_shapes),
        "headers": sum(1 for p in d.sections[0].header.paragraphs if p.text.strip()),
        "footers": sum(1 for p in d.sections[0].footer.paragraphs if p.text.strip()),
        "styles": len({p.style.name for p in d.paragraphs if p.style}),
        "fields": sum(1 for el in d.element.body.iter() if el.tag.endswith("}fldSimple") or el.tag.endswith("}fldChar")),
    }


def run_docx(src, out):
    from PySide6.QtWidgets import QApplication
    from beeoffice.plugins.bee_export import (
        import_from_docx, read_docx_header_footer, read_docx_page_settings,
    )
    from beeoffice.plugins.beewrite import BeeWriteEditor
    app = QApplication.instance() or QApplication([])
    md = import_from_docx(str(src))
    meta = read_docx_header_footer(str(src))
    e = BeeWriteEditor(); e._edit_mode = "rich_text"; e.set_content(md)
    e._switch_mode("rich_text")
    e._page_settings.update(read_docx_page_settings(str(src)))
    e._header_text = meta.get("header", "")
    e._footer_text = meta.get("footer", "")
    ok = e._write_docx(str(out))
    e.close()
    return bool(ok)


def excel_metrics(path):
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=False)
    ws = wb.active
    formulas = sum(1 for row in ws.iter_rows() for c in row if isinstance(c.value, str) and c.value.startswith("="))
    return {"sheets": len(wb.sheetnames), "rows": ws.max_row, "cols": ws.max_column,
            "formulas": formulas, "print_area": str(ws.print_area or ""),
            "merged": len(ws.merged_cells.ranges),
            "conditional_formats": len(list(ws.conditional_formatting)),
            "charts": len(ws._charts), "freeze": str(ws.freeze_panes or "")}


def run_excel(src, out):
    import pandas as pd
    from beeoffice.plugins.beesheet_xlsx_export import export_xlsx_preserving_styles, read_xlsx_formulas
    df = pd.read_excel(src)
    return export_xlsx_preserving_styles(str(src), df, str(out), read_xlsx_formulas(str(src)))


def ppt_metrics(path):
    from pptx import Presentation
    prs = Presentation(path)
    texts = charts = tables = pics = trans = timing = notes = 0
    for slide in prs.slides:
        texts += sum(len(shape.text_frame.text.strip()) for shape in slide.shapes if getattr(shape, "has_text_frame", False))
        charts += sum(1 for shape in slide.shapes if getattr(shape, "has_chart", False))
        tables += sum(1 for shape in slide.shapes if getattr(shape, "has_table", False))
        pics += sum(1 for shape in slide.shapes if shape.shape_type == 13)
        trans += 1 if slide.element.find("{http://schemas.openxmlformats.org/presentationml/2006/main}transition") is not None else 0
        timing += 1 if slide.element.find("{http://schemas.openxmlformats.org/presentationml/2006/main}timing") is not None else 0
        notes += 1 if slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip() else 0
    return {"slides": len(prs.slides), "text_chars": texts,
            "charts": charts, "tables": tables, "pics": pics,
            "transitions": trans, "timing": timing, "notes": notes}


def run_ppt(src, out):
    from unittest.mock import patch
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    from beeoffice.plugins.beeshow import BeeShowView
    app = QApplication.instance() or QApplication([])
    s = BeeShowView()
    with patch("PySide6.QtWidgets.QMessageBox.information", return_value=None), patch("PySide6.QtWidgets.QMessageBox.warning", return_value=None):
        opened = s.open_pptx(str(src))
    if not opened:
        s.close(); return False
    with patch("beeoffice.plugins.beeshow_export_mixin.QFileDialog.getSaveFileName", return_value=(str(out), "PowerPoint (*.pptx)")), patch("beeoffice.plugins.beeshow_export_mixin.QMessageBox.information", return_value=None), patch("beeoffice.plugins.beeshow_export_mixin.QMessageBox.warning", return_value=None):
        s._export_pptx()
    s.close()
    return True


def main():
    import tempfile
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    results = []
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for sample in data["samples"]:
            original = Path(sample["path"])
            src = td / (sample["id"] + original.suffix)
            import shutil
            shutil.copy2(original, src)
            out = td / (sample["id"] + "_out" + original.suffix)
            item = {"id": sample["id"], "kind": sample["kind"], "source": str(original)}
            try:
                if sample["kind"] == "word":
                    before = docx_metrics(src)
                    ok = run_docx(src, out)
                    after = docx_metrics(out) if out.exists() else {}
                elif sample["kind"] == "excel":
                    before = excel_metrics(src)
                    ok = run_excel(src, out)
                    after = excel_metrics(out) if out.exists() else {}
                else:
                    before = ppt_metrics(src)
                    ok = run_ppt(src, out)
                    after = ppt_metrics(out) if out.exists() else {}
                item.update({"ok": bool(ok) and out.exists(), "before": before, "after": after})
                if before and after:
                    item["retention"] = {
                        k: (after.get(k, 0) / before[k]) for k in before
                        if isinstance(before[k], (int, float)) and before[k]
                    }
            except Exception as exc:
                item.update({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            results.append(item)
            print(item["id"], "OK" if item["ok"] else "FAIL", item.get("before"), item.get("after"), flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("REPORT", OUT)
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
