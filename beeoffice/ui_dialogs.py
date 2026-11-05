# beeoffice/ui_dialogs.py
"""通用错误对话框：文本可选中、详情可复制。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton


def show_error(parent, title: str, text: str, details: str = "") -> None:
    """显示可复制信息的错误对话框。

    - 正文支持鼠标/键盘选择；
    - details 放入“显示详情”；
    - 额外提供“复制详情”按钮。
    """
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Critical)
    box.setWindowTitle(title)
    box.setText(text)
    box.setTextInteractionFlags(
        Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
    )
    if details:
        box.setDetailedText(details)

    copy_btn = QPushButton("复制详情")
    box.addButton(copy_btn, QMessageBox.ActionRole)
    copy_btn.clicked.connect(
        lambda: QApplication.clipboard().setText(
            f"{text}\n\n{details}".strip()
        )
    )
    box.addButton(QMessageBox.Ok)
    box.exec()
