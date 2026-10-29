# tests/fidelity/test_plugin_host_2026_10_29.py
"""S1：PluginContext 真实接入 Ribbon / TaskPane / 文档事务。"""
from types import SimpleNamespace

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QTextEdit

from beeoffice.plugin_api import PluginContext, PluginManifest
from beeoffice.plugin_host import PluginHost
from beeoffice.plugins.ribbon_widget import RibbonBar


class _TaskManager:
    def __init__(self, widget):
        self._widget = widget

    def currentWidget(self):
        return self._widget


class _PaneManager:
    def __init__(self):
        self.shown = {}

    def show_pane(self, pane_id, title, widget):
        self.shown[pane_id] = (title, widget)
        return widget


def _context(qtbot):
    editor = QTextEdit()
    qtbot.addWidget(editor)
    editor.setPlainText("hello world")
    widget = SimpleNamespace(
        _ribbon=RibbonBar(), rich_editor=editor,
    )
    app = SimpleNamespace(
        tab_manager=_TaskManager(widget),
        task_pane_manager=_PaneManager(),
    )
    host = PluginHost(app)
    manifest = PluginManifest.from_dict({
        "id": "com.example.host",
        "name": "Host Demo",
        "version": "1.0.0",
        "api_version": "1",
        "entry": "plugin.py",
        "permissions": ["doc.read", "doc.write"],
    })
    ctx = PluginContext(manifest, "5.0.30", host=host)
    return ctx, host, editor, app


def test_ribbon_taskpane_and_document_transaction(qtbot):
    ctx, host, editor, app = _context(qtbot)

    ctx.commands.register("demo.run", lambda: None)
    ctx.ribbon.add_tab("插件")
    group = ctx.ribbon.add_group("插件", "演示")
    ctx.ribbon.add_button(group, "运行", command="demo.run")
    assert "插件" in host._ribbon().tab_names()

    ctx.ui.add_task_pane("demo", "演示面板", widget=QTextEdit())
    assert "demo" in app.task_pane_manager.shown
    assert app.task_pane_manager.shown["demo"][0] == "演示面板"

    assert ctx.doc.read().startswith("hello world")
    cursor = editor.textCursor()
    cursor.select(QTextCursor.WordUnderCursor)
    editor.setTextCursor(cursor)
    assert ctx.doc.selection_text()
    with ctx.doc.transaction("替换"):
        ctx.doc.replace_selection("HI")
    assert editor.toPlainText().startswith("HI")
