#!/usr/bin/env python3
"""语料库完整性检查：读取 manifest，校验已登记文件的 OOXML 结构。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from ooxml_check import check_file  # noqa: E402


def check_pdf(path: Path) -> dict:
    result = {"path": str(path), "ok": False, "errors": []}
    try:
        data = path.read_bytes()
        if not data.startswith(b"%PDF"):
            result["errors"].append("缺少 %PDF 头")
        else:
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            if len(reader.pages) <= 0:
                result["errors"].append("PDF 没有页面")
    except Exception as exc:
        result["errors"].append(str(exc))
    result["ok"] = not result["errors"]
    return result


def check_manifest(manifest_path: Path, strict: bool = False) -> dict:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    base = manifest_path.parent
    summary = {"total": 0, "ready": 0, "missing": 0, "failed": 0, "results": []}
    for sample in data.get("samples", []):
        summary["total"] += 1
        rel = sample.get("path", "")
        if not rel:
            continue
        path = base / rel
        if not path.exists():
            summary["missing"] += 1
            summary["results"].append({"id": sample["id"], "ok": False, "reason": "missing"})
            continue
        if path.suffix.lower() == ".pdf":
            result = check_pdf(path)
        else:
            result = check_file(path)
        if result["ok"]:
            summary["ready"] += 1
        else:
            summary["failed"] += 1
        summary["results"].append({"id": sample["id"], **result})
    summary["ok"] = summary["failed"] == 0 and (not strict or summary["missing"] == 0)
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="语料库完整性检查")
    parser.add_argument("--manifest", default=str(ROOT / "tests" / "corpus" / "manifest.json"))
    parser.add_argument("--strict", action="store_true", help="缺少样本也视为失败")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = check_manifest(Path(args.manifest), strict=args.strict)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for item in result["results"]:
            if item.get("ok"):
                print(f"[OK] {item['id']}")
            else:
                print(f"[FAIL] {item['id']} {item.get('reason', item.get('errors', ''))}")
        print(
            f"summary: total={result['total']} ready={result['ready']} "
            f"missing={result['missing']} failed={result['failed']}"
        )
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
