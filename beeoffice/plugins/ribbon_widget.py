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
        # 阶段 4：组内多行——WPS 的一个组可以有多行小按钮
        self._rows_layout = QVBoxLayout()
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(2)
        layout.addLayout(self._rows_layout, 1)
        self._rows = []
        self.content = self.add_row()
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

    def add_large_button(self, text: str, tooltip: str, callback, icon=None, icon_name=None):
        """WPS 式大按钮（图标在上、文字在下）。"""
        button = QToolButton()
        # 大按钮文字只保留最后一行中文；前面的 emoji 交给统一图标，
        # 避免缺 emoji 字体时出现空方块。
        button.setText(text.split("\n")[-1] if "\n" in text else text)
        button.setToolTip(tooltip)
        button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        if icon_name:
            try:
                from beeoffice.plugins.ribbon_icons import make_icon
                button.setIcon(make_icon(icon_name))
                button.setIconSize(QSize(22, 22))
                button.setProperty("ribbonIcon", icon_name)
            except Exception:  # noqa: BLE001
                pass
        elif icon is not None:
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

    def add_row(self) -> QHBoxLayout:
        """新增一行内容；大按钮/小按钮会追加到当前行。"""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(3)
        self._rows.append(row)
        self._rows_layout.addLayout(row)
        self.content = row
        return row

    def add_small_button(self, text: str, tooltip: str, callback,
                         icon_name=None):
        """WPS 式小按钮（图标在左、文字在右），用于组内第二行。"""
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tooltip)
        button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        if icon_name:
            try:
                from beeoffice.plugins.ribbon_icons import make_icon
                button.setIcon(make_icon(icon_name))
                button.setIconSize(QSize(16, 16))
                button.setProperty("ribbonIcon", icon_name)
            except Exception:  # noqa: BLE001
                pass
        try:
            from beeoffice.theme import Theme
            color = Theme.tokens()["text"]
            hover = Theme.tokens()["accent_light"]
        except Exception:  # noqa: BLE001
            color, hover = "#333333", "#E8F0FE"
        button.setStyleSheet(
            "QToolButton{border:none;border-radius:3px;padding:2px 5px;"
            f"font-size:11px;color:{color};}}"
            f"QToolButton:hover{{background:{hover};}}"
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
        self._collapse_button = QToolButton()
        self._collapse_button.setText("⌃")
        self._collapse_button.setToolTip("折叠/展开功能区")
        self._collapse_button.setAutoRaise(True)
        self._collapse_button.setFixedSize(22, 20)
        self._collapse_button.clicked.connect(self.toggle_collapse)
        quick_row.addWidget(self._collapse_button)
        layout.addLayout(quick_row)
        self._file_button = None
        layout.addWidget(self._tabs)
        layout.addWidget(self._stack, 1)
        self._tabs.currentChanged.connect(self._stack.setCurrentIndex)
        self.apply_theme()

    def attach_file_menu(self, menu):
        """WPS 顶栏：快速访问栏左侧的「文件」入口（复用主菜单）。"""
        if menu is None:
            return
        if self._file_button is None:
            self._file_button = QToolButton()
            self._file_button.setText("文件")
            self._file_button.setPopupMode(QToolButton.InstantPopup)
            self._file_button.setAutoRaise(True)
            self._file_button.setStyleSheet(
                "QToolButton{border:none;padding:2px 10px;font-size:13px;"
                "font-weight:bold;}"
                "QToolButton:hover{background:#E8F0FE;border-radius:3px;}"
            )
            self._quick_layout.addWidget(self._file_button)
        self._file_button.setMenu(menu)

    def toggle_collapse(self):
        collapsed = self._stack.isVisible()
        self._stack.setVisible(not collapsed)
        self._collapse_button.setText("⌄" if collapsed else "⌃")
        self._collapse_button.setToolTip(
            "展开功能区" if collapsed else "折叠功能区"
        )

    def add_context_tab(self, title: str) -> QHBoxLayout:
        """新增默认隐藏的上下文标签页（选中表格/图片时显示）。"""
        page = self.add_tab(title)
        idx = self._tabs.count() - 1
        self._tabs.setTabVisible(idx, False)
        return page

    def set_context_tab_visible(self, title: str, visible: bool):
        for i in range(self._tabs.count()):
            if self._tabs.tabText(i) == title:
                self._tabs.setTabVisible(i, visible)
                if not visible and self._tabs.currentIndex() == i:
                    for j in range(self._tabs.count()):
                        if self._tabs.isTabVisible(j):
                            self._tabs.setCurrentIndex(j)
                            break
                return

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
        for button in self.findChildren(QToolButton):
            name = button.property("ribbonIcon")
            if name:
                try:
                    from beeoffice.plugins.ribbon_icons import make_icon
                    button.setIcon(make_icon(str(name)))
                except Exception:  # noqa: BLE001
                    pass
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

    def add_quick_action(self, text: str, tooltip: str, callback, icon_name=None):
        """快速访问栏按钮（WPS 标题栏下的小图标按钮）。"""
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tooltip)
        button.setAutoRaise(True)
        button.setFixedSize(24, 22)
        if icon_name:
            try:
                from beeoffice.plugins.ribbon_icons import make_icon
                button.setText("")
                button.setIcon(make_icon(icon_name))
                button.setIconSize(QSize(16, 16))
                button.setProperty("ribbonIcon", icon_name)
            except Exception:  # noqa: BLE001
                pass
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
