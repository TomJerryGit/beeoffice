#!/usr/bin/env python3
"""分段运行 Qt/单元/回归/根测试，规避一次性 WebEngine 崩溃。"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GROUPS = [
    ("qt", "tests/qt"),
    ("unit", "tests/unit"),
    ("regression", "tests/regression"),
    ("root", "tests --ignore=tests/qt --ignore=tests/unit --ignore=tests/regression"),
]


def main() -> int:
    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu")
    env.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
    env.setdefault("PYTHONPATH", str(ROOT))
    env.setdefault("PYTHONIOENCODING", "utf-8")
    failed = []
    for name, target in GROUPS:
        cmd = [sys.executable, "-m", "pytest", *target.split(), "-q",
               "--no-header", "-p", "no:cacheprovider", "-o", "log_file=",
               "--timeout=300"]
        print(f"=== {name} ===", flush=True)
        proc = subprocess.run(cmd, cwd=str(ROOT), env=env)
        if proc.returncode != 0:
            failed.append(name)
    print("FAILED_GROUPS=" + ",".join(failed), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
