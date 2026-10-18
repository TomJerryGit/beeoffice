# beeoffice/plugins/beewrite_view_mixin.py
"""
蜜写视图 / 查找替换 / 粘贴 / 撤销重做 / 状态栏 Mixin

职责：
  - 大纲面板
    * _toggle_outline
    * _on_outline_jump
    * _refresh_outline_if_visible
  - 阅读模式
    * _toggle_reading_mode / _enter_reading_mode / _exit_reading_mode
    * _hide_layout_widgets / _hide_layout_widgets_from_quick
    * keyPressEvent（Esc 退出阅读模式）
  - 双屏对比
    * _toggle_split_view / _enter_split_view / _exit_split_view
  - 查找替换
    * _find_current / _close_find_bar
  - 无格式粘贴
    * _paste_plain
  - 撤销 / 重做
    * _undo / _redo
  - 状态栏
    * _update_status_bar / _update_cursor_position

依赖：
  - PySide6（QDialog / QVBoxLayout / QHBoxLayout / QLabel / QTextEdit /
             QPushButton / QSplitter / QFileDialog / QMessageBox /
             QTextCursor / QApplication / Qt）
  - beewrite_utils（count_words / safe_escape_html）

说明：
  - 本 Mixin 负责「窗口布局 / 视图切换 / 编辑器辅助操作」相关的全部逻辑。
  - 不导入其他 beewrite_* Mixin，避免循环依赖。
"""
import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QPushButton,
    QSplitter,
    QFileDialog,
    QMessageBox,
    QApplication,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor

from beeoffice.plugins.beewrite_utils import (
    count_words,
    safe_escape_html,
)
from beeoffice.i18n import tr


