# -*- coding: utf-8 -*-
"""S3 真实语料 roundtrip：打开 → 保存 → 重开。

- DOCX：bee_export.import_from_docx → export_to_docx → python-docx 重开
- XLSX：pandas 读取首个工作表 → 写出 → 重开；记录结构
- PPTX：beeshow_pptx_import.import_pptx → save_deck(.beshow) → load_deck 重开

这是转换/保存层 roundtrip，不等同于完整 GUI 手工操作。
"""
from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def roundtrip_docx(path: Path, tmp: Path) -> dict:
    from docx import Document
    from beeoffice.plugins.bee_export import export_to_docx, import_from_docx

    md = import_from_docx(str(path))
    out = tmp / (path.stem + "_rt.docx")
    ok = export_to_docx(md, str(out))
    if not ok or not out.exists():
        raise RuntimeError("export_to_docx 返回失败")
    doc = Document(str(out))
    return {"md_chars": len(md or ""), "paragraphs": len(doc.paragraphs),
            "tables": len(doc.tables), "bytes": out.stat().st_size}


def roundtrip_xlsx(path: Path, tmp: Path) -> dict:
    import pandas as pd

    df = pd.read_excel(path, sheet_name=0)
    out = tmp / (path.stem + "_rt.xlsx")
    df.to_excel(out, index=False)
    again = pd.read_excel(out, sheet_name=0)
    return {"rows": int(len(df)), "cols": int(len(df.columns)),
            "rt_rows": int(len(again)), "bytes": out.stat().st_size}


def roundtrip_pptx(path: Path, tmp: Path) -> dict:
    from beeoffice.plugins.beeshow_doc import load_deck, save_deck
    from beeoffice.plugins.beeshow_pptx_import import import_pptx

    imported, md = import_pptx(str(path))
    out = tmp / (path.stem + ".beshow")
    if not save_deck(str(out), md):
        raise RuntimeError("save_deck 失败")
    reopened = load_deck(str(out))
    if not reopened:
        raise RuntimeError("load_deck 返回空")
    return {"slides": len(getattr(imported, "slides", []) or []),
            "md_chars": len(md or ""), "bytes": out.stat().st_size}


ROUNDTRIPS = {".docx": roundtrip_docx, ".xlsx": roundtrip_xlsx, ".pptx": roundtrip_pptx}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--json", required=True)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    root = Path(args.corpus)
    files = [p for p in sorted(root.rglob("*")) if p.suffix.lower() in ROUNDTRIPS]
    if args.limit:
        files = files[: args.limit]
    tmp = Path(tempfile.mkdtemp(prefix="bee_roundtrip_"))
    rows = []
    for path in files:
        start = time.perf_counter()
        row = {"file": str(path.relative_to(root)), "ext": path.suffix.lower()}
        try:
            row["stats"] = ROUNDTRIPS[path.suffix.lower()](path, tmp)
            row["status"] = "ok"
        except Exception as exc:  # noqa: BLE001
            row["status"] = "error"
            row["error"] = f"{type(exc).__name__}: {exc}"[:300]
        row["ms"] = round((time.perf_counter() - start) * 1000, 1)
        rows.append(row)
    summary = {
        "total": len(rows),
        "ok": sum(r["status"] == "ok" for r in rows),
        "error": sum(r["status"] == "error" for r in rows),
        "errors": [r for r in rows if r["status"] != "ok"],
    }
    Path(args.json).write_text(
        json.dumps({"corpus": str(root), "summary": summary, "results": rows},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not summary["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
