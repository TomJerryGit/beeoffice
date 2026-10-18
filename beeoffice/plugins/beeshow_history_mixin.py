# beeoffice/plugins/beeshow_history_mixin.py
"""
蜜演版本历史 Mixin（任务 4.1）

职责：
  - _save_snapshot      : 保存当前编辑器内容快照
  - _show_history_panel : 弹出历史版本面板
  - _restore_snapshot   : 回滚到指定版本
  - _clear_history      : 清空历史

设计：
  - 内存中保留最近 MAX_HISTORY 个快照（默认 50）
  - 每个快照记录：时间戳 + 全文 Markdown + 幻灯片数
  - 触发时机：_update_preview 防抖后（即用户停止编辑 300ms 后）
  - 去重：内容与最近一个快照完全相同则不保存
  - 与 Qt 无关的纯数据结构，便于测试

对标：
  - WPS 365 的「版本历史自动保存，一键回溯任意历史状态」

依赖：
  - time / datetime
  - PySide6（QDialog / QVBoxLayout / QHBoxLayout / QLabel /
             QPushButton / QListWidget / QListWidgetItem /
             QMessageBox / QSplitter / QPlainTextEdit）
  - beeoffice.plugins.beeshow_constants.SLIDE_THEMES（预览用）

注意：
  - 不导入其他 beeshow_* Mixin，避免循环依赖
  - _save_snapshot 由 SlideMixin._update_preview 调用
    （需在 slide_mixin 里加一行，见文末）
"""

import logging
from datetime import datetime

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QSplitter,
    QPlainTextEdit,
)
from PySide6.QtCore import Qt
from beeoffice.i18n import tr


