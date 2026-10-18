# -*- coding: utf-8 -*-
"""
插件发现：冻结环境必须能加载插件（发布阻塞级）

真实故障（5.2.0 打包验收时发现）：
    打包版的日志里写着「插件目录不存在」→「共加载 0 个插件」。
    因为 PyInstaller 把模块放进 PYZ 归档，磁盘上没有
    `beeoffice/plugins/` 目录，目录扫描必然空转。

    后果：界面还在，但蜜写 / 蜜算 / 蜜演 / PDF 批注四个模块全部消失，
    点新建什么都不会发生——而启动日志一切"正常"。

修复：
    目录不可用时回退到内置插件清单。
"""
import pytest

pytest.importorskip("PySide6.QtWidgets")


def _manager():
    from beeoffice.plugin_manager import PluginManager

    return PluginManager.__new__(PluginManager)


def test_frozen_fallback_returns_builtin_list(tmp_path):
    """目录不存在（模拟冻结环境）时必须回退到内置清单。"""
    from beeoffice.plugin_manager import PluginManager

    missing = tmp_path / "no_such_plugins"
    names = _manager()._collect_plugin_module_names(missing)
    assert names == list(PluginManager.BUILTIN_PLUGIN_MODULES)
    assert len(names) >= 4


def test_builtin_list_matches_real_plugin_files():
    """
    内置清单必须与磁盘上的 *_plugin.py 完全一致。

    这条是防"漂移"的：新增插件却忘了同步常量，
    打包版会静默少一个模块，而源码模式完全正常——最难查的一类问题。
    """
    import beeoffice.plugins as plugins_pkg
    from pathlib import Path

    from beeoffice.plugin_manager import PluginManager

    plugins_dir = Path(plugins_pkg.__file__).parent
    actual = {p.stem for p in plugins_dir.glob("*_plugin.py")}
    assert actual, "没有找到任何 *_plugin.py，测试环境异常"
    assert set(PluginManager.BUILTIN_PLUGIN_MODULES) == actual, (
        f"内置插件清单与实际文件不一致："
        f"清单多出 {set(PluginManager.BUILTIN_PLUGIN_MODULES) - actual}，"
        f"漏掉 {actual - set(PluginManager.BUILTIN_PLUGIN_MODULES)}"
    )


def test_normal_directory_scan_returns_plugins(tmp_path):
    """正常目录仍走扫描逻辑（这里用一个临时目录模拟）。"""
    from beeoffice.plugin_manager import PluginManager

    (tmp_path / "demo_plugin.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "helper.py").write_text("y = 2\n", encoding="utf-8")

    names = _manager()._collect_plugin_module_names(tmp_path)
    assert names == ["demo_plugin"], f"扫描结果异常: {names}"


def test_optional_dependency_filters_beeshow(tmp_path, monkeypatch):
    """
    精简版不含 WebEngine 时，蜜演插件必须被跳过。

    否则会出现更糟的情况：菜单里有"新建演示"，点下去才报 ImportError。
    """
    import importlib

    real_import = importlib.import_module

    def fake_import(name, *a, **k):
        if "QtWebEngine" in name:
            raise ImportError("no webengine")
        return real_import(name, *a, **k)

    monkeypatch.setattr(importlib, "import_module", fake_import)

    names = _manager()._collect_plugin_module_names(tmp_path / "missing")
    assert "beeshow_plugin" not in names, "缺 WebEngine 时蜜演不应注册"
    assert len(names) == 3, f"期望 3 个插件，实际 {names}"


def test_full_deps_keeps_all_four(tmp_path):
    names = _manager()._collect_plugin_module_names(tmp_path / "missing")
    assert len(names) == 4
