#!/usr/bin/env python3
"""按测试文件启动独立 pytest 子进程，定位 WebEngine 崩溃触发点。"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", default="tests/qt", help="测试目录")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--json", default="")
    args = parser.parse_args(argv)
    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu")
    env.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
    env.setdefault("PYTHONPATH", str(ROOT))
    env.setdefault("PYTHONIOENCODING", "utf-8")
    files = sorted((ROOT / args.group).rglob("test_*.py"))
    result = []
    failed = []
    for i, path in enumerate(files, 1):
        rel = path.relative_to(ROOT).as_posix()
        t0 = time.time()
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", rel, "-q", "--no-header",
                 "-p", "no:cacheprovider", "-o", "log_file=",
                 f"--timeout={args.timeout}"],
                cwd=str(ROOT), env=env, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=args.timeout + 30,
            )
            code = proc.returncode
            tail = (proc.stdout + proc.stderr)[-400:]
        except subprocess.TimeoutExpired:
            code = "TIMEOUT"
            tail = "timeout"
        item = {"file": rel, "exit": code, "seconds": round(time.time() - t0, 2),
                "tail": tail}
        result.append(item)
        if code != 0:
            failed.append(item)
            print(f"[FAIL] {rel} exit={code} {item['seconds']}s", flush=True)
        else:
            print(f"[OK] {rel} {item['seconds']}s", flush=True)
    print(f"\nFILES={len(files)} FAILED={len(failed)}")
    for item in failed:
        print(f"- {item['file']} exit={item['exit']}:\n{item['tail']}\n")
    if args.json:
        Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
