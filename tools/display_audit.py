# -*- coding: utf-8 -*-
"""多显示器/DPI 环境审计（S4.1 UI-15 基线）。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    args = ap.parse_args()

    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication([])
    screens = []
    for screen in app.screens():
        geo = screen.geometry()
        avail = screen.availableGeometry()
        screens.append({
            "name": screen.name(),
            "geometry": [geo.x(), geo.y(), geo.width(), geo.height()],
            "available": [avail.x(), avail.y(), avail.width(), avail.height()],
            "device_pixel_ratio": screen.devicePixelRatio(),
            "logical_dpi": screen.logicalDotsPerInch(),
            "physical_dpi": screen.physicalDotsPerInch(),
        })
    result = {"screen_count": len(screens), "screens": screens}
    Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=2),
                               encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
