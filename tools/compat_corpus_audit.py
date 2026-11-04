# -*- coding: utf-8 -*-
"""S3 兼容性语料审计：逐个打开 DOCX/XLSX/PPTX，记录结构统计与失败。

这是**库级**兼容性基线：验证生产依赖能打开语料；
应用层打开/保存路径由 functional_sweep 与 fidelity 测试覆盖。
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path


def audit_docx(path: Path) -> dict:
    from docx import Document
    doc = Document(str(path))
    paragraphs = len(doc.paragraphs)
    tables = len(doc.tables)
    images = len(doc.inline_shapes)
    return {"paragraphs": paragraphs, "tables": tables, "images": images}


def audit_xlsx(path: Path) -> dict:
    import openpyxl
    wb = openpyxl.load_workbook(str(path), data_only=False, read_only=True)
    try:
        # 只读模式下不逐单元格遍历：大表会耗时数分钟；
        # 用维度乘积作为规模指标，精确内容由应用层测试覆盖。
        cells = sum(
            (ws.max_row or 0) * (ws.max_column or 0) for ws in wb.worksheets
        )
        return {"sheets": len(wb.sheetnames), "cells": cells}
    finally:
        wb.close()


def audit_pptx(path: Path) -> dict:
    from pptx import Presentation
    prs = Presentation(str(path))
    return {"slides": len(prs.slides),
            "shapes": sum(len(s.shapes) for s in prs.slides)}


AUDITORS = {".docx": audit_docx, ".xlsx": audit_xlsx, ".pptx": audit_pptx}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--json", required=True)
    args = ap.parse_args()
    root = Path(args.corpus)
    files = [p for p in root.rglob("*") if p.suffix.lower() in AUDITORS]
    results = []
    for path in sorted(files):
        start = time.perf_counter()
        row = {"file": str(path.relative_to(root)), "ext": path.suffix.lower()}
        try:
            row["stats"] = AUDITORS[path.suffix.lower()](path)
            row["status"] = "ok"
        except Exception as exc:  # noqa: BLE001
            row["status"] = "error"
            row["error"] = f"{type(exc).__name__}: {exc}"[:300]
        row["ms"] = round((time.perf_counter() - start) * 1000, 1)
        results.append(row)
    summary = {
        "total": len(results),
        "ok": sum(r["status"] == "ok" for r in results),
        "error": sum(r["status"] == "error" for r in results),
        "by_ext": dict(Counter(r["ext"] for r in results)),
        "errors": [r for r in results if r["status"] != "ok"],
    }
    out = {"corpus": str(root), "summary": summary, "results": results}
    Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=2),
                               encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not summary["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
