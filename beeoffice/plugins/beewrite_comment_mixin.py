# beeoffice/plugins/beewrite_comment_mixin.py
"""
蜜写批注 / 书签 / 修订 Mixin

职责：
  - 批注
    * _add_comment                : 给选中文字添加批注
    * _add_comment_no_anchor      : 无锚点新建批注（供批注面板调用）
    * _highlight_comment_range    : 高亮批注锚点文本
    * _toggle_comment_panel       : 显示 / 隐藏批注面板
    * _refresh_comment_panel      : 刷新批注列表
    * _on_comment_jump            : 跳转到批注锚点
    * _on_comment_delete          : 删除批注
    * _on_comment_resolve         : 标记批注已解决 / 未解决
    * _on_comment_reply           : 编辑 / 回复批注
  - 书签
    * _add_bookmark               : 添加书签
    * _show_bookmark_list         : 书签管理对话框
  - 修订
    * _toggle_revision            : 开启 / 关闭修订模式
    * _show_revision_diff         : 显示修订对比

依赖：
  - PySide6（QMessageBox / QInputDialog / QDialog / QVBoxLayout /
             QHBoxLayout / QLabel / QTextEdit / QPushButton /
             QListWidget / QListWidgetItem / QTextCursor /
             QTextCharFormat / QColor / Qt）
  - beewrite_comment（CommentEditDialog）
  - beewrite_utils（safe_escape_html）

说明：
  - CommentManager / BookmarkManager / RevisionManager 由主文件
    BeeWriteEditor.__init__ 初始化，本 Mixin 只读取和调用。
  - CommentPanel 由主文件初始化并通过信号连接到本 Mixin 的槽。
  - 不导入其他 beewrite_* Mixin，避免循环依赖。
"""
import logging

from PySide6.QtWidgets import (
    QMessageBox,
    QInputDialog,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QPushButton,
    QListWidget,
    QListWidgetItem,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QTextCursor,
    QTextCharFormat,
    QColor,
)

from beeoffice.plugins.beewrite_comment import CommentEditDialog
from beeoffice.plugins.beewrite_utils import safe_escape_html


