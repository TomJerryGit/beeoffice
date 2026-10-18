# beeoffice/plugins/beesheet_style_mixin.py
"""
蜜算样式功能 Mixin：单元格格式、表格样式、字体、对齐、数字格式
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QComboBox, QSpinBox,
    QCheckBox, QDialogButtonBox, QMenu, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from beeoffice.i18n import tr


class StyleMixin:
    """样式相关功能的 Mixin"""

    # ==================== 选中单元格获取 ====================
    def _get_selected_indexes(self):
        """获取当前选中单元格的索引列表"""
        sel = self.table_view.selectionModel().selection()
        if not sel:
            return []
        return sel.indexes()

    # ==================== 通用格式应用 ====================
    def _apply_format_to_selection(self, key, value):
        """将格式应用到所有选中单元格"""
        indexes = self._get_selected_indexes()
        if not indexes:
            return
        for idx in indexes:
            k = (idx.row(), idx.column())
            if k not in self._cell_formats:
                self._cell_formats[k] = {}
            self._cell_formats[k][key] = value
            # 宏录制（阶段三 #8）：格式动作也要能录下来
            try:
                from beeoffice.plugins.macro_recorder import RECORDER
                RECORDER.record_format(idx.row(), idx.column(), key, value)
            except Exception:
                pass
            self.model.dataChanged.emit(idx, idx)

    # ==================== 加粗/斜体/下划线 ====================
    def _toggle_cell_bold(self):
        """切换加粗状态"""
        indexes = self._get_selected_indexes()
        if not indexes:
            return
        first = indexes[0]
        k = (first.row(), first.column())
        cur = self._cell_formats.get(k, {}).get('bold', False)
        new_val = not cur
        self._apply_format_to_selection('bold', new_val)
        self._fmt_bold_btn.setChecked(new_val)

    def _toggle_cell_italic(self):
        """切换斜体状态"""
        indexes = self._get_selected_indexes()
        if not indexes:
            return
        first = indexes[0]
        k = (first.row(), first.column())
        cur = self._cell_formats.get(k, {}).get('italic', False)
        new_val = not cur
        self._apply_format_to_selection('italic', new_val)
        self._fmt_italic_btn.setChecked(new_val)

    def _toggle_cell_underline(self):
        """切换下划线状态"""
        indexes = self._get_selected_indexes()
        if not indexes:
            return
        first = indexes[0]
        k = (first.row(), first.column())
        cur = self._cell_formats.get(k, {}).get('underline', False)
        new_val = not cur
        self._apply_format_to_selection('underline', new_val)
        self._fmt_underline_btn.setChecked(new_val)

    # ==================== 对齐 ====================
    def _align_cell_left(self):
        """左对齐"""
        self._apply_format_to_selection('align', 'left')

    def _align_cell_center(self):
        """居中对齐"""
        self._apply_format_to_selection('align', 'center')

    def _align_cell_right(self):
        """右对齐"""
        self._apply_format_to_selection('align', 'right')

    # ==================== 数字格式 ====================
    def _apply_num_format(self, text):
        """应用数字格式下拉框中选择的格式"""
        indexes = self._get_selected_indexes()
        if not indexes:
            return
        decimals = self._decimal_spin.value()
        for idx in indexes:
            k = (idx.row(), idx.column())
            if k not in self._cell_formats:
                self._cell_formats[k] = {}
            self._cell_formats[k]['number_format'] = text
            self._cell_formats[k]['decimals'] = decimals
            try:
                from beeoffice.plugins.macro_recorder import RECORDER
                RECORDER.record_format(idx.row(), idx.column(), 'number_format', text)
                RECORDER.record_format(idx.row(), idx.column(), 'decimals', decimals)
            except Exception:
                pass
            self.model.dataChanged.emit(idx, idx)

    # ==================== 按钮状态同步 ====================
    def _sync_format_buttons(self):
        """同步格式工具栏按钮状态到当前选中单元格"""
        indexes = self._get_selected_indexes()
        if not indexes:
            return
        first = indexes[0]
        k = (first.row(), first.column())
        fmt = self._cell_formats.get(k, {})

        self._fmt_bold_btn.blockSignals(True)
        self._fmt_bold_btn.setChecked(fmt.get('bold', False))
        self._fmt_bold_btn.blockSignals(False)

        self._fmt_italic_btn.blockSignals(True)
        self._fmt_italic_btn.setChecked(fmt.get('italic', False))
        self._fmt_italic_btn.blockSignals(False)

        self._fmt_underline_btn.blockSignals(True)
        self._fmt_underline_btn.setChecked(fmt.get('underline', False))
        self._fmt_underline_btn.blockSignals(False)

        if fmt.get('number_format'):
            self._num_format_combo.blockSignals(True)
            self._num_format_combo.setCurrentText(fmt['number_format'])
            self._num_format_combo.blockSignals(False)

        if fmt.get('decimals') is not None:
            self._decimal_spin.blockSignals(True)
            self._decimal_spin.setValue(fmt['decimals'])
            self._decimal_spin.blockSignals(False)

    # ==================== 单元格格式对话框 ====================
    def _show_cell_format_dialog(self):
        """打开"设置单元格格式"对话框"""
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("auto.beesheet_style_mixin.6c2df6ba", "设置单元格格式"))
        dlg.resize(400, 200)
        layout = QVBoxLayout(dlg)
        form = QFormLayout()

        num_type = QComboBox()
        num_type.addItems(
            ["常规", "数值", "货币", "日期", "百分比", "文本"]
        )
        form.addRow("分类:", num_type)

        decimals = QSpinBox()
        decimals.setRange(0, 10)
        decimals.setValue(2)
        form.addRow("小数位数:", decimals)

        separator = QCheckBox(tr("auto.beesheet_style_mixin.061b7e6f", "千分位分隔符"))
        form.addRow(separator)

        layout.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        btns.accepted.connect(
            lambda: self._apply_cell_format_dialog(
                num_type.currentText(), decimals.value(), dlg
            )
        )
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        dlg.exec()

    def _apply_cell_format_dialog(self, num_type, decimals, dlg):
        """应用单元格格式对话框的选择"""
        self._apply_format_to_selection('number_format', num_type)
        self._apply_format_to_selection('decimals', decimals)
        dlg.accept()
        self._set_status(tr("auto.beesheet_style_mixin.7065ed93", "格式已应用"), 3000)

    # ==================== 表格整体样式 ====================
    def _show_style_menu(self):
        """表格样式菜单"""
        menu = QMenu(self)

        presets = {
            "🐝 琥珀蜜蜂": {
                "header_bg": QColor(255, 179, 0, 220),
                "stripe_bg": QColor(255, 243, 224, 150),
                "stripe": True,
            },
            "🌊 海洋蓝": {
                "header_bg": QColor(33, 150, 243, 220),
                "stripe_bg": QColor(227, 242, 253, 150),
                "stripe": True,
            },
            "🌿 森林绿": {
                "header_bg": QColor(76, 175, 80, 220),
                "stripe_bg": QColor(232, 245, 233, 150),
                "stripe": True,
            },
            "🌅 日落橙": {
                "header_bg": QColor(255, 112, 67, 220),
                "stripe_bg": QColor(251, 233, 231, 150),
                "stripe": True,
            },
            "⚫ 极简灰": {
                "header_bg": QColor(80, 80, 80, 220),
                "stripe_bg": QColor(245, 245, 245, 150),
                "stripe": True,
            },
            "📄 纯白": {
                "header_bg": QColor(240, 240, 240, 220),
                "stripe_bg": None,
                "stripe": False,
            },
        }

        for name, style in presets.items():
            act = menu.addAction(name)
            act.triggered.connect(
                lambda checked=False, s=style:
                    self._apply_table_style(s)
            )

        menu.addSeparator()
        menu.addAction(tr("auto.beesheet_style_mixin.07ca0dad", "❌ 清除样式")).triggered.connect(
            lambda: self._apply_table_style(None)
        )
        menu.exec(self.sender().mapToGlobal(
            self.sender().rect().bottomLeft()
        ))

    def _apply_table_style(self, style):
        """应用表格整体样式"""
        self._table_style = style
        self.model._table_style_ref = style

        # 触发全表重绘
        if self.model.rowCount() > 0 and self.model.columnCount() > 0:
            self.model.dataChanged.emit(
                self.model.index(0, 0),
                self.model.index(
                    self.model.rowCount() - 1,
                    self.model.columnCount() - 1
                ),
                [Qt.BackgroundRole]
            )

        if style:
            self._set_status(tr("auto.beesheet_style_mixin.74b6868c", "✅ 已应用表格样式"), 2000)
        else:
            self._set_status(tr("auto.beesheet_style_mixin.7c785004", "已清除表格样式"), 2000)