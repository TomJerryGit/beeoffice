# beeoffice/plugins/ribbon_widget.py
"""
WPS 式 Ribbon 标签栏（2026-10-23）。

现有插件工具栏是"平铺多行按钮"；本控件把已有行布局（QHBoxLayout）挂到
"开始 / 插入 / 数据 / 视图"等标签页下，切换标签只显示对应页，视觉与
WPS 的标签式功能区一致，且不复制按钮、不改变任何命令逻辑。

用法：
    ribbon = RibbonBar()
    page = ribbon.add_tab("开始")
    page.addLayout(existing_hbox_layout)   # 布局会从旧父布局移入
    ...
    layout.addWidget(ribbon)
"""
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QToolButton,
    QTabBar,
    QVBoxLayout,
    QWidget,
)


class RibbonGroup(QFrame):
    """Ribbon 分组框：内容在上、组名在下的 WPS/Office 样式。"""

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("RibbonGroup")
        self.setStyleSheet(
            "QFrame#RibbonGroup{border-right:1px solid #E3E3E3;}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 6, 1)
        layout.setSpacing(0)
        self.content = QHBoxLayout()
        self.content.setContentsMargins(0, 0, 0, 0)
        self.content.setSpacing(3)
        layout.addLayout(self.content, 1)
        self._title = QLabel(title or "")
        self._title.setAlignment(Qt.AlignCenter)
        self._title.setStyleSheet("color:#777;font-size:10px;padding-top:1px;")
        layout.addWidget(self._title)

    def apply_theme(self):
        """按当前全局主题刷新分组框颜色。"""
        try:
            from beeoffice.theme import Theme
            dark = Theme.is_dark()
        except Exception:  # noqa: BLE001
            dark = False
        border = "#444" if dark else "#E3E3E3"
        title = "#AAA" if dark else "#777"
        self.setStyleSheet(
            "QFrame#RibbonGroup{border-right:1px solid " + border + ";}"
        )
        self._title.setStyleSheet(
            "color:" + title + ";font-size:10px;padding-top:1px;"
        )

    def add_large_button(self, text: str, tooltip: str, callback, icon=None):
        """WPS 式大按钮（图标在上、文字在下）。"""
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tooltip)
        button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        if icon is not None:
            button.setIcon(icon)
            button.setIconSize(QSize(22, 22))
        button.setMinimumSize(56, 46)
        button.setStyleSheet(
            "QToolButton{border:none;border-radius:4px;padding:2px;"
            "font-size:12px;color:#333;}"
            "QToolButton:hover{background:#E8F0FE;}"
        )
        button.clicked.connect(callback)
        self.content.addWidget(button)
        return button

    def add_layout(self, layout):
        self.content.addLayout(layout)

    def add_widget(self, widget):
        self.content.addWidget(widget)


