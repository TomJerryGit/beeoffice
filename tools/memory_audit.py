# -*- coding: utf-8 -*-
"""S3 内存审计：反复创建/渲染/销毁蜜写编辑器，观察 RSS 是否回收。"""
from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def rss_mb():
    try:
        import psutil
        return round(psutil.Process().memory_info().rss / 1024 / 1024, 1)
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", type=int, default=8)
    ap.add_argument("--json", required=True)
    args = ap.parse_args()

    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication
    from beeoffice.plugins.beewrite import BeeWriteEditor

    app = QApplication.instance() or QApplication([])
    gc.collect()
    samples = [{"cycle": 0, "rss_mb": rss_mb()}]
    md = "\n\n".join(f"## 标题 {i}\n\n正文 **粗体** 第 {i} 段。" for i in range(60))
    for i in range(1, args.cycles + 1):
        ed = BeeWriteEditor()
        ed.set_content(md)
        ed._switch_mode("rich_text")
        ed.set_content(md)
        ed.close()
        ed.deleteLater()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
        gc.collect()
        samples.append({"cycle": i, "rss_mb": rss_mb()})
    start = samples[0]["rss_mb"]
    end = samples[-1]["rss_mb"]
    result = {
        "cycles": args.cycles,
        "samples": samples,
        "start_rss_mb": start,
        "end_rss_mb": end,
        "delta_mb": round(end - start, 1) if start is not None and end is not None else None,
        "per_cycle_mb": round((end - start) / args.cycles, 2) if start is not None and end is not None else None,
    }
    Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=2),
                               encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
