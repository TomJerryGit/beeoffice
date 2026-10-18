# beeoffice/plugins/beewrite_comment.py
"""
蜜写批注管理：批注数据、批注面板、增删改查
"""
import json
import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QTextEdit, QInputDialog,
    QMessageBox, QMenu, QDialog, QDialogButtonBox, QFormLayout,
    QLineEdit
)
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QColor, QFont
from beeoffice.i18n import tr


# ==================== 批注数据管理器 ====================
class CommentManager:
    """批注数据管理器"""

    def __init__(self):
        self._comments = []  # 列表，每条是 dict
        self._next_id = 1

    def add(self, text, anchor_start, anchor_end, excerpt="",
            author="当前用户"):
        """添加批注"""
        comment = {
            "id": self._next_id,
            "text": text,
            "author": author,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "anchor_start": anchor_start,
            "anchor_end": anchor_end,
            "excerpt": excerpt,
            "resolved": False,
        }
        self._comments.append(comment)
        self._next_id += 1
        return comment

    def remove(self, comment_id):
        """删除批注"""
        self._comments = [
            c for c in self._comments if c["id"] != comment_id
        ]

    def resolve(self, comment_id, resolved=True):
        """标记已解决"""
        for c in self._comments:
            if c["id"] == comment_id:
                c["resolved"] = resolved
                return True
        return False

    def get_all(self):
        return list(self._comments)

    def get_by_id(self, comment_id):
        for c in self._comments:
            if c["id"] == comment_id:
                return c
        return None

    def count(self):
        return len(self._comments)

    def clear(self):
        self._comments = []
        self._next_id = 1

    def to_dict(self):
        return list(self._comments)

    def from_dict(self, data):
        if isinstance(data, list):
            self._comments = data
            # 重置 ID 计数器
            max_id = 0
            for c in self._comments:
                if isinstance(c, dict) and "id" in c:
                    max_id = max(max_id, c["id"])
            self._next_id = max_id + 1

    def save_to_file(self, path):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._comments, f,
                          ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logging.error(f"批注保存失败: {e}")
            return False

    def load_from_file(self, path):
        try:
            p = Path(path)
            if not p.exists():
                return False
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.from_dict(data)
            return True
        except Exception as e:
            logging.error(f"批注加载失败: {e}")
            return False


