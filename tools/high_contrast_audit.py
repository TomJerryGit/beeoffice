# -*- coding: utf-8 -*-
"""高对比度审计：找出仍硬编码浅色背景/文字的插件内联样式。"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATTERN = re.compile(
    r"(background(?:-color)?\s*:\s*#(?:FFF|FFFFFF|FAFAFA|F5F5F5|FFF8E1|FFF3E0)"
    r"|color\s*:\s*#(?:333|666|111|000)(?![0-9A-Fa-f]))",
    re.IGNORECASE,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    args = ap.parse_args()
    rows = []
    for path in sorted((ROOT / "beeoffice").rglob("*.py")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        hits = []
        for i, line in enumerate(text.splitlines(), 1):
            if PATTERN.search(line):
                hits.append({"line": i, "text": line.strip()[:160]})
        if hits:
            rows.append({
                "file": str(path.relative_to(ROOT)),
                "count": len(hits),
                "hits": hits,
            })
    result = {
        "files_with_hardcoded_colors": len(rows),
        "total_hits": sum(r["count"] for r in rows),
        "rows": rows,
    }
    Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=2),
                               encoding="utf-8")
    print(json.dumps({
        "files_with_hardcoded_colors": result["files_with_hardcoded_colors"],
        "total_hits": result["total_hits"],
        "top": [(r["file"], r["count"]) for r in rows[:12]],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
