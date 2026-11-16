"""PDF 页面管理器：缩略图拖拽排序、删除、旋转、另存。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QVBoxLayout, QAbstractItemView,
)

from beeoffice.pdf_backend import get_backend


def build_reordered_pdf(src, out, order, rotations=None):
    """按 order 重排页面，可选旋转角度（90 的倍数）。"""
    from pypdf import PdfReader, PdfWriter
    reader = PdfReader(str(src))
    writer = PdfWriter()
    rotations = rotations or {}
    for idx in order:
        if idx < 0 or idx >= len(reader.pages):
            continue
        page = reader.pages[idx]
        angle = int(rotations.get(idx, 0)) % 360
        if angle:
            page.rotate(angle)
        writer.add_page(page)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        writer.write(f)
    return str(out)


class PDFPageManagerDialog(QDialog):
    """当前 PDF 的页面缩略图管理器。"""

    def __init__(self, src: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PDF 页面管理")
        self.resize(760, 620)
        self._src = src
        self._backend = get_backend()
        self._rotations = {}
        self._deleted = set()
        self.output_path = None
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("拖拽缩略图排序；选中后可删除/旋转。"))
        self._list = QListWidget()
        self._list.setDragDropMode(QAbstractItemView.InternalMove)
        self._list.setIconSize(QSize(105, 140))
        layout.addWidget(self._list, 1)
        row = QHBoxLayout()
        for text, slot in (
            ("删除", self._delete_selected),
            ("顺时针旋转", self._rotate_selected),
            ("更多页面工具…", self._open_toolbox),
        ):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch()
        layout.addLayout(row)
        btns = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        self._load()

    def _load(self):
        self._list.clear()
        try:
            count = self._backend.page_count(self._src)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "页面管理", f"无法读取 PDF：{e}")
            return
        import os
        import tempfile
        for i in range(count):
            try:
                fd, tmp = tempfile.mkstemp(suffix=".png")
                os.close(fd)
                self._backend.render_page_png(self._src, i, tmp, scale=0.2)
                pm = QPixmap(tmp)
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                item = QListWidgetItem(QIcon(pm), f"第 {i + 1} 页")
            except Exception:  # noqa: BLE001
                item = QListWidgetItem(f"第 {i + 1} 页")
            item.setData(Qt.UserRole, i)
            self._list.addItem(item)

    def _selected(self):
        return self._list.currentItem()

    def _delete_selected(self):
        item = self._selected()
        if item is None:
            return
        idx = int(item.data(Qt.UserRole))
        self._deleted.add(idx)
        self._list.takeItem(self._list.row(item))

    def _rotate_selected(self):
        item = self._selected()
        if item is None:
            return
        idx = int(item.data(Qt.UserRole))
        self._rotations[idx] = (self._rotations.get(idx, 0) + 90) % 360
        item.setText(f"第 {idx + 1} 页（旋转 {self._rotations[idx]}°）")

    def _open_toolbox(self):
        from beeoffice.plugins.pdf_toolbox_dialog import PDFToolboxDialog
        dlg = PDFToolboxDialog(self)
        dlg.exec()

    def _save(self):
        order = [
            int(self._list.item(i).data(Qt.UserRole))
            for i in range(self._list.count())
        ]
        if not order:
            QMessageBox.warning(self, "页面管理", "至少保留一页。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "另存为新 PDF", "pages.pdf", "PDF (*.pdf)"
        )
        if not path:
            return
        try:
            self.output_path = build_reordered_pdf(
                self._src, path, order, self._rotations
            )
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "页面管理", f"保存失败：{e}")
            return
        self.accept()
