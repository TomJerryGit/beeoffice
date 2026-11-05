# -*- coding: utf-8 -*-
"""S4.1 显示缩放验收：在多个 QT_SCALE_FACTOR 下启动最小主窗口并检查关键控件。

注意：这是缩放模拟，不是真实多显示器/混合 DPI 验收。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROBE = r'''
import json, sys
from PySide6.QtWidgets import QApplication
from beeoffice.app import BeeApp
app = QApplication.instance() or QApplication([])
w = BeeApp()
w.resize(1100, 700)
w.show()
w._lazy_load_modules()
editor = w._new_beewrite()
app.processEvents()
screens = [{
    "name": s.name(), "size": [s.geometry().width(), s.geometry().height()],
    "dpr": s.devicePixelRatio()
} for s in app.screens()]
result = {
    "window": [w.width(), w.height()],
    "minimum": [w.minimumWidth(), w.minimumHeight()],
    "screens": screens,
    "status_visible": bool(w.statusBar().isVisible()),
    "zoom_visible": bool(getattr(editor, "_zoom_label", None)
                        and editor._zoom_label.isVisible()),
}
print(json.dumps(result, ensure_ascii=False))
w.close()
'''


def main() -> int:
    out = []
    probe = ROOT / "_display_probe.py"
    probe.write_text(PROBE, encoding="utf-8")
    try:
        for scale in ("1.0", "1.25", "1.5", "2.0"):
            env = dict(os.environ)
            env.update({
                "QT_QPA_PLATFORM": "windows",
                "QT_SCALE_FACTOR": scale,
                "PYTHONPATH": str(ROOT),
                "PYTHONIOENCODING": "utf-8",
            })
            proc = subprocess.run(
                [sys.executable, str(probe)], cwd=str(ROOT), env=env,
                capture_output=True, text=True, timeout=120,
            )
            row = {"scale": scale, "returncode": proc.returncode}
            if proc.returncode == 0 and proc.stdout.strip():
                try:
                    row.update(json.loads(proc.stdout.strip().splitlines()[-1]))
                except Exception:
                    row["raw"] = proc.stdout[-300:]
            else:
                row["stderr"] = (proc.stderr or "")[-300:]
            out.append(row)
    finally:
        try:
            probe.unlink()
        except OSError:
            pass
    result = {"probes": out}
    out_path = ROOT / "_ptmp" / "analysis" / "display_acceptance.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if all(p["returncode"] == 0 for p in out) else 1


if __name__ == "__main__":
    raise SystemExit(main())
