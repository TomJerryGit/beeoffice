# -*- coding: utf-8 -*-
"""
i18n 语言包：不允许堆积无人引用的翻译键

背景：
    命令面板从 `cmd.*` 改名为 `cmd.palette.*` 之后，
    旧键在语言包里躺了 113 条；加上其它改版遗留，
    一次扫描发现 **159 个键没有任何代码引用**。
    这些死键会让翻译工作量和维护成本持续虚高。

本测试把它变成硬约束：新代码改键名时必须同时删旧键。

允许的例外（动态拼接，无法用字面量扫描发现）：
    · `cmd.palette.<slug>`          —— commands.py 用 f-string 拼
    · `theme.accent.<color>`        —— menus.py 用 f-string 拼
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCALES = ROOT / "beeoffice" / "locales"
KEEP_PREFIXES = ("theme.accent.", "cmd.palette.")


def _all_source() -> str:
    parts = []
    for p in (ROOT / "beeoffice").rglob("*.py"):
        try:
            parts.append(p.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    return "\n".join(parts)


def test_no_unused_translation_keys():
    src = _all_source()
    en = json.loads((LOCALES / "en_US.json").read_text(encoding="utf-8"))

    # 注意：源码里既有 tr("k") 也有 tr('k')，只查双引号会误删单引号引用的键
    unused = [
        k for k in en
        if f'"{k}"' not in src and f"'{k}'" not in src
        and not k.startswith(KEEP_PREFIXES)
    ]
    assert not unused, (
        f"发现 {len(unused)} 个无人引用的翻译键（改键名时请同步删除）："
        f"{unused[:10]}"
    )


def test_dynamic_prefixes_are_still_used():
    """例外前缀必须真的还在被动态拼接，否则例外就该取消。"""
    src = _all_source()
    for prefix in KEEP_PREFIXES:
        assert re.search(
            rf'tr\(\s*f"{re.escape(prefix)}\{{', src
        ), f"{prefix} 已不再被动态使用，请从白名单移除"


def test_zh_and_en_key_sets_are_compatible():
    """zh 里出现的键必须都在 en 里（英文不允许缺失）。"""
    en = json.loads((LOCALES / "en_US.json").read_text(encoding="utf-8"))
    zh = json.loads((LOCALES / "zh_CN.json").read_text(encoding="utf-8"))
    missing = sorted(k for k in zh if k not in en)
    assert not missing, f"zh 有而 en 缺：{missing[:10]}"
