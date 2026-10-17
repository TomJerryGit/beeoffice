# -*- coding: utf-8 -*-
"""
i18n 试点：标签页文案可随语言切换（tab_manager）

背景：
    全仓 1631 条中文 UI 字符串里只有 146 处走了 tr()（约 8%）。
    本次以 TabManager 为试点跑通完整流程：
        控件文案 → tr(key, 默认值) → 语言包补 key → 切换语言生效

本文件锁定：
    1. zh_CN / en_US 两个语言包的 tab.* key 必须一一对应
    2. 切换语言后 tr() 返回值确实变化
    3. TabManager 构造出来的欢迎页标题跟随语言（端到端）
"""
import pytest

from beeoffice.i18n import I18nManager, set_language, tr


@pytest.fixture(autouse=True)
def _restore_language():
    """用例结束后恢复原语言，避免污染其他测试。"""
    manager = I18nManager()
    original = manager.current_language
    yield
    set_language(original)


def test_tab_keys_exist_in_both_locales():
    manager = I18nManager()
    zh = manager._translations.get("zh_CN", {})
    en = manager._translations.get("en_US", {})

    keys = sorted(k for k in zh if k.startswith("tab."))
    assert keys, "zh_CN 语言包里没有 tab.* key"

    missing = [k for k in keys if k not in en]
    assert not missing, f"en_US 语言包缺少这些 key: {missing}"


def test_tr_switches_between_languages():
    set_language("zh_CN")
    assert tr("tab.close") == "关闭标签"

    set_language("en_US")
    assert tr("tab.close") == "Close Tab"
    assert tr("tab.untitled") == "Untitled"


def test_tab_manager_uses_translation(qtbot):
    """端到端：构造 TabManager 时欢迎页标题应跟随当前语言。"""
    set_language("en_US")

    from beeoffice.tab_manager import TabManager

    tabs = TabManager()
    qtbot.addWidget(tabs)

    assert tabs.tabText(0) == "Start", (
        f"英文环境下欢迎页标题仍为 {tabs.tabText(0)!r}"
    )
