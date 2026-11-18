#!/usr/bin/env python3
"""轻量 OOXML 完整性校验：ZIP、必需部件、XML 可解析性。

不替代 Open XML SDK；用于 CI 快速拦截损坏文件。
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

REQUIRED = {
    ".docx": ("word/document.xml",),
    ".xlsx": ("xl/workbook.xml",),
    ".pptx": ("ppt/presentation.xml",),
}


def check_file(path: Path) -> dict:
    result = {"path": str(path), "ok": False, "errors": [], "warnings": []}
    if not path.exists():
        result["errors"].append("文件不存在")
        return result
    ext = path.suffix.lower()
    if ext not in REQUIRED:
        result["errors"].append(f"不支持的扩展名: {ext}")
        return result
    try:
        with zipfile.ZipFile(path) as z:
            bad = z.testzip()
            if bad:
                result["errors"].append(f"ZIP 损坏: {bad}")
                return result
            names = set(z.namelist())
            for required in ("[Content_Types].xml", "_rels/.rels", *REQUIRED[ext]):
                if required not in names:
                    result["errors"].append(f"缺少部件: {required}")
            for name in sorted(names):
                if not (name.endswith(".xml") or name.endswith(".rels")):
                    continue
                try:
                    ElementTree.fromstring(z.read(name))
                except ElementTree.ParseError as exc:
                    result["errors"].append(f"XML 解析失败: {name}: {exc}")
    except zipfile.BadZipFile as exc:
        result["errors"].append(f"不是有效 ZIP: {exc}")
    result["ok"] = not result["errors"]
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="OOXML 完整性校验")
    parser.add_argument("paths", nargs="+", help="docx/xlsx/pptx 文件")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)
    results = [check_file(Path(p)) for p in args.paths]
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for item in results:
            status = "OK" if item["ok"] else "FAIL"
            print(f"[{status}] {item['path']}")
            for err in item["errors"]:
                print(f"  - {err}")
    return 0 if all(item["ok"] for item in results) else 1


if __name__ == "__main__":
    sys.exit(main())