class RibbonBar(QWidget):
    """标签式功能区：QTabBar + 每标签一页水平分组布局。"""

    STYLE = """
    QTabBar::tab {
        background: #F5F5F5; color: #444; padding: 5px 16px;
        border: 1px solid #E3E3E3; border-bottom: none;
        border-top-left-radius: 4px; border-top-right-radius: 4px;
        margin-right: 1px; font-size: 12px;
    }
    QTabBar::tab:selected {
        background: #FFFFFF; color: #1A73E8; font-weight: bold;
        border-bottom: 2px solid #1A73E8;
    }
    QTabBar::tab:hover { background: #EAF2FD; }
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("RibbonBar")
        self._tabs = QTabBar()
        self._tabs.setExpanding(False)
        self._tabs.setDrawBase(False)
        self._tabs.setStyleSheet(self.STYLE)
        self._stack = QStackedWidget()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        # 快速访问栏（保存/撤销等）在标签栏上方，WPS 式
        quick_row = QHBoxLayout()
        quick_row.setContentsMargins(4, 1, 4, 0)
        quick_row.setSpacing(2)
        self._quick_layout = QHBoxLayout()
        self._quick_layout.setContentsMargins(0, 0, 0, 0)
        self._quick_layout.setSpacing(2)
        quick_row.addLayout(self._quick_layout)
        quick_row.addStretch()
        layout.addLayout(quick_row)
        layout.addWidget(self._tabs)
        layout.addWidget(self._stack, 1)
        self._tabs.currentChanged.connect(self._stack.setCurrentIndex)
        self.apply_theme()

    def apply_theme(self):
        """按当前全局主题刷新标签/快速访问栏/分组（浅色/深色 + 强调色）。"""
        try:
            from beeoffice.theme import Theme
            dark = Theme.is_dark()
            accent = Theme.get_accent_color("primary")
            light = Theme.get_accent_color("light")
            dark_a = Theme.get_accent_color("dark")
        except Exception:  # noqa: BLE001
            dark, accent, light, dark_a = False, "#2196F3", "#E3F2FD", "#0D47A1"
        bg = "#2D2D2D" if dark else "#F5F5F5"
        fg = "#CCC" if dark else "#444"
        page_bg = "#252525" if dark else "#FFFFFF"
        tab_bg = "#333" if dark else "#F5F5F5"
        tab_sel_bg = "#FFFFFF" if dark else "#FFFFFF"
        tab_sel_fg = accent if not dark else "#FFFFFF"
        border = "#3D3D3D" if dark else "#E3E3E3"
        self._tabs.setStyleSheet(f"""
            QTabBar::tab {{
                background: {tab_bg}; color: {fg}; padding: 5px 16px;
                border: 1px solid {border}; border-bottom: none;
                border-top-left-radius: 4px; border-top-right-radius: 4px;
                margin-right: 1px; font-size: 12px;
            }}
            QTabBar::tab:selected {{
                background: {tab_sel_bg}; color: {tab_sel_fg};
                font-weight: bold; border-bottom: 2px solid {accent};
            }}
            QTabBar::tab:hover {{ background: {light if not dark else '#444'}; }}
        """)
        self._stack.setStyleSheet(f"QStackedWidget{{background:{page_bg};}}")
        for button in self._quick_layout.findChildren(QToolButton) if hasattr(self, "_quick_layout") else []:
            button.setStyleSheet(
                "QToolButton{border:none;border-radius:3px;font-size:13px;"
                f"color:{fg};}}"
                f"QToolButton:hover{{background:{light if not dark else '#444'};}}"
            )
        for group in self.findChildren(RibbonGroup):
            group.apply_theme()

    def add_tab(self, title: str) -> QHBoxLayout:
        page = QWidget()
        page_layout = QHBoxLayout(page)
        page_layout.setContentsMargins(4, 2, 4, 2)
        page_layout.setSpacing(4)
        page_layout.addStretch()
        self._stack.addWidget(page)
        index = self._tabs.addTab(title)
        if index == 0:
            self._tabs.setCurrentIndex(0)
        return page_layout

    def add_group(self, page_layout: QHBoxLayout, title: str = "") -> RibbonGroup:
        """在标签页里追加一个 Ribbon 分组框。"""
        group = RibbonGroup(title, page_layout.parentWidget())
        page_layout.insertWidget(max(0, page_layout.count() - 1), group)
        return group

    def add_quick_action(self, text: str, tooltip: str, callback):
        """快速访问栏按钮（WPS 标题栏下的小图标按钮）。"""
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tooltip)
        button.setAutoRaise(True)
        button.setFixedSize(24, 22)
        button.setStyleSheet(
            "QToolButton{border:none;border-radius:3px;font-size:13px;}"
            "QToolButton:hover{background:#E8F0FE;}"
        )
        button.clicked.connect(callback)
        self._quick_layout.addWidget(button)
        return button

    def tab_names(self):
        return [self._tabs.tabText(i) for i in range(self._tabs.count())]

    def set_current_tab(self, index: int):
        self._tabs.setCurrentIndex(index)

    def current_index(self) -> int:
        return self._tabs.currentIndex()
