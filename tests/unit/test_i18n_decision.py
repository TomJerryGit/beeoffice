# tests/unit/test_i18n_decision.py
"""
i18n 决策回归（2026-10-20，路线 B：**中文优先**）。

## 决策内容
* 不再提供语言切换入口（实测 `tr()` 包装率约 11%，切 en_US 会得到"半英文"界面）；
* 应用启动固定 `zh_CN`，旧配置里的 `language: en_US` 不再生效；
* `beeoffice/i18n.py`、`locales/*.json`、`tr()` **保留**，作为未来按模块 tr 化的基础；
* `tools/i18n_audit.py` 的 GUI 硬编码棘轮继续阻止新增债务。

## 本文件锁住
1. 菜单里没有语言子菜单、没有 `_switch_language` 调用；
2. 应用/入口固定 zh_CN（源码级断言，避免以后又"顺手"恢复半成品入口）；
3. 语言包和 tr 基础设施仍可用（将来 tr 化不需要推倒重来）。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_no_language_switcher_in_menus():
    source = _source("beeoffice/menus.py")
    assert "_build_language_menu" not in source, (
        "语言子菜单入口又回来了：i18n 决策是中文优先（路线 B）"
    )
    assert "_switch_language" not in source
    assert "menu.view.language" not in source


def test_app_and_entry_force_chinese():
    app = _source("beeoffice/app.py")
    main = _source("beeoffice/main.py")
    assert 'set_language("zh_CN")' in app
    assert 'set_language("zh_CN")' in main
    # 不再按 settings 里的旧值切换
    assert "set_language(self.settings.language)" not in app
    assert "set_language(settings.language)" not in main


def test_settings_ignores_legacy_language(tmp_path):
    """旧配置里的 en_US 不再生效（否则启动时又切到半成品英文）。"""
    from beeoffice.settings import AppSettings

    config = tmp_path / "settings.json"
    config.write_text(
        '{"version": 1, "language": "en_US", "theme": "light"}',
        encoding="utf-8",
    )
    settings = AppSettings(config)
    assert settings.language == "zh_CN"


def test_i18n_infrastructure_is_kept_for_future():
    """路线 B 不等于删掉 i18n：语言包与 tr() 仍在，未来 tr 化可直接用。"""
    from beeoffice.i18n import I18nManager, set_language, tr

    manager = I18nManager()
    assert "zh_CN" in manager._translations
    assert "en_US" in manager._translations          # 保留给未来，不对外提供入口
    assert set_language("en_US") is True             # 基础设施仍可切（测试/未来用）
    assert tr("app.title")                            # 能取到文案
    set_language("zh_CN")
