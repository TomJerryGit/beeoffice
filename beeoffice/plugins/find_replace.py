# beeoffice/plugins/find_replace.py
"""
蜜写查找替换栏：支持普通/正则查找、区分大小写、全字匹配、替换、全部替换
"""
import re
import logging

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLineEdit, QPushButton,
    QCheckBox, QLabel, QPlainTextEdit, QTextEdit, QMessageBox
)
from PySide6.QtGui import QTextCursor, QTextDocument, QTextCharFormat, QColor
from PySide6.QtCore import Qt


class FindReplaceBar(QWidget):
    """查找替换栏"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._editor = None
        self._last_search = ""
        self._build_ui()
        self.hide()

    # ==================== UI ====================
    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 6, 8, 6)
        main_layout.setSpacing(4)

        # ---- 查找行 ----
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("🔍 查找:"))

        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("输入要查找的内容...")
        self.find_input.setMinimumWidth(200)
        self.find_input.returnPressed.connect(self.find_next)
        self.find_input.textChanged.connect(self._on_search_text_changed)
        row1.addWidget(self.find_input, 1)

        self.btn_prev = QPushButton("↑ 上一个")
        self.btn_prev.clicked.connect(self.find_prev)
        row1.addWidget(self.btn_prev)

        self.btn_next = QPushButton("↓ 下一个")
        self.btn_next.clicked.connect(self.find_next)
        row1.addWidget(self.btn_next)

        self.btn_close = QPushButton("✕")
        self.btn_close.setFixedWidth(30)
        self.btn_close.setToolTip("关闭查找栏 (Esc)")
        self.btn_close.clicked.connect(self.hide)
        row1.addWidget(self.btn_close)

        main_layout.addLayout(row1)

        # ---- 替换行 ----
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("📝 替换:"))

        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText("输入替换内容...")
        row2.addWidget(self.replace_input, 1)

        self.btn_replace = QPushButton("替换")
        self.btn_replace.clicked.connect(self.replace_one)
        row2.addWidget(self.btn_replace)

        self.btn_replace_all = QPushButton("全部替换")
        self.btn_replace_all.clicked.connect(self.replace_all)
        row2.addWidget(self.btn_replace_all)

        main_layout.addLayout(row2)

        # ---- 选项行 ----
        row3 = QHBoxLayout()

        self.case_check = QCheckBox("区分大小写")
        row3.addWidget(self.case_check)

        self.word_check = QCheckBox("全字匹配")
        row3.addWidget(self.word_check)

        self.regex_check = QCheckBox("正则表达式")
        self.regex_check.stateChanged.connect(self._on_regex_changed)
        row3.addWidget(self.regex_check)

        row3.addStretch()

        self.result_label = QLabel("")
        self.result_label.setStyleSheet(
            "QLabel{color:#666;font-size:12px;padding:0 8px;}"
        )
        row3.addWidget(self.result_label)

        main_layout.addLayout(row3)

        # 样式
        self.setStyleSheet(
            "FindReplaceBar{background:#FFF8E1;border-bottom:1px solid #FFE0B2;}"
            "QLineEdit{border:1px solid #CCC;border-radius:3px;padding:4px 8px;}"
            "QLineEdit:focus{border-color:#FFB300;}"
            "QPushButton{background:#FFF;border:1px solid #CCC;"
            "border-radius:3px;padding:4px 10px;}"
            "QPushButton:hover{background:#FFE0B2;}"
        )

    # ==================== 对外接口 ====================
    def show_for_editor(self, editor):
        """
        显示查找栏并绑定编辑器
        :param editor: QPlainTextEdit 或 QTextEdit 或 None
        """
        if editor is None:
            editor = self._find_editor_from_parent()
            if editor is None:
                QMessageBox.information(
                    self, "提示", "当前文档不支持查找替换"
                )
                return
        self._editor = editor
        self.show()

        # 如果编辑器有选中文字，自动填入
        cursor = editor.textCursor()
        if cursor.hasSelection():
            selected = cursor.selectedText()
            if selected and len(selected) < 200:
                self.find_input.setText(selected)

        self.find_input.setFocus()
        self.find_input.selectAll()

    def set_editor(self, editor):
        """直接绑定编辑器（不显示）"""
        self._editor = editor

    # ==================== 内部工具 ====================
    def _find_editor_from_parent(self):
        """从父窗口查找当前活动的编辑器"""
        p = self.parent()
        while p:
            if hasattr(p, '_edit_mode') and hasattr(p, 'markdown_editor'):
                if p._edit_mode == "markdown":
                    return p.markdown_editor
                else:
                    return p.rich_editor
            p = p.parent()
        return None

    def _on_search_text_changed(self, text):
        """查找文本变化时清空结果提示"""
        if text != self._last_search:
            self.result_label.setText("")

    def _on_regex_changed(self):
        """切换到正则模式时给出提示"""
        if self.regex_check.isChecked():
            self.find_input.setPlaceholderText(
                "输入正则表达式，如 \\d+ 或 [A-Z]+"
            )
        else:
            self.find_input.setPlaceholderText("输入要查找的内容...")

    def _get_search_text(self):
        """获取当前查找文本"""
        text = self.find_input.text()
        if not text:
            return None
        return text

    def _build_pattern(self, text):
        """构造正则模式"""
        if self.regex_check.isChecked():
            # 正则模式：直接使用
            flags = 0 if self.case_check.isChecked() else re.IGNORECASE
            try:
                return re.compile(text, flags)
            except re.error as e:
                self.result_label.setText(f"⚠ 正则错误：{e}")
                return None
        else:
            # 普通模式：转义特殊字符
            pattern = re.escape(text)
            if self.word_check.isChecked():
                pattern = r'\b' + pattern + r'\b'
            flags = 0 if self.case_check.isChecked() else re.IGNORECASE
            return re.compile(pattern, flags)

    # ==================== 查找 ====================
    def find_next(self):
        """查找下一个"""
        if not self._editor:
            self._editor = self._find_editor_from_parent()
        if not self._editor:
            return

        text = self._get_search_text()
        if not text:
            return

        pattern = self._build_pattern(text)
        if not pattern:
            return

        content = self._editor.toPlainText()
        cursor = self._editor.textCursor()
        start_pos = cursor.selectionEnd()

        match = pattern.search(content, start_pos)
        if not match:
            # 从头再找一次
            match = pattern.search(content, 0)
            if not match:
                self.result_label.setText("未找到")
                self._clear_selection_highlight()
                return
            else:
                self.result_label.setText("已循环到开头")

        # 选中匹配内容
        self._select_range(match.start(), match.end())
        self._last_search = text

    def find_prev(self):
        """查找上一个"""
        if not self._editor:
            self._editor = self._find_editor_from_parent()
        if not self._editor:
            return

        text = self._get_search_text()
        if not text:
            return

        pattern = self._build_pattern(text)
        if not pattern:
            return

        content = self._editor.toPlainText()
        cursor = self._editor.textCursor()
        start_pos = cursor.selectionStart()

        # 在 start_pos 之前查找所有匹配
        matches = list(pattern.finditer(content[:start_pos]))
        if not matches:
            # 从头查找全部，取最后一个
            all_matches = list(pattern.finditer(content))
            if not all_matches:
                self.result_label.setText("未找到")
                return
            match = all_matches[-1]
            self.result_label.setText("已循环到结尾")
        else:
            match = matches[-1]

        self._select_range(match.start(), match.end())
        self._last_search = text

    def _select_range(self, start, end):
        """选中编辑器中指定位置的内容"""
        if not self._editor:
            return
        cursor = self._editor.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        self._editor.setTextCursor(cursor)
        # 滚动到可见
        self._editor.ensureCursorVisible()

    def _clear_selection_highlight(self):
        """清除选中状态"""
        if self._editor:
            cursor = self._editor.textCursor()
            cursor.clearSelection()
            self._editor.setTextCursor(cursor)

    # ==================== 替换 ====================
    def replace_one(self):
        """替换当前选中"""
        if not self._editor:
            self._editor = self._find_editor_from_parent()
        if not self._editor:
            return

        text = self._get_search_text()
        if not text:
            return

        replace_text = self.replace_input.text()
        cursor = self._editor.textCursor()

        if not cursor.hasSelection():
            self.find_next()
            return

        # 校验当前选中是否匹配
        selected = cursor.selectedText()
        pattern = self._build_pattern(text)
        if not pattern:
            return

        if not pattern.fullmatch(selected):
            # 不匹配就重新查找
            self.find_next()
            return

        # 替换
        cursor.insertText(replace_text)
        self.result_label.setText("已替换 1 处")
        # 继续查找下一个
        self.find_next()

    def replace_all(self):
        """全部替换"""
        if not self._editor:
            self._editor = self._find_editor_from_parent()
        if not self._editor:
            return

        text = self._get_search_text()
        if not text:
            return

        replace_text = self.replace_input.text()

        content = self._editor.toPlainText()
        pattern = self._build_pattern(text)
        if not pattern:
            return

        # 统计匹配数
        matches = list(pattern.finditer(content))
        if not matches:
            self.result_label.setText("未找到")
            return

        count = len(matches)

        # 使用 sub 替换全部
        new_content = pattern.sub(replace_text, content)

        # 保留光标位置
        cursor = self._editor.textCursor()
        pos = cursor.position()

        # 应用替换（用 beginEditBlock 保证可撤销）
        cursor.beginEditBlock()
        try:
            if isinstance(self._editor, QPlainTextEdit):
                self._editor.setPlainText(new_content)
            else:
                self._editor.setPlainText(new_content)
        finally:
            cursor.endEditBlock()

        # 恢复光标（尽量）
        cursor = self._editor.textCursor()
        if pos <= len(new_content):
            cursor.setPosition(pos)
            self._editor.setTextCursor(cursor)

        self.result_label.setText(f"已替换 {count} 处")

    # ==================== 键盘事件 ====================
    def keyPressEvent(self, event):
        """Esc 关闭；Enter 查找下一个"""
        if event.key() == Qt.Key_Escape:
            self.hide()
            if self._editor:
                self._editor.setFocus()
            return
        if event.key() == Qt.Key_F3:
            if event.modifiers() & Qt.ShiftModifier:
                self.find_prev()
            else:
                self.find_next()
            return
        super().keyPressEvent(event)