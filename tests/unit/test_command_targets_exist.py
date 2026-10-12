# tests/unit/test_command_targets_exist.py
"""
静态契约回归：菜单与插件命令引用的目标方法必须存在。

背景（优化规划「先删后补」）
---------------------------
删除假功能入口时，很容易只删掉方法定义、却漏掉菜单项或插件命令注册里的
引用。这类问题的表现是：

  * 菜单里点了没反应（`AttributeError` 被槽函数吞掉），或
  * 更隐蔽：`build_command_palette` 对每个插件单独 try/except，
    某个插件注册命令时抛 AttributeError → **该插件后面所有命令都注册不上**，
    但只在日志里留一行 ERROR。

本次实际发生过：删掉 `BeeWritePlugin.export_html` 后，
`register_commands` 里仍引用它，导致蜜写插件的命令注册整体失败。

本文件用源码扫描把这类引用变成自动检查，无需启动 GUI。
"""
import inspect
import re

import pytest

from beeoffice.app import BeeApp
from beeoffice.plugins.beewrite_plugin import BeeWritePlugin
from beeoffice.plugins.beesheet_plugin import BeeSheetPlugin
from beeoffice.plugins.beeshow_plugin import BeeShowPlugin
from beeoffice.plugins.pdf_annotator_plugin import PDFAnnotatorPlugin


PLUGIN_CLASSES = [
    BeeWritePlugin,
    BeeSheetPlugin,
    BeeShowPlugin,
    PDFAnnotatorPlugin,
]

# 这些是 Plugin.__init__ 里设置的实例属性，不是类属性
INSTANCE_ATTRS = {"parent", "widget", "_enabled"}


def _referenced_self_attrs(func):
    """取出一个方法体里出现的 self.<name> 名字。"""
    src = inspect.getsource(func)
    return set(re.findall(r"self\.(\w+)", src))


def test_menu_actions_reference_existing_app_methods():
    """
    menus.py 里所有 `main_window._xxx` 都必须是 BeeApp 上真实存在的方法。

    删方法却漏删菜单项时，这里会立刻失败（否则要等到用户点菜单才发现）。
    """
    from beeoffice import menus

    src = inspect.getsource(menus.setup_menus)
    names = set(re.findall(r"main_window\.(_\w+)", src))
    assert names, "未从 setup_menus 源码中解析到任何 main_window._xxx 引用"

    missing = sorted(n for n in names if not hasattr(BeeApp, n))
    assert not missing, (
        f"menus.py 引用了 BeeApp 上不存在的方法: {missing}"
    )


@pytest.mark.parametrize(
    "plugin_cls", PLUGIN_CLASSES, ids=lambda c: c.__name__
)
def test_plugin_commands_reference_existing_methods(plugin_cls):
    """
    插件的 register_commands 里所有 `self._xxx` 都必须是该类真实存在的方法。

    这类引用一旦失效，会让**整个插件**的命令注册中断（异常被
    commands.build_command_palette 捕获，只在日志里留一行 ERROR）。
    """
    method = getattr(plugin_cls, "register_commands", None)
    if method is None:
        pytest.skip(f"{plugin_cls.__name__} 未实现 register_commands")

    missing = sorted(
        name
        for name in _referenced_self_attrs(method)
        if name not in INSTANCE_ATTRS and not hasattr(plugin_cls, name)
    )
    assert not missing, (
        f"{plugin_cls.__name__}.register_commands 引用了不存在的方法: {missing}"
    )


def test_plugin_register_menus_references_exist():
    """register_menus 同理。"""
    for plugin_cls in PLUGIN_CLASSES:
        method = getattr(plugin_cls, "register_menus", None)
        if method is None:
            continue
        missing = sorted(
            name
            for name in _referenced_self_attrs(method)
            if name not in INSTANCE_ATTRS and not hasattr(plugin_cls, name)
        )
        assert not missing, (
            f"{plugin_cls.__name__}.register_menus 引用了不存在的方法: {missing}"
        )


# ==================== 被删入口确实不再存在 ====================

REMOVED_APP_ENTRIES = ["_play_macro", "_toggle_macro"]

REMOVED_BEESHEET_ENTRIES = [
    "_show_freeze_menu", "_freeze_row", "_freeze_column",
    "_freeze_cell", "_unfreeze_all",
]

REMOVED_BEEWRITE_ENTRIES = ["_insert_header", "_insert_footer"]


@pytest.mark.parametrize("name", REMOVED_APP_ENTRIES)
def test_removed_app_entries_are_gone(name):
    assert not hasattr(BeeApp, name), (
        f"{name} 属于已删除的假功能入口，不应再出现（优化规划「先删后补」）"
    )


@pytest.mark.parametrize("name", REMOVED_BEESHEET_ENTRIES)
def test_removed_freezepane_entries_are_gone(name):
    """冻结窗格是假实现（只改表头 resize 模式，无滚动冻结效果），已删除。"""
    from beeoffice.plugins.beesheet import BeeSheetView

    assert not hasattr(BeeSheetView, name)


@pytest.mark.parametrize("name", REMOVED_BEEWRITE_ENTRIES)
def test_removed_header_footer_entries_are_gone(name):
    """页眉/页脚此前只是把 HTML 注释当正文写入，无任何消费者，已删除。"""
    from beeoffice.plugins.beewrite import BeeWriteEditor

    assert not hasattr(BeeWriteEditor, name)


def test_macro_entries_are_gone():
    """蜜算宏录制/播放是纯声明（view 上从来没有对应实现），已删除。"""
    from beeoffice.plugins.beesheet import BeeSheetView

    assert not hasattr(BeeSheetView, "_toggle_macro_recording")
    assert not hasattr(BeeSheetView, "_play_macro")
    assert not hasattr(BeeSheetPlugin, "toggle_macro_recording")
    assert not hasattr(BeeSheetPlugin, "play_macro")


def test_laser_and_brush_stubs_are_gone():
    """
    激光笔/画笔全为桩（全仓无 mouseMoveEvent/mousePressEvent），
    对应的 L / P 按键处理与状态已删除。
    """
    from beeoffice.plugins import beeshow_play_mixin as play_mixin

    src = inspect.getsource(play_mixin)
    # 用词边界，避免把 Qt.Key_PageDown / Key_PageUp 误判成 Key_P
    assert not re.search(r"\bQt\.Key_L\b", src), "激光笔按键处理应已删除"
    assert not re.search(r"\bQt\.Key_P\b", src), "画笔按键处理应已删除"
    assert "_laser_active" not in src
    assert "_drawing_active" not in src
    assert "getElementById('laser')" not in src


# ==================== 「补」的落点：已接线，不再是死入口 ====================

def test_html_export_is_now_wired_up():
    """
    阶段 1 按「先删后补」删掉了不可达的「导出 HTML」入口；
    阶段 2（§2.6）补齐了实现并把入口接回（编辑器 / 主窗口 / 插件）。
    """
    from beeoffice.app import BeeApp
    from beeoffice.plugins.beewrite import BeeWriteEditor
    from beeoffice.plugins.beewrite_plugin import BeeWritePlugin
    from beeoffice.plugins.bee_export import export_to_html

    # 底层实现（一直存在）
    assert callable(export_to_html)
    # 编辑器上的实现
    assert hasattr(BeeWriteEditor, "export_html"), (
        "BeeWriteEditor 应实现 export_html"
    )
    # 主窗口转发
    assert hasattr(BeeApp, "_export_html"), "BeeApp 应提供 _export_html 转发"
    # 插件壳转发
    assert hasattr(BeeWritePlugin, "export_html")
