# beeoffice/plugins/beewrite_nav_panel.py
"""蜜写统一导航面板：目录 / 章节 / 书签 / 查找替换。"""
from __future__ import annotations

import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from beeoffice.i18n import tr
from beeoffice.plugins.beewrite_outline import OutlinePanel


class NavigationPanel(QWidget):
    """WPS 式左侧导航栏；四个标签共用同一块侧栏宽度。"""

    jump_requested = Signal(int)
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BeeWriteNavPanel")
        self._editor = None
        self.setMinimumWidth(200)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        # 目录：复用原有 OutlinePanel
        self.outline = OutlinePanel()
        self.outline.jump_requested.connect(self.jump_requested)
        self.outline.close_requested.connect(self.close_requested)
        self.tabs.addTab(self.outline, tr("beewrite.nav.toc", "目录"))

        # 章节：扁平标题列表
        self.chapter_list = QListWidget()
        self.chapter_list.itemClicked.connect(self._on_item_clicked)
        self.tabs.addTab(self.chapter_list, tr("beewrite.nav.chapters", "章节"))

        # 书签
        self.bookmark_list = QListWidget()
        self.bookmark_list.itemClicked.connect(self._on_item_clicked)
        self.tabs.addTab(self.bookmark_list, tr("beewrite.nav.bookmarks", "书签"))

        # 查找替换：由 BeeWrite 注入 FindReplaceBar
        self.find_host = QWidget()
        self._find_layout = QVBoxLayout(self.find_host)
        self._find_layout.setContentsMargins(4, 4, 4, 4)
        self.tabs.addTab(self.find_host, tr("beewrite.nav.find", "查找替换"))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------
    def apply_theme(self):
        """高对比度：刷新导航面板与内嵌大纲/查找栏。"""
        try:
            from beeoffice.theme import Theme
            high = Theme.is_high_contrast()
        except Exception:
            high = False
        if high:
            self.tabs.setStyleSheet(
                "QTabWidget::pane{background:#000000;border:2px solid #FFFFFF;}"
                "QTabBar::tab{background:#000000;color:#FFFFFF;"
                "border:1px solid #FFFFFF;padding:6px 10px;}"
                "QTabBar::tab:selected{background:#FFD600;color:#000000;}"
                "QListWidget{background:#000000;color:#FFFFFF;"
                "border:2px solid #FFFFFF;}"
                "QListWidget::item:selected{background:#FFD600;color:#000000;}"
            )
        if hasattr(self, "outline"):
            self.outline.apply_theme()

    def attach_find_bar(self, bar):
        self._find_layout.addWidget(bar)

    def show_find_tab(self):
        self.tabs.setCurrentIndex(3)

    def set_editor(self, editor):
        self._editor = editor
        self.outline.set_editor(editor)
        self._refresh_chapters()

    def set_bookmarks(self, bookmarks: dict):
        self.bookmark_list.clear()
        for name, data in sorted((bookmarks or {}).items()):
            pos = int(data.get("pos", 0))
            item = QListWidgetItem(f"🔖 {name}")
            item.setData(Qt.UserRole, pos)
            item.setToolTip(data.get("time", ""))
            self.bookmark_list.addItem(item)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _refresh_chapters(self):
        self.chapter_list.clear()
        editor = self._editor
        if editor is None:
            return
        try:
            doc = editor.document()
            block = doc.begin()
            while block.isValid():
                level = block.blockFormat().headingLevel()
                text = block.text().strip()
                if level > 0 and text:
                    item = QListWidgetItem("  " * (level - 1) + text)
                    item.setData(Qt.UserRole, block.position())
                    self.chapter_list.addItem(item)
                block = block.next()
            if self.chapter_list.count():
                return

            # Markdown 源码模式：解析 # 标题，位置按行首 offset
            plain = editor.toPlainText()
            offset = 0
            for line in plain.splitlines(True):
                m = re.match(r"^(#{1,6})\s+(.+?)\s*$", line.rstrip("\n"))
                if m:
                    level = len(m.group(1))
                    item = QListWidgetItem("  " * (level - 1) + m.group(2))
                    item.setData(Qt.UserRole, offset)
                    self.chapter_list.addItem(item)
                offset += len(line)
        except Exception:
            pass

    def _on_item_clicked(self, item):
        pos = item.data(Qt.UserRole)
        if pos is not None:
            self.jump_requested.emit(int(pos))
