# -*- coding: utf-8 -*-
"""
i18n 走查：导出中英对照表，并自动检测术语不一致。

检测三类问题：
    1. 同一句中文 → 多个不同英文（同一句话在不同地方译法不同，应统一）
    2. 同一个英文 ← 多个不同中文（可能是一词多义，需要人工确认）
    3. 核心术语混用（Sheet / Table、Comment / Reply 等）

用法：
    python tools/i18n_review.py                 # 打印摘要 + 写到 docs/i18n-review.md
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EN_PATH = ROOT / "beeoffice" / "locales" / "en_US.json"
OUT_PATH = ROOT / "docs" / "i18n-review.md"

# tr("key", "中文默认值")  —— 只取单行字面量
TR_PATTERN = re.compile(r'tr\(\s*"([^"]+)"\s*,\s*"((?:[^"\\]|\\.)*)"\s*\)')

# 需要重点关注的核心术语（英文侧）
CORE_TERMS = [
    "Sheet", "Table", "Slide", "Note", "Comment", "Reply",
    "Template", "Export", "Save", "Document", "Outline",
]


def collect_zh():
    """扫描源码，建立 key → 中文默认值。"""
    pairs = {}
    for p in (ROOT / "beeoffice").rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        try:
            src = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for key, zh in TR_PATTERN.findall(src):
            # 跳过不像真 key 的匹配：注释里的示例（如 tr("k", "中文")）
            # 真实键一定是 `模块.条目` 形式，至少含一个点
            if "." not in key:
                continue
            pairs.setdefault(key, zh)
    return pairs


def module_of(key: str) -> str:
    parts = key.split(".")
    if len(parts) >= 2:
        return parts[1] if parts[0] == "auto" else parts[0]
    return key


def main():
    zh_by_key = collect_zh()
    en = json.loads(EN_PATH.read_text(encoding="utf-8"))

    rows = []
    for key, english in en.items():
        zh = zh_by_key.get(key)
        if zh is None:
            continue  # 手工 key（tab.* / cmd.palette.*）的中文不在这份扫描里
        rows.append((module_of(key), zh, english))

    rows.sort()

    # 0) 代码里用了 tr() 但语言包缺英文（会静默回退成中文，最隐蔽）
    missing = sorted(k for k in zh_by_key if k not in en)

    # 1) 同一中文 → 多个英文
    zh_to_en = defaultdict(set)
    for _m, zh, english in rows:
        zh_to_en[zh].add(english)
    zh_conflicts = {k: v for k, v in zh_to_en.items() if len(v) > 1}

    # 2) 同一英文 ← 多个中文
    en_to_zh = defaultdict(set)
    for _m, zh, english in rows:
        en_to_zh[english].add(zh)
    en_collisions = {k: v for k, v in en_to_zh.items() if len(v) > 1}

    # 3) 核心术语分布
    term_hits = defaultdict(list)
    for _m, zh, english in rows:
        for term in CORE_TERMS:
            if re.search(rf"\b{term}", english):
                term_hits[term].append((zh, english))

    lines = ["# i18n 走查报告", ""]
    lines.append(f"- 代码中的 tr() key：**{len(zh_by_key)}**")
    lines.append(f"- **英文缺失（会回退中文）：{len(missing)}**")
    lines.append(f"- 可对照条目：**{len(rows)}**")
    lines.append(f"- 同一中文多种译法：**{len(zh_conflicts)}**")
    lines.append(f"- 同一英文对应多个中文：**{len(en_collisions)}**")
    lines.append("")

    lines.append("## 0. 缺失英文的 key（必须为 0）")
    lines.append("")
    if missing:
        for k in missing:
            lines.append(f"- `{k}` ← {zh_by_key[k]}")
    else:
        lines.append("（无）")
    lines.append("")

    lines.append("## 1. 同一中文 → 多种英文（需要统一）")
    lines.append("")
    if zh_conflicts:
        for zh, variants in sorted(zh_conflicts.items()):
            lines.append(f"- **{zh}**")
            for v in sorted(variants):
                lines.append(f"  - {v}")
    else:
        lines.append("（无）")
    lines.append("")

    lines.append("## 2. 同一英文 ← 多个中文（确认是否有意）")
    lines.append("")
    for english, zhs in sorted(en_collisions.items())[:60]:
        lines.append(f"- **{english}** ← {' / '.join(sorted(zhs))}")
    lines.append("")

    lines.append("## 3. 核心术语分布")
    lines.append("")
    for term in CORE_TERMS:
        hits = term_hits.get(term, [])
        if not hits:
            continue
        lines.append(f"### {term}（{len(hits)} 条）")
        for zh, english in sorted(hits)[:12]:
            lines.append(f"- {zh} → {english}")
        lines.append("")

    lines.append("## 4. 全量对照表")
    lines.append("")
    lines.append("| 模块 | 中文 | English |")
    lines.append("|---|---|---|")
    for module, zh, english in rows:
        zhs = zh.replace("|", "\\|")
        ens = english.replace("|", "\\|")
        lines.append(f"| {module} | {zhs} | {ens} |")

    OUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"可对照条目      : {len(rows)}")
    print(f"英文缺失        : {len(missing)}")
    print(f"同一中文多译法  : {len(zh_conflicts)}")
    print(f"同一英文多中文  : {len(en_collisions)}")
    print(f"报告已写入      : {OUT_PATH.relative_to(ROOT)}")

    if missing:
        print("\n缺失英文的 key：")
        for k in missing[:15]:
            print(f"  {k}  ← {zh_by_key[k]}")

    if zh_conflicts:
        print("\n需要统一的术语：")
        for zh, variants in list(sorted(zh_conflicts.items()))[:12]:
            print(f"  {zh}  ->  {' | '.join(sorted(variants))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