# ==================== ViewMixin ====================
class ViewMixin:
    """蜜写视图 / 查找替换 / 粘贴 / 撤销重做 / 状态栏 Mixin"""

    # ==================================================================
    # 大纲面板
    # ==================================================================
    def _toggle_outline(self):
        """显示 / 隐藏大纲面板"""
        if self._outline_panel.isVisible():
            self._outline_panel.setVisible(False)
            sizes = self._main_splitter.sizes()
            sizes[0] = 0
            self._main_splitter.setSizes(sizes)
        else:
            editor = (
                self.rich_editor
                if self._edit_mode == "rich_text"
                else self.markdown_editor
            )
            self._outline_panel.set_editor(editor)
            self._outline_panel.setVisible(True)
            sizes = self._main_splitter.sizes()
            sizes[0] = 220
            self._main_splitter.setSizes(sizes)

    def _on_outline_jump(self, pos):
        """大纲点击 → 跳转到对应位置"""
        editor = (
            self.rich_editor
            if self._edit_mode == "rich_text"
            else self.markdown_editor
        )

        if hasattr(editor, 'document'):
            cursor = editor.textCursor()
            cursor.setPosition(pos)
            editor.setTextCursor(cursor)
        else:
            cursor = editor.textCursor()
            cursor.movePosition(QTextCursor.Start)
            for _ in range(pos):
                cursor.movePosition(QTextCursor.Down)
            editor.setTextCursor(cursor)

        editor.ensureCursorVisible()
        editor.setFocus()

    def _refresh_outline_if_visible(self):
        """刷新大纲（若面板可见）"""
        if self._outline_panel.isVisible():
            editor = (
                self.rich_editor
                if self._edit_mode == "rich_text"
                else self.markdown_editor
            )
            self._outline_panel.set_editor(editor)

    # ==================================================================
    # 阅读模式
    # ==================================================================
    def _toggle_reading_mode(self):
        """切换阅读模式"""
        if getattr(self, '_reading_mode', False):
            self._exit_reading_mode()
        else:
            self._enter_reading_mode()

    def _enter_reading_mode(self):
        """进入阅读模式：隐藏工具栏、面板、预览，只保留编辑器"""
        self._reading_mode = True
        self._reading_state = {
            "toolbar1": self._toolbar1.isVisible(),
            "toolbar2": self._toolbar2.isVisible(),
            "outline": self._outline_panel.isVisible(),
            "comments": self._comment_panel.isVisible(),
            "variables": self.variable_panel.isVisible(),
        }

        # 隐藏工具栏与面板
        self._toolbar1.setVisible(False)
        self._toolbar2.setVisible(False)
        self._hide_layout_widgets(self._mode_toolbar, True)
        self._hide_layout_widgets_from_quick(True)

        self._outline_panel.setVisible(False)
        self._comment_panel.setVisible(False)
        self.variable_panel.setVisible(False)

        # 隐藏预览，让编辑器占满
        self.preview.setVisible(False)
        sizes = self._main_splitter.sizes()
        total = sum(sizes)
        new_sizes = [0] * len(sizes)
        # 索引 1 为 editor_stack
        new_sizes[1] = total
        self._main_splitter.setSizes(new_sizes)

        self._set_status(tr("auto.beewrite_view_mixin.7ec936f4", "📖 阅读模式（按 F11 或 Esc 退出）"), 0)

    def _exit_reading_mode(self):
        """退出阅读模式，恢复原布局"""
        self._reading_mode = False
        state = getattr(self, '_reading_state', {})

        self._toolbar1.setVisible(state.get("toolbar1", True))
        self._toolbar2.setVisible(state.get("toolbar2", True))
        self._hide_layout_widgets(self._mode_toolbar, False)
        self._hide_layout_widgets_from_quick(False)

        self._outline_panel.setVisible(state.get("outline", False))
        self._comment_panel.setVisible(state.get("comments", False))
        self.variable_panel.setVisible(state.get("variables", True))

        self.preview.setVisible(True)
        self._main_splitter.setSizes([0, 350, 350, 0, 250])

        self._set_status(tr("auto.beewrite_view_mixin.e8cd7a82", "已退出阅读模式"), 2000)

    def _hide_layout_widgets(self, layout, hide):
        """遍历 QLayout 中的 widget，统一设置可见性"""
        for i in range(layout.count()):
            item = layout.itemAt(i)
            w = item.widget() if item else None
            if w:
                w.setVisible(not hide)

    def _hide_layout_widgets_from_quick(self, hide):
        """隐藏 / 恢复快捷工具栏中的按钮（通过文本匹配定位）"""
        try:
            for child in self.findChildren(QPushButton):
                text = child.text()
                if text in (
                    "📄 导出 PDF",
                    "📝 导出 Word",
                    "💾 保存 MD",
                    "📋 存为模板",
                    "📄 页面设置",
                    "🖨️ 打印预览",
                ):
                    child.setVisible(not hide)
        except Exception as e:
            logging.error(f"隐藏快捷工具栏失败: {e}")

    def keyPressEvent(self, event):
        """阅读模式下按 Esc 退出"""
        if getattr(self, '_reading_mode', False):
            if event.key() == Qt.Key_Escape:
                self._exit_reading_mode()
                return
        super().keyPressEvent(event)

    # ==================================================================
    # 双屏对比
    # ==================================================================
    def _toggle_split_view(self):
        """切换双屏对比"""
        if getattr(self, '_split_view_active', False):
            self._exit_split_view()
        else:
            self._enter_split_view()

    def _enter_split_view(self):
        """打开双屏对比对话框"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("auto.beewrite_view_mixin.79abf256", "选择对照文档"),
            "",
            tr("auto.beewrite_view_mixin.d6bedeb2", "Markdown (*.md);;文本 (*.txt);;所有文件 (*)"),
        )
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                compare_content = f.read()
        except Exception as e:
            QMessageBox.warning(self, tr("auto.beewrite_view_mixin.e1ae8ece", "打开失败"), str(e))
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(tr("auto.beewrite_view_mixin.7817b7b1", "📊 双屏对比 — {0}").format(Path(path).name))
        dlg.resize(1100, 700)
        layout = QVBoxLayout(dlg)

        # ---------- 顶部标题 ----------
        header = QLabel(
            tr("auto.beewrite_view_mixin.ee0d46d7", "<b>左侧</b>：当前文档　|　<b>右侧</b>：{0}").format(Path(path).name)
        )
        header.setStyleSheet(
            "QLabel{background:#FFF8E1;padding:8px;"
            "border-radius:4px;font-size:12px;}"
        )
        layout.addWidget(header)

        # ---------- 分屏视图 ----------
        splitter = QSplitter(Qt.Horizontal)

        left_edit = QTextEdit()
        left_edit.setReadOnly(True)
        left_edit.setPlainText(self.content())
        left_edit.setStyleSheet(
            "QTextEdit{border:1px solid #DDD;font-family:Consolas;"
            "font-size:13px;padding:8px;background:#FAFAFA;}"
        )
        splitter.addWidget(left_edit)

        right_edit = QTextEdit()
        right_edit.setReadOnly(True)
        right_edit.setPlainText(compare_content)
        right_edit.setStyleSheet(
            "QTextEdit{border:1px solid #DDD;font-family:Consolas;"
            "font-size:13px;padding:8px;background:#FAFAFA;}"
        )
        splitter.addWidget(right_edit)

        splitter.setSizes([550, 550])
        layout.addWidget(splitter, 1)

        # ---------- 按钮栏 ----------
        bl = QHBoxLayout()

        btn_diff = QPushButton(tr("auto.beewrite_view_mixin.7202d66a", "🔍 显示差异"))
        btn_diff.setStyleSheet(
            "QPushButton{background:#FFF3E0;border:1px solid #FFB300;"
            "color:#E65100;padding:6px 12px;border-radius:4px;}"
            "QPushButton:hover{background:#FFE0B2;}"
        )

        def show_diff():
            from beeoffice.plugins.bee_export import compare_documents
            result = compare_documents(
                compare_content, self.content()
            )
            diff_dlg = QDialog(dlg)
            diff_dlg.setWindowTitle(tr("auto.beewrite_view_mixin.95f60c82", "📊 差异详情"))
            diff_dlg.resize(800, 500)
            dl = QVBoxLayout(diff_dlg)

            summary = QLabel(
                tr("auto.beewrite_view_mixin.922d2cf6", "新增：<b>{0}</b> 行　|　删除：<b>{1}</b> 行　|　总变更：<b>{2}</b> 处").format(result['additions'], result['deletions'], result['total_changes'])
            )
            summary.setStyleSheet(
                "QLabel{background:#FFF8E1;padding:12px;"
                "border-radius:6px;font-size:13px;}"
            )
            dl.addWidget(summary)

            diff_view = QTextEdit()
            diff_view.setReadOnly(True)
            diff_view.setStyleSheet(
                "QTextEdit{background:#FAFAFA;font-family:Consolas;"
                "font-size:12px;padding:8px;}"
            )

            html_lines = []
            for line in result["diff"].split("\n"):
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
            dl.addWidget(diff_view, 1)

            btn_close2 = QPushButton(tr("auto.beewrite_view_mixin.6c14bd7f", "关闭"))
            btn_close2.clicked.connect(diff_dlg.reject)
            dl.addWidget(btn_close2)

            diff_dlg.exec()

        btn_diff.clicked.connect(show_diff)
        bl.addWidget(btn_diff)

        bl.addStretch()

        # ---------- 交换左右 ----------
        btn_swap = QPushButton(tr("auto.beewrite_view_mixin.0cd0f997", "🔄 交换左右"))

        def swap():
            left_content = left_edit.toPlainText()
            right_content = right_edit.toPlainText()
            left_edit.setPlainText(right_content)
            right_edit.setPlainText(left_content)

        btn_swap.clicked.connect(swap)
        bl.addWidget(btn_swap)

        # ---------- 关闭 ----------
        btn_close = QPushButton(tr("auto.beewrite_view_mixin.6c14bd7f", "关闭"))
        btn_close.clicked.connect(dlg.accept)
        bl.addWidget(btn_close)

        layout.addLayout(bl)

        self._split_view_active = True
        dlg.finished.connect(lambda _: self._exit_split_view())
        dlg.exec()

    def _exit_split_view(self):
        """退出双屏对比"""
        self._split_view_active = False

    # ==================================================================
    # 查找替换
    # ==================================================================
    def _find_current(self):
        """在当前编辑器中打开查找替换栏"""
        editor = (
            self.rich_editor
            if self._edit_mode == "rich_text"
            else self.markdown_editor
        )
        self.find_bar.show_for_editor(editor)
        self.find_bar.find_input.setFocus()

    def _close_find_bar(self):
        """关闭查找替换栏"""
        if self.find_bar.isVisible():
            self.find_bar.hide()
            editor = (
                self.rich_editor
                if self._edit_mode == "rich_text"
                else self.markdown_editor
            )
            editor.setFocus()

    # ==================================================================
    # 无格式粘贴
    # ==================================================================
    def _paste_plain(self):
        """无格式粘贴（粘贴纯文本，清除所有富文本格式）"""
        cb = QApplication.clipboard()
        if not cb.mimeData().hasText():
            return
        text = cb.mimeData().text()
        if self._edit_mode == "markdown":
            self.markdown_editor.insertPlainText(text)
        else:
            self.rich_editor.insertPlainText(text)

    # ==================================================================
    # 撤销 / 重做
    # ==================================================================
    def _undo(self):
        """撤销"""
        if self._edit_mode == "markdown":
            self.markdown_editor.undo()
        else:
            self.rich_editor.undo()

    def _redo(self):
        """重做"""
        if self._edit_mode == "markdown":
            self.markdown_editor.redo()
        else:
            self.rich_editor.redo()

    # ==================================================================
    # 状态栏
    # ==================================================================
    def _update_status_bar(self):
        """更新状态栏（字数 / 字符）"""
        text = self.content()
        char_count = len(text)
        word_count = count_words(text)
        self._word_count_label.setText(tr("auto.beewrite_view_mixin.1a98e9a7", "字数：{word_count}").format(word_count=word_count))
        self._char_count_label.setText(tr("auto.beewrite_view_mixin.fc9bf7d3", "字符：{char_count}").format(char_count=char_count))

    def _update_cursor_position(self):
        """更新状态栏光标行列位置"""
        if self._edit_mode == "markdown":
            cursor = self.markdown_editor.textCursor()
        else:
            cursor = self.rich_editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        self._cursor_pos_label.setText(tr("auto.beewrite_view_mixin.fef93934", "行 {line} 列 {col}").format(line=line, col=col))