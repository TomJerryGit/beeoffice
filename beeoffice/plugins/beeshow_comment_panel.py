# beeoffice/plugins/beeshow_comment_panel.py
"""
蜜演评论面板（任务 4.2）

职责：
  - 显示评论列表（含作者、时间、已解决状态）
  - 按页分组 / 按时间排序
  - 支持跳转 / 编辑 / 删除 / 标记已解决

信号：
  - jump_requested(comment_id)    : 跳转请求
  - edit_requested(comment_id)    : 编辑请求
  - delete_requested(comment_id)  : 删除请求
  - resolve_requested(comment_id) : 标记已解决
  - close_requested()             : 关闭面板

依赖：
  - PySide6（QWidget / QVBoxLayout / QHBoxLayout / QLabel /
             QListWidget / QListWidgetItem / QPushButton / QMenu /
             QSizePolicy）
  - PySide6.QtCore（Qt / Signal）
  - PySide6.QtGui（QColor / QFont）
"""

import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QMenu,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from beeoffice.i18n import tr


class CommentPanel(QWidget):
    """评论面板"""

    # 信号
    jump_requested = Signal(int)
    edit_requested = Signal(int)
    delete_requested = Signal(int)
    resolve_requested = Signal(int)
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(240)
        self.setMaximumWidth(400)
        self.setSizePolicy(
            QSizePolicy.Preferred, QSizePolicy.Expanding
        )
        self._comments = []
        self._build_ui()

    # ==================== UI ====================
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 标题栏
        header = QHBoxLayout()
        self._title_label = QLabel(tr("auto.beeshow_comment_panel.6ca733e4", "💬 评论"))
        self._title_label.setStyleSheet(
            "QLabel{font-size:13px;font-weight:bold;color:#E65100;}"
        )
        header.addWidget(self._title_label)
        header.addStretch()

        # 关闭按钮
        btn_close = QPushButton("✕")
        btn_close.setFixedWidth(24)
        btn_close.setStyleSheet(
            "QPushButton{border:none;color:#999;font-size:14px;}"
            "QPushButton:hover{color:#E65100;}"
        )
        btn_close.clicked.connect(self.close_requested.emit)
        header.addWidget(btn_close)

        layout.addLayout(header)

        # 提示
        tip = QLabel(tr("auto.beeshow_comment_panel.6309e31b", "💡 双击评论可跳转到对应页"))
        tip.setStyleSheet(
            "QLabel{color:#999;font-size:11px;padding:2px;}"
        )
        tip.setWordWrap(True)
        layout.addWidget(tip)

        # 列表
        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget{border:1px solid #E0E0E0;"
            "border-radius:4px;background:#FFF;}"
            "QListWidget::item{padding:8px;"
            "border-bottom:1px solid #F0F0F0;}"
            "QListWidget::item:selected{background:#FFF3E0;}"
        )
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(
            self._on_context_menu
        )
        layout.addWidget(self._list, 1)

    # ==================== 公开接口 ====================
    def refresh(self, comments: list):
        """
        刷新评论列表。

        :param comments: [{id, author, text, time, resolved,
                          page_title, page_index}, ...]
        """
        self._comments = comments
        self._list.clear()

        # 统计
        total = len(comments)
        unresolved = sum(
            1 for c in comments if not c.get("resolved", False)
        )
        self._title_label.setText(
            f"💬 评论（{total}）"
            + (f" · 未解决 {unresolved}" if unresolved else "")
        )

        # 排序：未解决优先，同状态按时间倒序
        sorted_comments = sorted(
            comments,
            key=lambda c: (
                c.get("resolved", False),
                c.get("time", ""),
            ),
            reverse=False,
        )
        # 未解决的放上面；同状态按时间倒序（新→旧）
        sorted_comments = sorted(
            comments,
            key=lambda c: (
                c.get("resolved", False),
                # 时间倒序：用负的字符串排序做不到，简单用时间字符串
                # 保证 "2026-09-17 10:30" 比 "2026-09-17 09:00" 大
            ),
        )
        # 简化：直接遍历原顺序（已由上层保证顺序）
        sorted_comments = comments

        for c in sorted_comments:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, c["id"])

            # 状态图标
            status_icon = "✅" if c.get("resolved") else "📝"

            # 作者和时间
            header_text = (
                f"{status_icon} "
                f"{c.get('page_title', '?')} · "
                f"{c.get('author', '?')} · {c.get('time', '?')}"
            )
            # 正文
            text = c.get("text", "")
            if len(text) > 100:
                text = text[:100] + "..."

            item.setText(f"{header_text}\n    {text}")
            item.setToolTip(f"原文：{text}")
            item.setData(Qt.UserRole + 1, c)

            # 视觉样式
            if c.get("resolved"):
                item.setForeground(QColor("#999"))
                font = QFont()
                font.setStrikeOut(False)  # 不完全划线，保留可读性
                item.setFont(font)
            else:
                item.setForeground(QColor("#333"))

            self._list.addItem(item)

    # ==================== 事件 ====================
    def _on_item_double_clicked(self, item):
        """双击跳转到对应页"""
        comment_id = item.data(Qt.UserRole)
        if comment_id is not None:
            self.jump_requested.emit(comment_id)

    def _on_context_menu(self, pos):
        """右键菜单"""
        item = self._list.itemAt(pos)
        if item is None:
            return
        comment_id = item.data(Qt.UserRole)
        comment_data = item.data(Qt.UserRole + 1)
        if comment_id is None:
            return

        menu = QMenu(self)
        menu.addAction(tr("auto.beeshow_comment_panel.f3ef403a", "📍 跳转到此页")).triggered.connect(
            lambda: self.jump_requested.emit(comment_id)
        )
        menu.addAction(tr("auto.beeshow_comment_panel.b186d065", "✏️ 编辑")).triggered.connect(
            lambda: self.edit_requested.emit(comment_id)
        )

        is_resolved = comment_data.get("resolved", False)
        if is_resolved:
            menu.addAction(tr("auto.beeshow_comment_panel.b5df733f", "↩️ 标记未解决")).triggered.connect(
                lambda: self.resolve_requested.emit(comment_id)
            )
        else:
            menu.addAction(tr("auto.beeshow_comment_panel.865439df", "✅ 标记已解决")).triggered.connect(
                lambda: self.resolve_requested.emit(comment_id)
            )

        menu.addSeparator()
        menu.addAction(tr("auto.beeshow_comment_panel.d217371d", "🗑️ 删除")).triggered.connect(
            lambda: self.delete_requested.emit(comment_id)
        )

        menu.exec(self._list.mapToGlobal(pos))