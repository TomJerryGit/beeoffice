# -*- coding: utf-8 -*-
"""S3 性能基线：冷启动、文档打开/导出、内存。

用法：
    python tools/perf_baseline.py --out _ptmp/analysis/s3_perf_baseline.json

说明：
  - 不设阈值，只记录可复测的基线；
  - 默认 offscreen，不弹窗；
  - 文档操作用内存/临时目录，不读写用户文件。
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _median(values):
    return round(statistics.median(values), 1) if values else None


def _rss_mb():
    try:
        import psutil
        return round(psutil.Process().memory_info().rss / 1024 / 1024, 1)
    except Exception:
        return None


def measure_import(repeats=3):
    env = dict(os.environ)
    env.update({
        "QT_QPA_PLATFORM": "offscreen",
        "PYTHONPATH": str(ROOT),
        "PYTHONIOENCODING": "utf-8",
    })
    times = []
    for _ in range(repeats):
        start = time.perf_counter()
        subprocess.run(
            [sys.executable, "-c", "import beeoffice.app"],
            cwd=str(ROOT), env=env, check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        times.append((time.perf_counter() - start) * 1000)
    return {"runs_ms": [round(t, 1) for t in times], "median_ms": _median(times)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "_ptmp" / "analysis" / "s3_perf_baseline.json"))
    args = ap.parse_args()
    result = {"platform": sys.platform, "python": sys.version.split()[0]}

    print("[perf] import_app...", flush=True)
    result["import_app"] = measure_import()

    from PySide6.QtWidgets import QApplication
    from beeoffice.app import BeeApp

    app = QApplication.instance() or QApplication([])

    print("[perf] startup...", flush=True)
    t0 = time.perf_counter()
    window = BeeApp()
    window._lazy_load_modules()
    app.processEvents()
    result["startup"] = {"to_window_ms": round((time.perf_counter() - t0) * 1000, 1),
                         "rss_mb": _rss_mb()}

    tmp = Path(tempfile.mkdtemp(prefix="bee_perf_"))
    result["operations"] = {}

    print("[perf] writer...", flush=True)
    # 蜜写：200 段 Markdown → 富文本 → DOCX
    t0 = time.perf_counter()
    ed = window._new_beewrite()
    t_editor = (time.perf_counter() - t0) * 1000
    md = "\n\n".join(f"## 第 {i} 节\n\n正文 **加粗** 与 *斜体* 第 {i} 段。" for i in range(200))
    t0 = time.perf_counter()
    ed.set_content(md)
    t_content = (time.perf_counter() - t0) * 1000
    t0 = time.perf_counter()
    ed._switch_mode("rich_text")
    t_switch = (time.perf_counter() - t0) * 1000
    t_new = t_editor + t_content + t_switch
    from beeoffice.plugins.bee_export import export_to_docx
    out_docx = tmp / "perf.docx"
    t0 = time.perf_counter()
    ok = export_to_docx(ed.content(), str(out_docx))
    t_docx = (time.perf_counter() - t0) * 1000
    result["operations"]["writer"] = {
        "new_editor_ms": round(t_editor, 1),
        "set_content_ms": round(t_content, 1),
        "markdown_to_rich_ms": round(t_switch, 1),
        "new_and_render_ms": round(t_new, 1),
        "docx_export_ms": round(t_docx, 1),
        "docx_bytes": out_docx.stat().st_size if out_docx.exists() else 0,
        "docx_ok": bool(ok),
    }

    print("[perf] sheet...", flush=True)
    # 蜜算：5000 行 × 10 列 → DataFrame → CSV
    import pandas as pd
    sh = window._new_beesheet()
    df = pd.DataFrame({f"col{i}": range(5000) for i in range(10)})
    t0 = time.perf_counter()
    sh.model.set_full_dataframe(df)
    app.processEvents()
    t_df = (time.perf_counter() - t0) * 1000
    out_csv = tmp / "perf.csv"
    t0 = time.perf_counter()
    df_export = sh._get_export_df()
    df_export.to_csv(out_csv, index=False, encoding="utf-8-sig")
    t_csv = (time.perf_counter() - t0) * 1000
    result["operations"]["sheet"] = {
        "load_50k_cells_ms": round(t_df, 1),
        "csv_export_ms": round(t_csv, 1),
        "csv_bytes": out_csv.stat().st_size if out_csv.exists() else 0,
    }

    print("[perf] show...", flush=True)
    # 蜜演：30 页 → 预览 → PPTX
    show = window._new_beeshow()
    slides = "\n\n---\n\n".join(f"# 第 {i} 页\n\n正文第 {i} 页" for i in range(30))
    t0 = time.perf_counter()
    show._editor.setPlainText(slides)
    show._update_preview()
    app.processEvents()
    t_preview = (time.perf_counter() - t0) * 1000
    out_pptx = tmp / "perf.pptx"
    t0 = time.perf_counter()
    show._export_pptx_legacy(str(out_pptx))
    deadline = time.time() + 60
    while time.time() < deadline and not (out_pptx.exists() and out_pptx.stat().st_size > 1000):
        app.processEvents()
        time.sleep(0.05)
    t_pptx = (time.perf_counter() - t0) * 1000
    result["operations"]["show"] = {
        "preview_30_slides_ms": round(t_preview, 1),
        "pptx_export_ms": round(t_pptx, 1),
        "pptx_bytes": out_pptx.stat().st_size if out_pptx.exists() else 0,
    }

    print("[perf] done", flush=True)
    result["rss_after_mb"] = _rss_mb()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