# ==================== 批注面板 ====================
class CommentPanel(QWidget):
    """右侧批注面板"""

    jump_requested = Signal(int, int)  # (anchor_start, anchor_end)
    delete_requested = Signal(int)     # comment_id
    resolve_requested = Signal(int, bool)  # (comment_id, resolved)
    reply_requested = Signal(int)      # comment_id
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMaximumWidth(320)
        self.setMinimumWidth(240)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 标题栏
        header = QHBoxLayout()
        self._title_label = QLabel(tr("auto.beewrite_comment.358e7cb7", "💬 批注 (0)"))
        self._title_label.setStyleSheet(
            "QLabel{font-size:13px;font-weight:bold;color:#E65100;}"
        )
        header.addWidget(self._title_label)
        header.addStretch()

        btn_add = QPushButton(tr("auto.beewrite_comment.d1dd7737", "+ 新建"))
        btn_add.setStyleSheet(
            "QPushButton{background:#FFF3E0;border:1px solid #FFB300;"
            "color:#E65100;padding:3px 8px;border-radius:3px;"
            "font-size:12px;}"
            "QPushButton:hover{background:#FFE0B2;}"
        )
        btn_add.clicked.connect(self._on_add_new)
        header.addWidget(btn_add)

        btn_close = QPushButton("✕")
        btn_close.setFixedWidth(24)
        btn_close.setStyleSheet(
            "QPushButton{border:none;color:#999;font-size:14px;}"
            "QPushButton:hover{color:#E65100;}"
        )
        btn_close.clicked.connect(self.close_requested.emit)
        header.addWidget(btn_close)

        layout.addLayout(header)

        # 批注列表
        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget{border:1px solid #E0E0E0;"
            "border-radius:4px;background:#FFF;}"
            "QListWidget::item{padding:6px;"
            "border-bottom:1px solid #F0F0F0;}"
            "QListWidget::item:selected{background:#FFF3E0;}"
        )
        self._list.itemClicked.connect(self._on_item_clicked)
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(
            self._on_context_menu
        )
        layout.addWidget(self._list, 1)

        # 底部提示
        tip = QLabel(tr("auto.beewrite_comment.10df4150", "💡 双击列表项跳转到批注位置"))
        tip.setStyleSheet(
            "QLabel{color:#999;font-size:11px;padding:4px;}"
        )
        tip.setWordWrap(True)
        layout.addWidget(tip)

    # ==================== 公共方法 ====================
    def refresh(self, comments):
        """刷新列表"""
        self._list.clear()
        self._title_label.setText(tr("auto.beewrite_comment.4b2e7658", "💬 批注 ({0})").format(len(comments)))

        # 按时间倒序
        sorted_comments = sorted(
            comments, key=lambda c: c.get("time", ""), reverse=True
        )

        for c in sorted_comments:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, c["id"])

            # 显示文本
            excerpt = c.get("excerpt", "")[:30]
            if len(c.get("excerpt", "")) > 30:
                excerpt += "..."

            text = c.get("text", "")[:50]
            if len(c.get("text", "")) > 50:
                text += "..."

            if c.get("resolved", False):
                display = (f"✅ [{c['author']}] {c['time']}\n"
                           f"    {text}")
                item.setForeground(QColor("#999"))
            else:
                display = (f"📝 [{c['author']}] {c['time']}\n"
                           f"    {text}")

            item.setText(display)
            item.setToolTip(tr("auto.beewrite_comment.575ff22c", "原文：{0}\n\n{1}").format(excerpt, c.get('text', '')))
            self._list.addItem(item)

    # ==================== 事件 ====================
    def _on_item_clicked(self, item):
        """单击跳转"""
        comment_id = item.data(Qt.UserRole)
        if comment_id is None:
            return
        self._emit_jump(comment_id)

    def _emit_jump(self, comment_id):
        # 这里信号只传位置，父窗口负责查表
        self.jump_requested.emit(comment_id, 0)

    def _on_add_new(self):
        """新建批注（无锚点）"""
        text, ok = QInputDialog.getMultiLineText(
            self, "新建批注", "批注内容："
        )
        if ok and text.strip():
            # 通过父窗口处理
            parent = self.parent()
            while parent:
                if hasattr(parent, '_add_comment_no_anchor'):
                    parent._add_comment_no_anchor(text.strip())
                    break
                parent = parent.parent()

    def _on_context_menu(self, pos):
        """右键菜单"""
        item = self._list.itemAt(pos)
        if item is None:
            return
        comment_id = item.data(Qt.UserRole)

        menu = QMenu(self)
        menu.addAction(tr("auto.beewrite_comment.c0bd0f2c", "📍 跳转")).triggered.connect(
            lambda: self._emit_jump(comment_id)
        )
        menu.addAction(tr("auto.beewrite_comment.abf24497", "💬 回复")).triggered.connect(
            lambda: self.reply_requested.emit(comment_id)
        )
        menu.addSeparator()
        menu.addAction(tr("auto.beewrite_comment.865439df", "✅ 标记已解决")).triggered.connect(
            lambda: self.resolve_requested.emit(comment_id, True)
        )
        menu.addAction(tr("auto.beewrite_comment.b5df733f", "↩️ 标记未解决")).triggered.connect(
            lambda: self.resolve_requested.emit(comment_id, False)
        )
        menu.addSeparator()
        menu.addAction(tr("auto.beewrite_comment.d217371d", "🗑️ 删除")).triggered.connect(
            lambda: self.delete_requested.emit(comment_id)
        )
        menu.exec(self._list.mapToGlobal(pos))


# ==================== 批注编辑对话框 ====================
class CommentEditDialog(QDialog):
    """新建/编辑批注对话框"""

    def __init__(self, parent=None, initial_text="",
                 excerpt=""):
        super().__init__(parent)
        self.setWindowTitle(tr("auto.beewrite_comment.2c2856b1", "📝 批注"))
        self.resize(380, 260)
        layout = QVBoxLayout(self)

        if excerpt:
            excerpt_label = QLabel(tr("auto.beewrite_comment.1358fe30", "原文：{0}").format(excerpt[:80]))
            excerpt_label.setStyleSheet(
                "QLabel{color:#666;font-size:12px;"
                "background:#F5F5F5;padding:6px;"
                "border-radius:4px;}"
            )
            excerpt_label.setWordWrap(True)
            layout.addWidget(excerpt_label)

        layout.addWidget(QLabel(tr("auto.beewrite_comment.ef5350d6", "批注内容：")))
        self._edit = QTextEdit()
        self._edit.setPlainText(initial_text)
        self._edit.setStyleSheet(
            "QTextEdit{border:1px solid #CCC;"
            "border-radius:4px;padding:6px;}"
        )
        layout.addWidget(self._edit, 1)

        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_text(self):
        return self._edit.toPlainText().strip()