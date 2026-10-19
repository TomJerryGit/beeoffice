# tests/fidelity/test_i18n.py
"""
P0-6：语言包**完整性**（英文用户不该看到中文）。

## 修的是什么
`tr(key, default)` 在语言包里找不到 key 时会回退到代码里写的中文默认值 ——
所以 **zh_CN 缺键只是"没登记"，不致命**；但 **en_US 缺键 = 英文界面直接冒出中文** ✗。
审计记的"44 个缺失键"就是这个问题的旧快照（本批实测已有 **53** 个，
因为后续几批又新增了 `cmd.refresh_pivot` / `cmd.add_to_sync` 等 key）。

## 本文件锁住
* 代码里 `tr()` 用到的每个 key，**zh_CN 与 en_US 都必须有**（防止再漏）；
* 语言包必须是合法 JSON、值为非空字符串；
* `tr()` 在两种语言下都能返回对应文案（含 {占位符} 不被破坏）。
"""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOCALES = ROOT / "beeoffice" / "locales"
#: 只匹配 `tr("key")` 与 `tr("key", "...")` 两种调用形态
TR_CALL = re.compile(r'tr\(\s*[\'"]([^\'"]+)[\'"]')


def _used_keys() -> set:
    keys = set()
    for path in (ROOT / "beeoffice").rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            continue
        keys.update(TR_CALL.findall(text))
    return keys


def _load(lang: str) -> dict:
    return json.loads((LOCALES / f"{lang}.json").read_text(encoding="utf-8"))


# ==================== 1. 完整性 ====================

@pytest.mark.parametrize("lang", ["zh_CN", "en_US"])
def test_every_used_key_exists_in_locale(lang):
    """**核心回归**：代码里用到的 key 不能在任何语言包里缺失。"""
    used = _used_keys()
    data = _load(lang)
    missing = sorted(k for k in used if k not in data)
    assert not missing, (
        f"{lang}.json 缺少 {len(missing)} 个 key：{missing[:12]}"
        + ("…" if len(missing) > 12 else "")
    )


@pytest.mark.parametrize("lang", ["zh_CN", "en_US"])
def test_locale_values_are_non_empty_strings(lang):
    data = _load(lang)
    bad = [k for k, v in data.items()
           if not isinstance(v, str) or not v.strip()]
    assert not bad, f"{lang}.json 有空值/非字符串：{bad[:10]}"


def test_locales_have_same_key_set():
    """两种语言必须一一对应（否则切换语言时会出现"有的翻、有的不翻"）。"""
    zh, en = _load("zh_CN"), _load("en_US")
    only_zh = sorted(set(zh) - set(en))
    only_en = sorted(set(en) - set(zh))
    assert not only_zh and not only_en, (
        f"仅 zh_CN 有：{only_zh[:8]}；仅 en_US 有：{only_en[:8]}"
    )


def test_placeholders_are_preserved():
    """`{name}` 这类占位符两边必须一致（否则格式化会抛 KeyError）。"""
    zh, en = _load("zh_CN"), _load("en_US")
    pattern = re.compile(r"\{(\w+)\}")
    problems = []
    for key in zh:
        if key not in en:
            continue
        left = set(pattern.findall(zh[key]))
        right = set(pattern.findall(en[key]))
        if left != right:
            problems.append((key, left, right))
    assert not problems, f"占位符不一致：{problems[:5]}"


# ==================== 2. 运行时确实能取到 ====================

def test_tr_returns_english_after_switch():
    """切到 en_US 后，曾经缺失的 key 必须返回英文（而不是中文默认值）。"""
    from beeoffice.i18n import I18nManager

    manager = I18nManager()
    original = manager.current_language
    try:
        assert manager.set_language("en_US") is True
        assert manager.get("menu.tools", "工具") == "Tools"
        assert manager.get("msg.opened", "已打开：{name}") == "Opened: {name}"
    finally:
        manager.set_language(original)


def test_tr_falls_back_to_default_for_unknown_key():
    """未知 key 仍要回退到调用方给的默认值（这条行为不能被改动弄坏）。"""
    from beeoffice.i18n import I18nManager

    manager = I18nManager()
    assert manager.get("no.such.key", "兜底") == "兜底"
