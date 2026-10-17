# beeoffice/plugins/beesheet_delegate.py
"""
蜜算单元格编辑器委托（含下拉验证和批注三角）
"""
import pandas as pd
from PySide6.QtWidgets import (
    QStyledItemDelegate, QLineEdit, QComboBox, QAbstractItemDelegate
)
from PySide6.QtCore import Qt, QEvent, QPoint
from PySide6.QtGui import QColor, QPolygon

from beeoffice.plugins.beesheet_commands import EditCellCommand


class CellEditorDelegate(QStyledItemDelegate):
    """单元格编辑器委托"""

    def __init__(self, sheet_view, parent=None):
        super().__init__(parent)
        self._sheet = sheet_view
        self._old_value = None
        self._current_index = None
        self._editor_is_combo = False

    def createEditor(self, parent, option, index):
        """创建编辑器：有下拉验证时用 QComboBox，否则用 QLineEdit"""
        key = (index.row(), index.column())
        options = self._sheet._data_validations.get(key)

        if isinstance(options, list) and options:
            editor = QComboBox(parent)
            editor.addItems([""] + options)
            editor.setStyleSheet(
                "QComboBox{background:#FFF;border:2px solid #FFB300;"
                "padding:2px;font-size:14px;}"
            )
            self._current_index = index
            self._old_value = self._sheet.model.get_value(
                index.row(), index.column()
            )
            self._editor_is_combo = True
            return editor

        self._editor_is_combo = False
        editor = QLineEdit(parent)
        editor.setFrame(False)
        editor.setStyleSheet(
            "QLineEdit{background:#FFF;border:2px solid #FFB300;"
            "padding:2px;font-size:14px;}"
        )
        editor.installEventFilter(self)
        self._current_index = index
        self._old_value = self._sheet.model.get_value(
            index.row(), index.column()
        )
        return editor

    def setEditorData(self, editor, index):
        """将模型数据填入编辑器"""
        key = (index.row(), index.column())

        if isinstance(editor, QComboBox):
            val = self._sheet.model.get_value(index.row(), index.column())
            text = str(val) if not pd.isna(val) else ""
            i = editor.findText(text)
            if i >= 0:
                editor.setCurrentIndex(i)
            return

        # 优先显示公式原文
        if key in self._sheet._formula_cells:
            editor.setText(self._sheet._formula_cells[key])
        else:
            val = self._sheet.model.get_value(index.row(), index.column())
            editor.setText(str(val) if not pd.isna(val) else "")
        editor.selectAll()

    def setModelData(self, editor, model, index):
        """将编辑器数据写回模型"""
        if isinstance(editor, QComboBox):
            new_val = editor.currentText()
        else:
            new_val = editor.text()

        old_val = self._old_value

        if str(new_val) != str(old_val):
            # 压入撤销栈
            self._sheet._push_command(
                EditCellCommand(index.row(), index.column(), old_val, new_val)
            )
            model.setData(index, new_val)

            # 记录/清除公式
            key = (index.row(), index.column())
            if isinstance(new_val, str) and new_val.startswith('='):
                self._sheet._formula_cells[key] = new_val
            else:
                self._sheet._formula_cells.pop(key, None)

            # 触发依赖公式重算
            self._sheet._recalc_formulas()
            self._sheet._dirty = True
            self._sheet._update_status()

    def eventFilter(self, editor, event):
        """处理编辑器键盘事件（Esc 取消、Enter 提交、Tab 移到下一格）"""
        # QComboBox 交给父类处理
        if isinstance(editor, QComboBox):
            return super().eventFilter(editor, event)

        if event.type() == QEvent.KeyPress:
            key = event.key()
            if key == Qt.Key_Escape:
                # Esc：恢复原值并关闭
                editor.setText(
                    str(self._old_value)
                    if not pd.isna(self._old_value) else ""
                )
                self.closeEditor.emit(editor, QAbstractItemDelegate.NoHint)
                return True
            elif key in (Qt.Key_Enter, Qt.Key_Return):
                # Enter：提交并关闭
                self.commitData.emit(editor)
                self.closeEditor.emit(
                    editor, QAbstractItemDelegate.SubmitModelCache
                )
                return True
            elif key == Qt.Key_Tab:
                # Tab：提交并跳到下一格
                self.commitData.emit(editor)
                self.closeEditor.emit(
                    editor, QAbstractItemDelegate.SubmitModelCache
                )
                idx = self._current_index
                if idx.isValid():
                    new_idx = idx.siblingAtColumn(idx.column() + 1)
                    if not new_idx.isValid():
                        new_idx = idx.siblingAtRow(
                            idx.row() + 1
                        ).siblingAtColumn(0)
                    if new_idx.isValid():
                        self._sheet.table_view.setCurrentIndex(new_idx)
                        self._sheet.table_view.edit(new_idx)
                return True
        return super().eventFilter(editor, event)

    def paint(self, painter, option, index):
        """重绘单元格：在原内容上叠加批注小三角"""
        super().paint(painter, option, index)

        if hasattr(self._sheet, '_cell_comments'):
            key = (index.row(), index.column())
            if key in self._sheet._cell_comments:
                painter.save()
                painter.setBrush(QColor(255, 87, 34))
                painter.setPen(Qt.NoPen)
                rect = option.rect
                size = 6
                points = [
                    QPoint(rect.right() - size, rect.top()),
                    QPoint(rect.right(), rect.top()),
                    QPoint(rect.right(), rect.top() + size),
                ]
                painter.drawPolygon(QPolygon(points))
                painter.restore()