# -*- coding: utf-8 -*-
"""S4 视觉差异对比：基线目录 vs 当前目录。

用法：
    python tools/ui_visual_diff.py --baseline docs/ui-baseline/2026-11-05 \
        --current _ptmp/analysis/current-shots --out _ptmp/analysis/ui-diff
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageChops


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--current", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-diff-percent", type=float, default=None,
                    help="任意截图差异超过该百分比时以非零退出")
    args = ap.parse_args()
    base = Path(args.baseline)
    cur = Path(args.current)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    for base_file in sorted(base.glob("*.png")):
        cur_file = cur / base_file.name
        if not cur_file.exists():
            rows.append((base_file.name, "MISSING", 0.0))
            continue
        a = Image.open(base_file).convert("RGB")
        b = Image.open(cur_file).convert("RGB")
        if a.size != b.size:
            rows.append((base_file.name, f"SIZE {a.size} != {b.size}", 1.0))
            continue
        diff = ImageChops.difference(a, b)
        bbox = diff.getbbox()
        pixels = a.width * a.height
        if bbox is None:
            rows.append((base_file.name, "SAME", 0.0))
            continue
        # 粗略差异比例：非零像素数 / 总像素
        hist = diff.convert("L").histogram()
        changed = sum(hist[9:])
        ratio = changed / max(1, pixels)
        diff.save(out / f"diff-{base_file.name}")
        rows.append((base_file.name, f"DIFF bbox={bbox}", round(ratio * 100, 2)))

    for name, status, ratio in rows:
        print(f"{name:24s} {status:32s} {ratio}%")
    (out / "summary.txt").write_text(
        "\n".join(f"{n}\t{s}\t{r}%" for n, s, r in rows) + "\n",
        encoding="utf-8",
    )
    if args.max_diff_percent is not None:
        over = [r for r in rows if isinstance(r[2], (int, float))
                and r[2] > args.max_diff_percent]
        if over or any("MISSING" in r[1] or "SIZE" in r[1] for r in rows):
            print(f"❌ 视觉差异超阈值 {args.max_diff_percent}%：{over}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
