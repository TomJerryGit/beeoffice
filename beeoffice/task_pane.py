# beeoffice/task_pane.py
"""任务窗格外壳（S0 原型）。

WPS/Office 的任务窗格是插件、AI、动画、属性等功能的承载容器。
这里先提供最小可用壳：
- TaskPane：标题 + 关闭按钮 + 内容区（QFrame）；
- TaskPaneManager：基于 QMainWindow 的右侧 QDockWidget，支持显示/隐藏/关闭/主题。

S1 会把它接到 PluginContext.ui.add_task_pane()。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class TaskPane(QFrame):
    """任务窗格内容壳：标题栏 + 可替换内容。"""

    closed = Signal()

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("TaskPane")
        self._title = QLabel(title)
        self._title.setStyleSheet(
            "font-weight:bold;font-size:13px;padding:2px 4px;"
        )
        self._close_btn = QToolButton()
        self._close_btn.setText("×")
        self._close_btn.setToolTip("关闭任务窗格")
        self._close_btn.setAutoRaise(True)
        self._close_btn.setFixedSize(22, 22)
        self._close_btn.clicked.connect(self.closed.emit)

        header = QHBoxLayout()
        header.setContentsMargins(6, 4, 6, 2)
        header.addWidget(self._title, 1)
        header.addWidget(self._close_btn)

        self._content = QVBoxLayout()
        self._content.setContentsMargins(6, 4, 6, 6)
        self._content.setSpacing(4)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(header)
        layout.addLayout(self._content, 1)

    def set_title(self, title: str):
        self._title.setText(title or "")

    def set_content(self, widget: QWidget):
        while self._content.count():
            item = self._content.takeAt(0)
            old = item.widget()
            if old is not None:
                old.setParent(None)
        if widget is not None:
            self._content.addWidget(widget, 1)

    def apply_theme(self):
        try:
            from beeoffice.theme import Theme

            dark = Theme.is_dark()
            accent = Theme.get_accent_color("primary")
        except Exception:  # noqa: BLE001
            dark, accent = False, "#2196F3"
        bg = "#2D2D2D" if dark else "#FFFFFF"
        fg = "#DDDDDD" if dark else "#333333"
        border = "#444444" if dark else "#D0D0D0"
        self.setStyleSheet(
            "QFrame#TaskPane{"
            f"background:{bg};color:{fg};border-left:1px solid {border};"
            "}"
            f"QFrame#TaskPane QLabel{{color:{fg};}}"
        )
        self._title.setStyleSheet(
            f"font-weight:bold;font-size:13px;padding:2px 4px;color:{fg};"
            f"border-bottom:1px solid {border};"
        )
        self._close_btn.setStyleSheet(
            "QToolButton{border:none;border-radius:3px;font-size:15px;"
            f"color:{fg};}}"
            f"QToolButton:hover{{background:{accent};color:#FFFFFF;}}"
        )


class TaskPaneManager:
    """管理主窗口右侧的任务窗格（每个 pane_id 一个 QDockWidget）。"""

    def __init__(self, main_window: QMainWindow):
        self._window = main_window
        self._panes: dict[str, QDockWidget] = {}

    def show_pane(self, pane_id: str, title: str, content: QWidget):
        dock = self._panes.get(pane_id)
        if dock is None:
            dock = QDockWidget(title, self._window)
            dock.setObjectName(f"TaskPaneDock_{pane_id}")
            dock.setFeatures(
                QDockWidget.DockWidgetClosable
                | QDockWidget.DockWidgetMovable
                | QDockWidget.DockWidgetFloatable
            )
            dock.setAllowedAreas(
                Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea
            )
            # 用 TaskPane 自己的标题栏，去掉原生标题栏重复
            dock.setTitleBarWidget(QWidget(dock))
            pane = TaskPane(title, dock)
            pane.closed.connect(dock.close)
            dock.setWidget(pane)
            self._window.addDockWidget(Qt.RightDockWidgetArea, dock)
            self._panes[pane_id] = dock
        else:
            pane = dock.widget()
            pane.set_title(title)
        pane.set_content(content)
        pane.apply_theme()
        dock.show()
        dock.raise_()
        return dock

    def hide_pane(self, pane_id: str):
        dock = self._panes.get(pane_id)
        if dock is not None:
            dock.hide()

    def close_pane(self, pane_id: str):
        dock = self._panes.pop(pane_id, None)
        if dock is not None:
            dock.close()
            dock.deleteLater()

    def apply_theme(self):
        for dock in self._panes.values():
            pane = dock.widget()
            if isinstance(pane, TaskPane):
                pane.apply_theme()
