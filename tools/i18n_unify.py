# -*- coding: utf-8 -*-
"""
术语统一：把「同一句中文」的所有英文词条强制改成同一个说法。

场景：
    同一个中文在不同模块被译成两种英文（例如 删除失败 → Delete failed / Deletion failed）。
    本工具按中文原文定位所有相关 key，统一覆盖。

用法：
    python tools/i18n_unify.py docs/canonical.json

canonical.json 形如：
    { "删除失败": "Delete failed", "自然语言生成公式": "Formula from Plain Language" }
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EN_PATH = ROOT / "beeoffice" / "locales" / "en_US.json"
TR_PATTERN = re.compile(r'tr\(\s*"([^"]+)"\s*,\s*"((?:[^"\\]|\\.)*)"\s*\)')


def collect_zh():
    pairs = {}
    for p in (ROOT / "beeoffice").rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        try:
            src = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for key, zh in TR_PATTERN.findall(src):
            pairs.setdefault(key, zh)
    return pairs


def main(argv):
    if not argv:
        print("用法: python tools/i18n_unify.py <canonical.json>")
        return 1
    canonical = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    zh_by_key = collect_zh()
    en = json.loads(EN_PATH.read_text(encoding="utf-8"))

    changed = 0
    for key, zh in zh_by_key.items():
        if zh in canonical and key in en and en[key] != canonical[zh]:
            print(f"  {en[key]!r} -> {canonical[zh]!r}   ({zh})")
            en[key] = canonical[zh]
            changed += 1

    EN_PATH.write_text(
        json.dumps(en, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\n已统一 {changed} 条；en_US 共 {len(en)} keys")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
