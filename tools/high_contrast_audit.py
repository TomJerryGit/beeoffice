# -*- coding: utf-8 -*-
"""高对比度审计：AST 定位 setStyleSheet 中硬编码的浅色/深色。

只统计真正传给 QWidget.setStyleSheet 的 QSS 字符串，
排除导出 HTML、移动端模板等非 UI 样式。
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATTERN = re.compile(
    r"(background(?:-color)?\s*:\s*#(?:FFF|FFFFFF|FAFAFA|F5F5F5|FFF8E1|FFF3E0|FFF)"
    r"|color\s*:\s*#(?:333|666|111|000)(?![0-9A-Fa-f]))",
    re.IGNORECASE,
)


def _string_value(node) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            v.value if isinstance(v, ast.Constant) and isinstance(v.value, str)
            else "{}" for v in node.values
        )
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    args = ap.parse_args()
    rows = []
    for path in sorted((ROOT / "beeoffice").rglob("*.py")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(text)
        except Exception:
            continue
        hits = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute)
                    and func.attr == "setStyleSheet"):
                continue
            if not node.args:
                continue
            value = _string_value(node.args[0])
            if value and PATTERN.search(value):
                hits.append({
                    "line": getattr(node, "lineno", 0),
                    "text": value.strip().replace("\n", " ")[:200],
                })
        if hits:
            rows.append({"file": str(path.relative_to(ROOT)),
                         "count": len(hits), "hits": hits})
    result = {
        "files_with_hardcoded_setStyleSheet": len(rows),
        "total_setStyleSheet_hits": sum(r["count"] for r in rows),
        "rows": rows,
    }
    Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=2),
                               encoding="utf-8")
    print(json.dumps({
        "files": result["files_with_hardcoded_setStyleSheet"],
        "hits": result["total_setStyleSheet_hits"],
        "top": [(r["file"], r["count"]) for r in rows],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
