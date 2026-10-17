# -*- coding: utf-8 -*-
"""
插件市场：内置插件保护（P0 数据安全）

背景：
    插件市场把用户插件直接复制进 `beeoffice/plugins/`，与内置插件混在同一目录。
    原实现的 `_uninstall_plugin` 会无条件 `file_path.unlink()`——
    用户点一次"卸载 蜜写"，`beewrite_plugin.py` 就从源码目录消失了。

修复：安装时写入一行标记，卸载时只删除带标记的文件；
      内置插件只能"禁用"，不能删除。
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def market():
    pytest.importorskip("PySide6.QtWidgets")
    from beeoffice.plugins.plugin_market import PluginMarketDialog
    return PluginMarketDialog


@pytest.mark.parametrize("rel", [
    "beeoffice/plugins/beewrite_plugin.py",
    "beeoffice/plugins/beesheet_plugin.py",
    "beeoffice/plugins/beeshow_plugin.py",
    "beeoffice/plugins/pdf_annotator_plugin.py",
])
def test_builtin_plugins_are_protected(market, rel):
    """仓库自带的插件不应被识别为"用户安装"。"""
    path = ROOT / rel
    if not path.exists():
        pytest.skip(f"文件不存在: {rel}")
    assert market._is_user_installed(path) is False, (
        f"{rel} 被误判为用户插件，卸载时会删除源文件"
    )


def test_install_file_writes_marker_and_keeps_content(market, tmp_path):
    """安装时必须打标记，且不能损坏原文件内容。"""
    src = tmp_path / "my_plugin.py"
    src.write_text(
        "from beeoffice.plugin_base import Plugin\n"
        "class MyPlugin(Plugin):\n"
        "    name = 'demo'\n",
        encoding="utf-8",
    )
    dest = tmp_path / "installed.py"

    market._install_file(src, dest)

    assert dest.exists()
    assert market._is_user_installed(dest) is True
    text = dest.read_text(encoding="utf-8")
    assert "class MyPlugin(Plugin):" in text
    # 标记必须写在最前面，否则 _is_user_installed 读不到
    assert text.lstrip("\ufeff").startswith(
        market._USER_PLUGIN_MARKER
    )


def test_install_file_is_idempotent(market, tmp_path):
    """重复安装同一个文件不应叠加多行标记。"""
    src = tmp_path / "p.py"
    src.write_text("x = 1\n", encoding="utf-8")
    dest = tmp_path / "p_installed.py"

    market._install_file(src, dest)
    market._install_file(dest, tmp_path / "p_installed2.py")

    text = (tmp_path / "p_installed2.py").read_text(encoding="utf-8")
    assert text.count(market._USER_PLUGIN_MARKER) == 1
