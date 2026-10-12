# tests/regression/v5/test_v505_html_export_wiring.py
"""
优化规划 §2.6「补」回归：蜜写「导出 HTML」从死入口变成可用功能。

背景
----
阶段 1 按「先删后补」删掉了这个入口，因为它当时不可达：
`app._export_html` 取 `hasattr(widget, "export_html")`，而 `BeeWriteEditor`
**没有** `export_html`，所以菜单点了静默无动作。

底层实现 `bee_export.export_to_html` 一直存在且有测试覆盖
（tests/unit/test_bee_export.py），缺的只是编辑器上的薄封装 + 入口接线。

本文件断言：
  1. 真正导出会产出文件，且内容是被渲染过的 HTML；
  2. 文件名后缀会被补齐为 .html；
  3. 渲染失败时不产出文件且给出提示（不假报成功）；
  4. 菜单 / 命令面板 / 插件 / 主窗口四个入口都接上了。
"""
import inspect

import pytest
from PySide6.QtWidgets import QMessageBox


@pytest.fixture(autouse=True)
def _no_modal(monkeypatch):
    """headless 下把提示框换成记录器。"""
    shown = []

    def _record(*args, **kwargs):
        shown.append(args)
        return QMessageBox.Ok

    for name in ("warning", "information", "critical"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(_record))
    return shown


def _patch_save_dialog(monkeypatch, target_path):
    monkeypatch.setattr(
        "beeoffice.plugins.beewrite_export_mixin.QFileDialog.getSaveFileName",
        lambda *a, **k: (str(target_path), "HTML (*.html)"),
    )


def test_export_html_writes_rendered_file(beewrite_editor, tmp_path, monkeypatch):
    """导出应产出文件，且内容含渲染后的 HTML 结构。"""
    out = tmp_path / "doc.html"
    _patch_save_dialog(monkeypatch, out)
    beewrite_editor.set_content("# 标题\n\n正文内容\n")

    beewrite_editor.export_html()

    assert out.exists(), "应产出 HTML 文件"
    text = out.read_text(encoding="utf-8")
    assert "<html" in text.lower(), "应是完整 HTML 文档"
    assert "标题" in text and "正文内容" in text


def test_export_html_appends_suffix(beewrite_editor, tmp_path, monkeypatch):
    """用户没写后缀时应自动补 .html。"""
    target = tmp_path / "no_suffix"
    _patch_save_dialog(monkeypatch, target)
    beewrite_editor.set_content("内容")

    beewrite_editor.export_html()

    assert (tmp_path / "no_suffix.html").exists(), (
        f"应补全后缀，实际目录内容: {[p.name for p in tmp_path.iterdir()]}"
    )


def test_export_html_cancel_writes_nothing(beewrite_editor, tmp_path, monkeypatch):
    """用户取消时不应产出文件、也不应报错。"""
    monkeypatch.setattr(
        "beeoffice.plugins.beewrite_export_mixin.QFileDialog.getSaveFileName",
        lambda *a, **k: ("", ""),
    )
    beewrite_editor.export_html()
    assert list(tmp_path.glob("*.html")) == []


def test_export_html_failure_is_reported(beewrite_editor, tmp_path, monkeypatch):
    """底层返回 False 时必须告警，不能静默。"""
    shown = []
    monkeypatch.setattr(
        QMessageBox, "warning",
        staticmethod(lambda *a, **k: shown.append(a)),
    )
    monkeypatch.setattr(
        "beeoffice.plugins.bee_export.export_to_html",
        lambda content, path: False,
    )
    out = tmp_path / "fail.html"
    _patch_save_dialog(monkeypatch, out)

    beewrite_editor.export_html()

    assert shown, "导出失败必须提示用户"
    assert not out.exists()


# ==================== 四个入口都接上了 ====================

def test_all_entry_points_are_wired():
    from beeoffice.app import BeeApp
    from beeoffice.plugins.beewrite import BeeWriteEditor
    from beeoffice.plugins.beewrite_plugin import BeeWritePlugin

    assert hasattr(BeeWriteEditor, "export_html")
    assert hasattr(BeeApp, "_export_html")
    assert hasattr(BeeWritePlugin, "export_html")


def test_menu_contains_export_html_action():
    from beeoffice import menus

    src = inspect.getsource(menus.setup_menus)
    assert "_export_html" in src, "菜单里应有「导出 HTML」"
    assert "cmd.export_html" in src, "应使用既有 i18n key"


def test_command_palette_registers_export_html():
    from beeoffice import commands

    src = inspect.getsource(commands._register_builtin_commands)
    assert "_export_html" in src, "命令面板里应有「导出 HTML」"


def test_plugin_registers_export_html_command():
    from beeoffice.plugins.beewrite_plugin import BeeWritePlugin

    src = inspect.getsource(BeeWritePlugin.register_commands)
    assert "export_html" in src, "插件命令面板里应有「蜜写：导出 HTML」"
