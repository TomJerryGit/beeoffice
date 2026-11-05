# -*- coding: utf-8 -*-
"""S4 视觉回归基线：抓取关键页面截图并生成 sha256 清单。

用法：
    python tools/ui_screenshots.py --out docs/ui-baseline/2026-11-05
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs" / "ui-baseline" / "2026-11-05"))
    ap.add_argument("--lang", default="")
    ap.add_argument("--contrast", action="store_true")
    args = ap.parse_args()

    from PySide6.QtWidgets import QApplication
    if args.lang:
        from beeoffice.i18n import set_language
        set_language(args.lang)
    if args.contrast:
        from beeoffice.theme import Theme
        Theme.set_high_contrast(True)
    from beeoffice.app import BeeApp

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    window = BeeApp()
    if args.contrast:
        from beeoffice.theme import Theme
        Theme.set_high_contrast(True)
        window._apply_theme()
    window.resize(1360, 860)
    window.show()
    window._lazy_load_modules()
    app.processEvents()

    shots = []

    def snap(name):
        app.processEvents()
        pix = window.grab()
        path = out / f"{name}.png"
        pix.save(str(path), "PNG")
        shots.append({"name": name, "file": path.name, "sha256": _sha(path),
                      "width": pix.width(), "height": pix.height()})

    snap("01-welcome")
    window._new_beewrite()
    app.processEvents()
    snap("02-beewrite")
    window._new_beesheet()
    app.processEvents()
    snap("03-beesheet")
    window._new_beeshow()
    app.processEvents()
    snap("04-beeshow")

    manifest = {
        "date": "2026-11-05",
        "platform": sys.platform,
        "dpi": os.environ.get("QT_SCALE_FACTOR", "1"),
        "language": args.lang or "default",
        "high_contrast": bool(args.contrast),
        "shots": shots,
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
