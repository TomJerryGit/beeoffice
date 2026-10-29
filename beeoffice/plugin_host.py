# beeoffice/plugin_host.py
"""把插件 API v1 接到真实主窗口：Ribbon / TaskPane / 文档事务。"""
from __future__ import annotations

from contextlib import contextmanager

from PySide6.QtWidgets import QLabel


class PluginHost:
    """一个主窗口对应一个 Host；PluginContext 只依赖这里的方法。"""

    def __init__(self, main_window):
        self._window = main_window
        self._groups = {}

    # ---------- 当前编辑器 ----------
    def current_widget(self):
        try:
            return self._window.tab_manager.currentWidget()
        except Exception:  # noqa: BLE001
            return None

    def _ribbon(self):
        widget = self.current_widget()
        return getattr(widget, "_ribbon", None)

    def _text_editor(self):
        widget = self.current_widget()
        for attr in ("rich_editor", "markdown_editor", "text_edit", "editor"):
            editor = getattr(widget, attr, None)
            if editor is not None and hasattr(editor, "textCursor"):
                return editor
        return None

    # ---------- Ribbon ----------
    def add_ribbon_button(self, tab: str, group: str, text: str,
                          callback, icon: str = "") -> bool:
        ribbon = self._ribbon()
        if ribbon is None:
            return False
        titles = ribbon.tab_names()
        if tab in titles:
            index = titles.index(tab)
            page = ribbon._stack.widget(index)
        else:
            ribbon.add_tab(tab)
            index = ribbon._tabs.count() - 1
            page = ribbon._stack.widget(index)
        key = (id(ribbon), tab, group)
        grp = self._groups.get(key)
        if grp is None:
            grp = ribbon.add_group(page.layout(), group)
            self._groups[key] = grp
        grp.add_small_button(
            text, text, callback, icon_name=icon or None
        )
        return True

    # ---------- Task Pane ----------
    def show_task_pane(self, pane_id: str, title: str, side: str = "right",
                       widget=None):
        manager = getattr(self._window, "task_pane_manager", None)
        if manager is None:
            return None
        if callable(widget):
            widget = widget()
        if widget is None:
            widget = QLabel(title)
        return manager.show_pane(pane_id, title, widget)

    # ---------- Document ----------
    def read(self) -> str:
        editor = self._text_editor()
        return editor.toPlainText() if editor is not None else ""

    def selection_text(self) -> str:
        editor = self._text_editor()
        if editor is None:
            return ""
        return editor.textCursor().selectedText().replace("\u2029", "\n")

    def replace_selection(self, text: str):
        editor = self._text_editor()
        if editor is None:
            raise RuntimeError("当前编辑器不支持文字替换")
        cursor = editor.textCursor()
        cursor.insertText(text)
        editor.setTextCursor(cursor)

    @contextmanager
    def transaction(self, label: str = ""):
        """Writer 一个 undo 步骤；没有光标时也保持上下文语义。"""
        editor = self._text_editor()
        if editor is None:
            yield
            return
        cursor = editor.textCursor()
        cursor.beginEditBlock()
        try:
            yield
        finally:
            cursor.endEditBlock()
            try:
                editor.setTextCursor(cursor)
            except Exception:  # noqa: BLE001
                pass

    # 兼容 DocumentAPI 的命名
    def transaction_context(self, label: str = ""):
        return self.transaction(label)
