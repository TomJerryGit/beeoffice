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
from PySide6.QtWidgets import (
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)


class RibbonBar(QWidget):
    """标签式功能区：QTabBar + 每标签一页垂直布局。"""

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
        layout.addWidget(self._tabs)
        layout.addWidget(self._stack, 1)
        self._tabs.currentChanged.connect(self._stack.setCurrentIndex)

    def add_tab(self, title: str) -> QVBoxLayout:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(4, 2, 4, 2)
        page_layout.setSpacing(2)
        self._stack.addWidget(page)
        index = self._tabs.addTab(title)
        if index == 0:
            self._tabs.setCurrentIndex(0)
        return page_layout

    def tab_names(self):
        return [self._tabs.tabText(i) for i in range(self._tabs.count())]

    def set_current_tab(self, index: int):
        self._tabs.setCurrentIndex(index)

    def current_index(self) -> int:
        return self._tabs.currentIndex()