class HistoryMixin:
    """蜜演版本历史 Mixin"""

    # 最多保留的快照数
    MAX_HISTORY = 50

    # ==================== 保存快照 ====================
    def _save_snapshot(self, force: bool = False):
        """
        保存当前编辑器内容快照。

        :param force: 强制保存（即使与上一个快照相同）

        触发时机：
          - _update_preview 末尾（防抖 300ms 后）
          - 用户主动保存时（force=True）

        去重逻辑：
          - 若内容与 _slide_history[-1]["content"] 完全相同 → 跳过
          - 若 force=True → 强制保存
        """
        try:
            content = self._editor.toPlainText()
            if not content.strip():
                return

            # 去重
            if not force and self._slide_history:
                last = self._slide_history[-1]
                if last["content"] == content:
                    return

            snapshot = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "content": content,
                "slide_count": len(self._slides_html),
                "char_count": len(content),
            }
            self._slide_history.append(snapshot)

            # 裁剪到 MAX_HISTORY
            if len(self._slide_history) > self.MAX_HISTORY:
                self._slide_history = self._slide_history[
                    -self.MAX_HISTORY:
                ]
        except Exception as e:
            logging.error(f"保存快照失败：{e}")

    # ==================== 历史面板 ====================
    def _show_history_panel(self):
        """
        弹出历史版本面板。

        布局：
          - 左侧：历史列表（时间 + 幻灯片数 + 字符数）
          - 右侧：选中版本的预览
          - 底部：恢复 / 删除 / 关闭
        """
        if not self._slide_history:
            QMessageBox.information(
                self, tr("auto.beeshow_history_mixin.fe6e2c68", "📜 版本历史"),
                tr("auto.beeshow_history_mixin.999fa178", "暂无历史版本。\n\n"
                "每次编辑后会自动保存快照，最多保留 50 个。")
            )
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(tr("auto.beeshow_history_mixin.fe6e2c68", "📜 版本历史"))
        dlg.resize(900, 560)
        layout = QVBoxLayout(dlg)

        # 顶部提示
        tip = QLabel(
            tr("auto.beeshow_history_mixin.eb5bc1cd", "💡 共 {0} 个历史版本。\n双击任意版本可恢复；恢复后当前内容会被覆盖（可撤销）。").format(len(self._slide_history))
        )
        tip.setStyleSheet(
            "QLabel{color:#666;font-size:12px;padding:8px;"
            "background:#FFF8E1;border-radius:4px;}"
        )
        tip.setWordWrap(True)
        layout.addWidget(tip)

        # 主体：左侧列表 + 右侧预览
        splitter = QSplitter(Qt.Horizontal)

        # 左侧列表
        lst = QListWidget()
        lst.setStyleSheet(
            "QListWidget{border:1px solid #DDD;border-radius:4px;"
            "font-size:13px;}"
            "QListWidget::item{padding:8px;}"
            "QListWidget::item:selected{background:#FFF3E0;}"
        )
        # 倒序显示（最新的在最上）
        for i in range(len(self._slide_history) - 1, -1, -1):
            snap = self._slide_history[i]
            item = QListWidgetItem(
                tr("auto.beeshow_history_mixin.64f5a68a", "🕐 {0}\n   {1} 页 · {2} 字").format(snap['timestamp'], snap['slide_count'], snap['char_count'])
            )
            item.setData(Qt.UserRole, i)  # 存原始索引
            lst.addItem(item)
        if lst.count() > 0:
            lst.setCurrentRow(0)
        splitter.addWidget(lst)

        # 右侧预览
        preview = QPlainTextEdit()
        preview.setReadOnly(True)
        preview.setStyleSheet(
            "QPlainTextEdit{background:#FAFAFA;"
            "font-family:Consolas;font-size:12px;padding:8px;}"
        )
        splitter.addWidget(preview)

        splitter.setSizes([300, 600])
        layout.addWidget(splitter)

        # 选中时刷新预览
        def on_selection_changed():
            item = lst.currentItem()
            if item is None:
                return
            idx = item.data(Qt.UserRole)
            if 0 <= idx < len(self._slide_history):
                preview.setPlainText(
                    self._slide_history[idx]["content"]
                )

        lst.currentItemChanged.connect(
            lambda cur, prev: on_selection_changed()
        )
        on_selection_changed()

        # 底部按钮
        bl = QHBoxLayout()

        btn_restore = QPushButton(tr("auto.beeshow_history_mixin.bc657d67", "↩ 恢复此版本"))
        btn_restore.setStyleSheet(
            "QPushButton{background:#FFB300;color:#000;"
            "padding:6px 16px;border:none;border-radius:4px;"
            "font-weight:bold;}"
            "QPushButton:hover{background:#FFA000;}"
        )

        def do_restore():
            item = lst.currentItem()
            if item is None:
                return
            idx = item.data(Qt.UserRole)
            if not (0 <= idx < len(self._slide_history)):
                return

            snap = self._slide_history[idx]
            reply = QMessageBox.question(
                dlg, tr("auto.beeshow_history_mixin.b537457e", "确认恢复"),
                tr("auto.beeshow_history_mixin.a6cff6a6", "确定恢复到 {0} 的版本吗？\n\n当前内容将被覆盖。\n（恢复后可通过再次编辑产生新快照）").format(snap['timestamp']),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

            # 先保存当前内容为快照（防止误恢复后无法找回）
            self._save_snapshot(force=True)

            # 恢复
            self._editor.blockSignals(True)
            self._editor.setPlainText(snap["content"])
            self._editor.blockSignals(False)
            self._current_slide = 0
            self._update_preview()
            self._set_status(
                tr("auto.beeshow_history_mixin.266550cf", "↩ 已恢复到 {0}").format(snap['timestamp']), 3000
            )
            dlg.accept()

        btn_restore.clicked.connect(do_restore)
        bl.addWidget(btn_restore)

        # 删除单条
        btn_delete = QPushButton(tr("auto.beeshow_history_mixin.e14a3d33", "🗑 删除此版本"))

        def do_delete():
            item = lst.currentItem()
            if item is None:
                return
            idx = item.data(Qt.UserRole)
            if not (0 <= idx < len(self._slide_history)):
                return
            reply = QMessageBox.question(
                dlg, tr("auto.beeshow_history_mixin.3c06abe1", "确认删除"),
                tr("auto.beeshow_history_mixin.ceb09c85", "确定删除此历史版本吗？（不可恢复）"),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            self._slide_history.pop(idx)
            lst.takeItem(lst.row(item))
            on_selection_changed()

        btn_delete.clicked.connect(do_delete)
        bl.addWidget(btn_delete)

        bl.addStretch()

        # 清空所有
        btn_clear = QPushButton(tr("auto.beeshow_history_mixin.a474364c", "🧹 清空历史"))
        btn_clear.setStyleSheet(
            "QPushButton{color:#B71C1C;border:1px solid #F44336;"
            "padding:6px 12px;border-radius:4px;}"
            "QPushButton:hover{background:#FFEBEE;}"
        )

        def do_clear():
            reply = QMessageBox.question(
                dlg, tr("auto.beeshow_history_mixin.1cb22bad", "确认清空"),
                tr("auto.beeshow_history_mixin.7337b389", "确定清空全部 {0} 个历史版本吗？（不可恢复）").format(len(self._slide_history)),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            self._slide_history.clear()
            dlg.accept()
            self._set_status(tr("auto.beeshow_history_mixin.b136f90b", "🧹 历史已清空"), 2000)

        btn_clear.clicked.connect(do_clear)
        bl.addWidget(btn_clear)

        # 关闭
        btn_close = QPushButton(tr("auto.beeshow_history_mixin.6c14bd7f", "关闭"))
        btn_close.clicked.connect(dlg.reject)
        bl.addWidget(btn_close)

        layout.addLayout(bl)
        dlg.exec()

    # ==================== 快速回滚 ====================
    def _restore_last_snapshot(self):
        """
        快速回滚到上一个版本（比当前内容早一个快照）。

        使用场景：误删内容后立刻 Ctrl+Z 式的补救。
        """
        if len(self._slide_history) < 2:
            self._set_status(tr("auto.beeshow_history_mixin.216dc3f6", "⚠️ 没有更早的版本"), 2000)
            return

        # 先保存当前内容
        self._save_snapshot(force=True)

        # 取倒数第二个（倒数第一个是刚保存的当前内容）
        prev = self._slide_history[-2]
        self._editor.blockSignals(True)
        self._editor.setPlainText(prev["content"])
        self._editor.blockSignals(False)
        self._current_slide = 0
        self._update_preview()
        self._set_status(
            tr("auto.beeshow_history_mixin.85b2e8c1", "↩ 已回滚到 {0}").format(prev['timestamp']), 3000
        )

    # ==================== 清空 ====================
    def _clear_history(self):
        """清空历史（无 UI，供外部调用）"""
        self._slide_history.clear()