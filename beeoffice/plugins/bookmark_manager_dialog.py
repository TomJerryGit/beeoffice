# beeoffice/plugins/bookmark_manager_dialog.py
"""PDF 书签管理（S3）：列表/改标题/改页码/删除。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from beeoffice.pdf_tools import PdfToolError, delete_bookmark, list_bookmarks, update_bookmark


class BookmarkManagerDialog(QDialog):
    def __init__(self, pdf_path, out_path=None, parent=None):
        super().__init__(parent)
        self._src = Path(pdf_path)
        self._out = Path(out_path) if out_path else None
        self._bookmarks = []
        self.setWindowTitle("🔖 书签管理")
        self.resize(560, 460)

        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._on_select)
        self.title_edit = QLineEdit()
        self.page_spin = QSpinBox()
        self.page_spin.setRange(1, 9999)
        self.status = QLabel("")

        form = QHBoxLayout()
        form.addWidget(QLabel("标题:"))
        form.addWidget(self.title_edit, 1)
        form.addWidget(QLabel("页码:"))
        form.addWidget(self.page_spin)
        save_btn = QPushButton("保存修改")
        save_btn.clicked.connect(self._save_one)
        del_btn = QPushButton("删除")
        del_btn.clicked.connect(self._delete_one)
        reload_btn = QPushButton("重新加载")
        reload_btn.clicked.connect(self.reload)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addWidget(save_btn)
        buttons.addWidget(del_btn)
        buttons.addWidget(reload_btn)
        buttons.addStretch()
        buttons.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.list, 1)
        layout.addLayout(form)
        layout.addLayout(buttons)
        layout.addWidget(self.status)
        self.reload()

    def _target(self) -> Path:
        if self._out is None:
            self._out = self._src.with_name(self._src.stem + "_bookmarks.pdf")
        return self._out

    def reload(self):
        try:
            self._bookmarks = list_bookmarks(self._src)
        except PdfToolError as e:
            self.status.setText(f"读取失败: {e}")
            self._bookmarks = []
        self.list.clear()
        for bm in self._bookmarks:
            self.list.addItem(f"{bm['title']}  (第 {bm['page']} 页)")
        self.status.setText(f"共 {len(self._bookmarks)} 条书签")

    def _on_select(self, row):
        if 0 <= row < len(self._bookmarks):
            bm = self._bookmarks[row]
            self.title_edit.setText(bm["title"])
            self.page_spin.setValue(bm["page"])

    def _save_one(self):
        row = self.list.currentRow()
        if not 0 <= row < len(self._bookmarks):
            return
        try:
            update_bookmark(
                self._src, self._target(), row,
                title=self.title_edit.text(), page=self.page_spin.value(),
            )
            self._src = self._target()
            self.reload()
            self.status.setText("已保存修改")
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "保存失败", str(e))

    def _delete_one(self):
        row = self.list.currentRow()
        if not 0 <= row < len(self._bookmarks):
            return
        try:
            delete_bookmark(self._src, self._target(), row)
            self._src = self._target()
            self.reload()
            self.status.setText("已删除")
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "删除失败", str(e))
