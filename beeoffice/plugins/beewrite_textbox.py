# beeoffice/plugins/beewrite_textbox.py
"""
蜜写文本框：用 QTextFrame 实现静态文本框（可设置背景色、边框、内边距）

v5.0.1 修复（P1-11）：
  - 文件头注释拼写修正：beewrite_textbox.py → beewrite_textbox.py
    （原文件名本身就是 beewrite_，仅注释少了一个 e）
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QDialogButtonBox, QPushButton, QComboBox, QSpinBox,
    QColorDialog, QCheckBox, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QColor, QTextCursor, QTextFrameFormat, QTextLength
)
from beeoffice.i18n import tr


class TextBoxDialog(QDialog):
    """文本框属性对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("auto.beewrite_textbox.a2d3c862", "📦 插入文本框"))
        self.resize(400, 380)

        self._bg_color = QColor("#FFF8E1")
        self._border_color = QColor("#FFB300")

        layout = QVBoxLayout(self)
        form = QFormLayout()

        # 宽高
        self._width_combo = QComboBox()
        self._width_combo.addItems(["100%", "80%", "60%", "50%", "自定义"])
        form.addRow("宽度:", self._width_combo)

        width_row = QHBoxLayout()
        self._width_spin = QSpinBox()
        self._width_spin.setRange(20, 2000)
        self._width_spin.setValue(200)
        self._width_spin.setSuffix(" px")
        width_row.addWidget(self._width_spin)
        form.addRow("自定义宽度:", width_row)

        # 边框
        self._border_spin = QSpinBox()
        self._border_spin.setRange(0, 10)
        self._border_spin.setValue(1)
        form.addRow("边框宽度:", self._border_spin)

        # 边框颜色
        self._border_btn = QPushButton(tr("auto.beewrite_textbox.ad2b9430", "选择边框颜色"))
        self._border_btn.setStyleSheet(
            f"QPushButton{{background:{self._border_color.name()};"
            f"padding:6px;border:1px solid #CCC;border-radius:3px;}}"
        )
        self._border_btn.clicked.connect(self._pick_border)
        form.addRow("边框颜色:", self._border_btn)

        # 背景色
        self._bg_btn = QPushButton(tr("auto.beewrite_textbox.5bd1333a", "选择背景色"))
        self._bg_btn.setStyleSheet(
            f"QPushButton{{background:{self._bg_color.name()};"
            f"padding:6px;border:1px solid #CCC;border-radius:3px;}}"
        )
        self._bg_btn.clicked.connect(self._pick_bg)
        form.addRow("背景色:", self._bg_btn)

        # 内边距
        self._padding_spin = QSpinBox()
        self._padding_spin.setRange(0, 50)
        self._padding_spin.setValue(8)
        form.addRow("内边距:", self._padding_spin)

        # 圆角（暂不支持，作为提示）
        self._round_check = QCheckBox(tr("auto.beewrite_textbox.ec911e7b", "圆角边框（不支持，仅提示）"))
        self._round_check.setEnabled(False)
        form.addRow(self._round_check)

        layout.addLayout(form)

        # 提示
        tip = QLabel(
            "💡 文本框是静态的，插入后内容在此框内输入。\n"
            "Qt 不支持拖动位置，也不能浮动于文字之上。"
        )
        tip.setStyleSheet(
            "QLabel{color:#666;font-size:11px;padding:8px;"
            "background:#FFF8E1;border-radius:4px;}"
        )
        tip.setWordWrap(True)
        layout.addWidget(tip)

        # 按钮
        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _pick_border(self):
        c = QColorDialog.getColor(self._border_color)
        if c.isValid():
            self._border_color = c
            self._border_btn.setStyleSheet(
                f"QPushButton{{background:{c.name()};"
                f"padding:6px;border:1px solid #CCC;"
                f"border-radius:3px;}}"
            )

    def _pick_bg(self):
        c = QColorDialog.getColor(self._bg_color)
        if c.isValid():
            self._bg_color = c
            self._bg_btn.setStyleSheet(
                f"QPushButton{{background:{c.name()};"
                f"padding:6px;border:1px solid #CCC;"
                f"border-radius:3px;}}"
            )

    def get_config(self):
        """返回配置字典"""
        width_text = self._width_combo.currentText()
        if width_text == "自定义":
            width_length = QTextLength(
                QTextLength.FixedLength,
                self._width_spin.value()
            )
        else:
            pct = float(width_text.replace("%", ""))
            width_length = QTextLength(
                QTextLength.PercentageLength, pct
            )
        return {
            "width": width_length,
            "border": self._border_spin.value(),
            "border_color": self._border_color,
            "bg_color": self._bg_color,
            "padding": self._padding_spin.value(),
        }


def insert_textbox(rich_editor, config):
    """
    在富文本编辑器中插入文本框
    :param rich_editor: RichTextEditor 实例
    :param config: TextBoxDialog.get_config() 的返回值
    """
    cursor = rich_editor.textCursor()
    # 先换行，保证框在独立段落
    cursor.insertBlock()

    frame_format = QTextFrameFormat()
    frame_format.setBorder(config["border"])
    frame_format.setBorderStyle(QTextFrameFormat.BorderStyle_Solid)
    frame_format.setBorderBrush(config["border_color"])
    frame_format.setBackground(config["bg_color"])
    frame_format.setPadding(config["padding"])
    frame_format.setWidth(config["width"])
    frame_format.setMargin(6)

    frame = cursor.insertFrame(frame_format)
    inner_cursor = frame.firstCursorPosition()
    inner_cursor.insertText("在此输入文本框内容...")

    # 选中占位文字，方便直接覆盖
    inner_cursor.select(QTextCursor.BlockUnderCursor)
    rich_editor.setTextCursor(inner_cursor)