# ==================== CommentMixin ====================
class CommentMixin:
    """蜜写批注 / 书签 / 修订 Mixin"""

    # ==================================================================
    # 批注：添加
    # ==================================================================
    def _add_comment(self):
        """给当前选中的文字添加批注"""
        if self._edit_mode != "rich_text":
            QMessageBox.information(
                self, "提示", "请先切换到所见即所得模式"
            )
            return

        cursor = self.rich_editor.textCursor()
        if not cursor.hasSelection():
            QMessageBox.information(
                self, "提示", "请先选中要加批注的文字"
            )
            return

        anchor_start = cursor.selectionStart()
        anchor_end = cursor.selectionEnd()
        excerpt = cursor.selectedText()[:100]

        dlg = CommentEditDialog(self, excerpt=excerpt)
        if dlg.exec() != QDialog.Accepted:
            return

        text = dlg.get_text()
        if not text:
            return

        comment = self._comment_manager.add(
            text, anchor_start, anchor_end, excerpt
        )

        self._highlight_comment_range(anchor_start, anchor_end)
        self._refresh_comment_panel()
        self._comment_panel.setVisible(True)
        self._set_status(
            f"✅ 已添加批注 #{comment['id']}", 2000
        )

    def _add_comment_no_anchor(self, text):
        """无锚点新建批注（由批注面板的「+ 新建」按钮触发）"""
        if self._edit_mode != "rich_text":
            QMessageBox.information(
                self, "提示", "请先切换到所见即所得模式"
            )
            return
        cursor = self.rich_editor.textCursor()
        pos = cursor.position()
        comment = self._comment_manager.add(text, pos, pos, "")
        self._refresh_comment_panel()
        self._comment_panel.setVisible(True)
        self._set_status(
            f"✅ 已添加批注 #{comment['id']}", 2000
        )

    # ==================================================================
    # 批注：高亮
    # ==================================================================
    def _highlight_comment_range(self, start, end):
        """给批注锚点范围加淡黄色背景"""
        cursor = self.rich_editor.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(255, 249, 196))
        cursor.mergeCharFormat(fmt)
        cursor.clearSelection()

    # ==================================================================
    # 批注：面板显示 / 刷新
    # ==================================================================
    def _toggle_comment_panel(self):
        """切换批注面板可见性"""
        if self._comment_panel.isVisible():
            self._comment_panel.setVisible(False)
        else:
            self._refresh_comment_panel()
            self._comment_panel.setVisible(True)

    def _refresh_comment_panel(self):
        """把最新批注列表刷新到面板"""
        self._comment_panel.refresh(self._comment_manager.get_all())

    # ==================================================================
    # 批注：跳转 / 删除 / 解决 / 编辑
    # ==================================================================
    def _on_comment_jump(self, comment_id, _):
        """跳转到批注锚点位置"""
        comment = self._comment_manager.get_by_id(comment_id)
        if not comment:
            return
        start = comment.get("anchor_start", 0)
        end = comment.get("anchor_end", 0)
        # 无锚点批注：定位到位置附近 ±20 字符
        if start == end:
            start = max(0, start - 20)
            end = min(len(self.rich_editor.toPlainText()), start + 40)

        cursor = self.rich_editor.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        self.rich_editor.setTextCursor(cursor)
        self.rich_editor.ensureCursorVisible()
        self.rich_editor.setFocus()

    def _on_comment_delete(self, comment_id):
        """删除批注（带确认）"""
        reply = QMessageBox.question(
            self,
            "删除批注",
            "确定删除这条批注吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._comment_manager.remove(comment_id)
        self._refresh_comment_panel()
        self._set_status("✅ 批注已删除", 2000)

    def _on_comment_resolve(self, comment_id, resolved):
        """标记批注为已解决 / 未解决"""
        self._comment_manager.resolve(comment_id, resolved)
        self._refresh_comment_panel()
        status = "已解决" if resolved else "未解决"
        self._set_status(f"✅ 批注已标记为{status}", 2000)

    def _on_comment_reply(self, comment_id):
        """编辑 / 回复批注（修改文本内容）"""
        comment = self._comment_manager.get_by_id(comment_id)
        if not comment:
            return
        dlg = CommentEditDialog(
            self, initial_text=comment.get("text", "")
        )
        if dlg.exec() != QDialog.Accepted:
            return
        new_text = dlg.get_text()
        if new_text:
            comment["text"] = new_text
            self._refresh_comment_panel()
            self._set_status("✅ 批注已更新", 2000)

    # ==================================================================
    # 书签
    # ==================================================================
    def _add_bookmark(self):
        """添加书签（记录当前位置）"""
        if self._edit_mode != "rich_text":
            QMessageBox.information(
                self, "提示", "请先切换到所见即所得模式"
            )
            return
        cursor = self.rich_editor.textCursor()
        pos = cursor.position()
        line = cursor.blockNumber() + 1

        name, ok = QInputDialog.getText(
            self,
            "添加书签",
            "书签名称：",
            text=f"书签{len(self._bookmark_manager._bookmarks) + 1}",
        )
        if not ok or not name.strip():
            return
        name = name.strip()

        # 同名书签覆盖确认
        if self._bookmark_manager.has(name):
            reply = QMessageBox.question(
                self,
                "书签已存在",
                f"书签「{name}」已存在，是否覆盖？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        self._bookmark_manager.add(name, pos, line)
        self._set_status(f"✅ 已添加书签「{name}」", 2000)

    def _show_bookmark_list(self):
        """书签管理对话框（跳转 / 删除）"""
        bookmarks = self._bookmark_manager.get_all()
        if not bookmarks:
            QMessageBox.information(self, "书签", "当前没有书签")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("🔖 书签管理")
        dlg.resize(400, 360)
        layout = QVBoxLayout(dlg)

        # ---------- 书签列表 ----------
        list_widget = QListWidget()
        for name, info in bookmarks.items():
            item = QListWidgetItem(
                f"🔖 {name}  (第 {info.get('line', '?')} 行)"
            )
            item.setData(Qt.UserRole, name)
            list_widget.addItem(item)
        layout.addWidget(list_widget)

        # ---------- 按钮栏 ----------
        bl = QHBoxLayout()

        def jump():
            item = list_widget.currentItem()
            if not item:
                return
            name = item.data(Qt.UserRole)
            info = self._bookmark_manager.get(name)
            if info:
                pos = info.get("pos", 0)
                cursor = self.rich_editor.textCursor()
                cursor.setPosition(pos)
                self.rich_editor.setTextCursor(cursor)
                self.rich_editor.ensureCursorVisible()
                self.rich_editor.setFocus()
            dlg.accept()

        def delete():
            item = list_widget.currentItem()
            if not item:
                return
            name = item.data(Qt.UserRole)
            self._bookmark_manager.remove(name)
            list_widget.takeItem(list_widget.row(item))
            self._set_status(f"✅ 已删除书签「{name}」", 2000)

        btn_jump = QPushButton("📍 跳转")
        btn_jump.clicked.connect(jump)
        bl.addWidget(btn_jump)

        btn_del = QPushButton("🗑️ 删除")
        btn_del.clicked.connect(delete)
        bl.addWidget(btn_del)

        bl.addStretch()

        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(dlg.reject)
        bl.addWidget(btn_close)

        layout.addLayout(bl)

        # 双击直接跳转
        list_widget.itemDoubleClicked.connect(lambda _: jump())
        dlg.exec()

    # ==================================================================
    # 修订：开关
    # ==================================================================
    def _toggle_revision(self):
        """开启 / 关闭修订模式"""
        if self._edit_mode != "rich_text":
            QMessageBox.information(
                self, "提示", "请先切换到所见即所得模式"
            )
            self._btn_revision.setChecked(False)
            return

        if self._revision_manager.active:
            # 关闭修订 → 显示对比
            self._revision_manager.stop_revision()
            self._btn_revision.setChecked(False)
            self._btn_revision.setText("📝 修订")
            self._show_revision_diff()
        else:
            # 开启修订 → 保存基线
            current = self.rich_editor.toPlainText()
            self._revision_manager.start_revision(current)
            self._btn_revision.setChecked(True)
            self._btn_revision.setText("📝 修订中")
            self._set_status(
                f"✅ 修订模式已开启（基线 {len(current)} 字符）", 3000
            )

    # ==================================================================
    # 修订：对比
    # ==================================================================
    def _show_revision_diff(self):
        """显示修订对比对话框（摘要 + 高亮 diff + 接受 / 拒绝）"""
        if not self._revision_manager.has_baseline:
            QMessageBox.information(self, "提示", "当前没有修订基线")
            return

        current = self.rich_editor.toPlainText()
        result = self._revision_manager.compute_diff(current)

        dlg = QDialog(self)
        dlg.setWindowTitle("📊 修订对比")
        dlg.resize(800, 560)
        layout = QVBoxLayout(dlg)

        # ---------- 摘要 ----------
        summary = QLabel(
            f"<b>修订摘要</b>（基线时间："
            f"{self._revision_manager.baseline_time}）<br>"
            f"<span style='color:#1B5E20;'>"
            f"新增 {result['additions']} 行</span> | "
            f"<span style='color:#B71C1C;'>"
            f"删除 {result['deletions']} 行</span> | "
            f"<span style='color:#E65100;'>"
            f"修改 {result['modified']} 行</span> | "
            f"<b>总变更 {result['total_changes']} 处</b>"
        )
        summary.setStyleSheet(
            "QLabel{background:#FFF8E1;padding:12px;"
            "border-radius:6px;font-size:13px;}"
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        # ---------- diff 视图 ----------
        diff_view = QTextEdit()
        diff_view.setReadOnly(True)
        diff_view.setStyleSheet(
            "QTextEdit{background:#FAFAFA;font-family:Consolas;"
            "font-size:12px;padding:8px;}"
        )

        html_lines = []
        for line in result["diff_text"].split("\n"):
            if line.startswith("+") and not line.startswith("+++"):
                html_lines.append(
                    f"<span style='color:#1B5E20;"
                    f"background:#E8F5E9;'>"
                    f"{safe_escape_html(line)}</span>"
                )
            elif line.startswith("-") and not line.startswith("---"):
                html_lines.append(
                    f"<span style='color:#B71C1C;"
                    f"background:#FFEBEE;'>"
                    f"{safe_escape_html(line)}</span>"
                )
            elif line.startswith("@@"):
                html_lines.append(
                    f"<span style='color:#0D47A1;font-weight:bold;'>"
                    f"{safe_escape_html(line)}</span>"
                )
            else:
                html_lines.append(safe_escape_html(line))

        diff_view.setHtml("<br>".join(html_lines))
        layout.addWidget(diff_view, 1)

        # ---------- 按钮栏 ----------
        bl = QHBoxLayout()

        btn_accept = QPushButton("✅ 接受所有修改")
        btn_accept.setStyleSheet(
            "QPushButton{background:#E8F5E9;border:1px solid #4CAF50;"
            "color:#1B5E20;padding:6px 12px;border-radius:4px;}"
            "QPushButton:hover{background:#C8E6C9;}"
        )

        def do_accept():
            self._revision_manager.accept_all()
            self._btn_revision.setChecked(False)
            self._btn_revision.setText("📝 修订")
            self._set_status("✅ 已接受所有修改", 2000)
            dlg.accept()

        btn_accept.clicked.connect(do_accept)
        bl.addWidget(btn_accept)

        btn_reject = QPushButton("❌ 拒绝所有修改")
        btn_reject.setStyleSheet(
            "QPushButton{background:#FFEBEE;border:1px solid #F44336;"
            "color:#B71C1C;padding:6px 12px;border-radius:4px;}"
            "QPushButton:hover{background:#FFCDD2;}"
        )

        def do_reject():
            baseline = self._revision_manager.reject_all()
            if baseline is not None:
                self.rich_editor.setPlainText(baseline)
            self._btn_revision.setChecked(False)
            self._btn_revision.setText("📝 修订")
            self._set_status("✅ 已恢复到基线", 2000)
            dlg.accept()

        btn_reject.clicked.connect(do_reject)
        bl.addWidget(btn_reject)

        bl.addStretch()

        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(dlg.reject)
        bl.addWidget(btn_close)

        layout.addLayout(bl)
        dlg.exec()