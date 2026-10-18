# beeoffice/plugins/beewrite_hyperlink.py
"""
蜜写超链接管理：扫描、列表、编辑、删除

v5.0.1 修复（P1-11）：
  - 文件头注释拼写修正：beewrite_hyperlink.py → beewrite_hyperlink.py
    （原文件名本身就是 beewrite_，仅注释少了一个 e）
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QLineEdit, QMessageBox,
    QFormLayout, QDialogButtonBox
)
from PySide6.QtGui import QTextCursor, QTextCharFormat, QColor
from PySide6.QtCore import Qt
from beeoffice.i18n import tr


class HyperlinkDialog(QDialog):
    """插入/编辑超链接对话框"""

    def __init__(self, parent=None, initial_text="",
                 initial_url="", show_text_field=True):
        super().__init__(parent)
        self.setWindowTitle(tr("auto.beewrite_hyperlink.2fd97d00", "🔗 超链接"))
        self.resize(400, 200)
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._text_edit = QLineEdit()
        self._text_edit.setText(initial_text)
        if show_text_field:
            form.addRow("显示文本:", self._text_edit)

        self._url_edit = QLineEdit()
        self._url_edit.setText(initial_url or "https://")
        self._url_edit.setPlaceholderText("https://example.com")
        form.addRow("链接地址:", self._url_edit)

        layout.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_ok(self):
        url = self._url_edit.text().strip()
        if not url or url == "https://":
            QMessageBox.warning(self, tr("auto.beewrite_hyperlink.ab3656a9", "提示"), tr("auto.beewrite_hyperlink.f9460ff0", "请输入有效的链接地址"))
            return
        self.accept()

    def get_text(self):
        return self._text_edit.text().strip()

    def get_url(self):
        return self._url_edit.text().strip()


class HyperlinkManagerDialog(QDialog):
    """超链接管理对话框：列出所有链接"""

    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self._editor = editor
        self.setWindowTitle(tr("auto.beewrite_hyperlink.895095e0", "🔗 超链接管理"))
        self.resize(560, 400)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(tr("auto.beewrite_hyperlink.bf3f1bb6", "当前文档中的超链接：")))

        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget{border:1px solid #DDD;border-radius:4px;}"
            "QListWidget::item{padding:6px;}"
            "QListWidget::item:selected{background:#FFF3E0;}"
        )
        self._list.itemDoubleClicked.connect(self._jump_to_link)
        layout.addWidget(self._list, 1)

        # 按钮栏
        bl = QHBoxLayout()

        btn_jump = QPushButton(tr("auto.beewrite_hyperlink.c0bd0f2c", "📍 跳转"))
        btn_jump.clicked.connect(self._jump_to_link)
        bl.addWidget(btn_jump)

        btn_edit = QPushButton(tr("auto.beewrite_hyperlink.b186d065", "✏️ 编辑"))
        btn_edit.clicked.connect(self._edit_link)
        bl.addWidget(btn_edit)

        btn_remove = QPushButton(tr("auto.beewrite_hyperlink.1173260e", "🗑️ 移除链接"))
        btn_remove.clicked.connect(self._remove_link)
        bl.addWidget(btn_remove)

        bl.addStretch()

        btn_close = QPushButton(tr("auto.beewrite_hyperlink.6c14bd7f", "关闭"))
        btn_close.clicked.connect(self.accept)
        bl.addWidget(btn_close)

        layout.addLayout(bl)

        self._refresh_list()

    def _refresh_list(self):
        """扫描编辑器中所有超链接"""
        self._list.clear()
        self._links = []

        doc = self._editor.document()
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                fragment = it.fragment()
                if fragment.isValid():
                    fmt = fragment.charFormat()
                    if fmt.isAnchor():
                        href = fmt.anchorHref()
                        if href:
                            self._links.append({
                                "text": fragment.text(),
                                "url": href,
                                "pos": fragment.position(),
                                "len": fragment.length(),
                            })
                it += 1
            block = block.next()

        for link in self._links:
            item = QListWidgetItem(
                f"🔗 {link['text'][:40]}  →  {link['url']}"
            )
            self._list.addItem(item)

        if not self._links:
            item = QListWidgetItem(tr("auto.beewrite_hyperlink.50b9da5c", "（当前文档没有超链接）"))
            item.setFlags(Qt.NoItemFlags)
            self._list.addItem(item)

    def _jump_to_link(self):
        idx = self._list.currentRow()
        if idx < 0 or idx >= len(self._links):
            return
        link = self._links[idx]
        cursor = self._editor.textCursor()
        cursor.setPosition(link["pos"])
        cursor.setPosition(
            link["pos"] + link["len"], QTextCursor.KeepAnchor
        )
        self._editor.setTextCursor(cursor)
        self._editor.ensureCursorVisible()
        self._editor.setFocus()

    def _edit_link(self):
        idx = self._list.currentRow()
        if idx < 0 or idx >= len(self._links):
            return
        link = self._links[idx]

        dlg = HyperlinkDialog(
            self, initial_text=link["text"],
            initial_url=link["url"]
        )
        if dlg.exec() != QDialog.Accepted:
            return

        new_text = dlg.get_text()
        new_url = dlg.get_url()

        cursor = self._editor.textCursor()
        cursor.setPosition(link["pos"])
        cursor.setPosition(
            link["pos"] + link["len"], QTextCursor.KeepAnchor
        )

        fmt = QTextCharFormat()
        fmt.setAnchor(True)
        fmt.setAnchorHref(new_url)
        fmt.setForeground(QColor("#1565C0"))
        fmt.setFontUnderline(True)
        cursor.insertText(new_text, fmt)

        self._refresh_list()

    def _remove_link(self):
        idx = self._list.currentRow()
        if idx < 0 or idx >= len(self._links):
            return
        link = self._links[idx]

        cursor = self._editor.textCursor()
        cursor.setPosition(link["pos"])
        cursor.setPosition(
            link["pos"] + link["len"], QTextCursor.KeepAnchor
        )

        # 保留文本，去除链接格式
        fmt = QTextCharFormat()
        fmt.setAnchor(False)
        fmt.setAnchorHref("")
        fmt.setForeground(QColor("#333"))
        fmt.setFontUnderline(False)
        cursor.mergeCharFormat(fmt)

        self._refresh_list()