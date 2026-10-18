# beeoffice/plugins/beewrite_paragraph_mixin.py
"""
蜜写段落格式与列表 Mixin

职责：
  - 字符底纹 / 字符边框
  - 段落格式（行距 / 缩进 / 段前后 / 对齐 / 大纲级别 / 段落底纹 / 段落边框）
  - 多级列表

依赖：
  - PySide6

本次更新：
  - 修复 setLineHeight 第二个参数类型问题：
    PySide6 6.6.0 要求第二个参数必须是 int，
    QTextBlockFormat.ProportionalHeight 是枚举对象，不能 int() 转换。
    改用 C++ 枚举对应的数字值（1 = ProportionalHeight，2 = FixedHeight）。
"""
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QCheckBox,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QMenu,
    QMessageBox,
    QColorDialog,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QFont,
    QColor,
    QTextCursor,
    QTextCharFormat,
    QTextBlockFormat,
    QTextListFormat,
)
from beeoffice.i18n import tr


# ==================== 常量 ====================
# QTextBlockFormat.LineHeightTypes 的 C++ 枚举值
# （PySide6 6.6.0 不接受枚举对象，只接受 int）
_LINE_HEIGHT_SINGLE = 0
_LINE_HEIGHT_PROPORTIONAL = 1
_LINE_HEIGHT_FIXED = 2
_LINE_HEIGHT_MINIMUM = 3
_LINE_HEIGHT_LINE_DISTANCE = 4


# ==================== ParagraphMixin ====================
class ParagraphMixin:
    """蜜写段落格式与列表 Mixin"""

    # ==================================================================
    # 字符底纹
    # ==================================================================
    def _show_char_shade_dialog(self):
        """字符底纹 / 字符边框设置对话框"""
        if self._edit_mode != "rich_text":
            QMessageBox.information(
                self, tr("auto.beewrite_paragraph_mixin.ab3656a9", "提示"), tr("auto.beewrite_paragraph_mixin.09b3badd", "请先切换到所见即所得模式")
            )
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(tr("auto.beewrite_paragraph_mixin.40e4a6af", "▦ 字符底纹"))
        dlg.resize(360, 260)
        layout = QVBoxLayout(dlg)
        form = QFormLayout()

        # ---------- 背景色 ----------
        bg_btn = QPushButton(tr("auto.beewrite_paragraph_mixin.5bd1333a", "选择背景色"))
        bg_color = {"value": None}

        def pick_bg():
            c = QColorDialog.getColor()
            if c.isValid():
                bg_color["value"] = c
                bg_btn.setStyleSheet(
                    f"QPushButton{{background:{c.name()};"
                    f"padding:6px;color:#000;border:1px solid #CCC;"
                    f"border-radius:3px;}}"
                )

        bg_btn.clicked.connect(pick_bg)
        form.addRow("底纹色:", bg_btn)

        # ---------- 文字色 ----------
        fg_btn = QPushButton(tr("auto.beewrite_paragraph_mixin.1589ddbd", "选择文字色"))
        fg_color = {"value": None}

        def pick_fg():
            c = QColorDialog.getColor()
            if c.isValid():
                fg_color["value"] = c
                fg_btn.setStyleSheet(
                    f"QPushButton{{background:{c.name()};"
                    f"padding:6px;color:#000;border:1px solid #CCC;"
                    f"border-radius:3px;}}"
                )

        fg_btn.clicked.connect(pick_fg)
        form.addRow("文字色:", fg_btn)

        # ---------- 加粗 / 下划线 ----------
        bold_check = QCheckBox(tr("auto.beewrite_paragraph_mixin.f670b2ad", "加粗"))
        form.addRow(bold_check)

        underline_check = QCheckBox(tr("auto.beewrite_paragraph_mixin.9bc18ae5", "下划线"))
        form.addRow(underline_check)

        layout.addLayout(form)

        # ---------- 提示 ----------
        tip = QLabel(
            tr("auto.beewrite_paragraph_mixin.ef29b058", "💡 提示：Qt 富文本不支持字符边框，底纹/颜色会立即生效。")
        )
        tip.setStyleSheet(
            "QLabel{color:#666;font-size:12px;padding:8px;"
            "background:#FFF8E1;border-radius:4px;}"
        )
        tip.setWordWrap(True)
        layout.addWidget(tip)

        # ---------- 确定 / 取消 ----------
        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )

        def on_ok():
            cursor = self.rich_editor.textCursor()
            if not cursor.hasSelection():
                QMessageBox.information(
                    dlg, tr("auto.beewrite_paragraph_mixin.ab3656a9", "提示"), tr("auto.beewrite_paragraph_mixin.1eaaa547", "请先选中要设置的文字")
                )
                return
            cursor.beginEditBlock()
            try:
                fmt = QTextCharFormat()
                if bg_color["value"]:
                    fmt.setBackground(bg_color["value"])
                if fg_color["value"]:
                    fmt.setForeground(fg_color["value"])
                if bold_check.isChecked():
                    fmt.setFontWeight(QFont.Bold)
                if underline_check.isChecked():
                    fmt.setFontUnderline(True)
                cursor.mergeCharFormat(fmt)
            finally:
                cursor.endEditBlock()
            self._set_status(tr("auto.beewrite_paragraph_mixin.a7d3cc7d", "✅ 字符底纹已应用"), 2000)
            dlg.accept()

        btns.accepted.connect(on_ok)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        dlg.exec()

    # ==================================================================
    # 段落格式对话框
    # ==================================================================
    def _show_paragraph_dialog(self):
        """段落格式设置对话框"""
        if self._edit_mode != "rich_text":
            QMessageBox.information(
                self, tr("auto.beewrite_paragraph_mixin.ab3656a9", "提示"), tr("auto.beewrite_paragraph_mixin.09b3badd", "请先切换到所见即所得模式")
            )
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(tr("auto.beewrite_paragraph_mixin.6c638dc4", "¶ 段落格式"))
        dlg.resize(420, 500)
        layout = QVBoxLayout(dlg)
        form = QFormLayout()

        # ---------- 对齐方式 ----------
        align_combo = QComboBox()
        align_combo.addItems([
            "左对齐", "居中", "右对齐", "两端对齐", "默认"
        ])
        form.addRow("对齐方式:", align_combo)

        # ---------- 大纲级别 ----------
        outline_combo = QComboBox()
        outline_combo.addItems([
            "正文", "标题 1", "标题 2", "标题 3", "标题 4"
        ])
        form.addRow("大纲级别:", outline_combo)

        # ---------- 行距 ----------
        line_spacing_combo = QComboBox()
        line_spacing_combo.addItems([
            "单倍行距", "1.15 倍", "1.5 倍", "2 倍", "固定值"
        ])
        form.addRow("行距:", line_spacing_combo)

        line_spacing_spin = QDoubleSpinBox()
        line_spacing_spin.setRange(8, 100)
        line_spacing_spin.setValue(12)
        line_spacing_spin.setSuffix(" pt")
        line_spacing_spin.setEnabled(False)
        form.addRow("固定值:", line_spacing_spin)

        def on_line_spacing_changed(text):
            line_spacing_spin.setEnabled(text == "固定值")

        line_spacing_combo.currentTextChanged.connect(
            on_line_spacing_changed
        )

        # ---------- 段前后距离 ----------
        before_spin = QDoubleSpinBox()
        before_spin.setRange(0, 100)
        before_spin.setValue(0)
        before_spin.setSuffix(" pt")
        form.addRow("段前距离:", before_spin)

        after_spin = QDoubleSpinBox()
        after_spin.setRange(0, 100)
        after_spin.setValue(0)
        after_spin.setSuffix(" pt")
        form.addRow("段后距离:", after_spin)

        # ---------- 左右缩进 ----------
        left_indent_spin = QDoubleSpinBox()
        left_indent_spin.setRange(0, 200)
        left_indent_spin.setValue(0)
        left_indent_spin.setSuffix(" pt")
        form.addRow("左缩进:", left_indent_spin)

        right_indent_spin = QDoubleSpinBox()
        right_indent_spin.setRange(0, 200)
        right_indent_spin.setValue(0)
        right_indent_spin.setSuffix(" pt")
        form.addRow("右缩进:", right_indent_spin)

        # ---------- 特殊格式（首行缩进 / 悬挂缩进） ----------
        first_line_combo = QComboBox()
        first_line_combo.addItems(["无", "首行缩进", "悬挂缩进"])
        form.addRow("特殊格式:", first_line_combo)

        first_line_spin = QDoubleSpinBox()
        first_line_spin.setRange(0, 100)
        first_line_spin.setValue(24)
        first_line_spin.setSuffix(" pt")
        first_line_spin.setEnabled(False)
        form.addRow("缩进值:", first_line_spin)

        def on_first_line_changed(text):
            first_line_spin.setEnabled(text != "无")

        first_line_combo.currentTextChanged.connect(on_first_line_changed)

        layout.addLayout(form)

        # ---------- 段落底纹 / 边框 ----------
        shade_form = QFormLayout()

        para_bg_btn = QPushButton(tr("auto.beewrite_paragraph_mixin.62e2b074", "选择段落底纹色"))
        para_bg_color = {"value": None}

        def pick_para_bg():
            c = QColorDialog.getColor()
            if c.isValid():
                para_bg_color["value"] = c
                para_bg_btn.setStyleSheet(
                    f"QPushButton{{background:{c.name()};"
                    f"padding:6px;color:#000;"
                    f"border:1px solid #CCC;border-radius:3px;}}"
                )

        para_bg_btn.clicked.connect(pick_para_bg)
        shade_form.addRow("段落底纹:", para_bg_btn)

        para_border_combo = QComboBox()
        para_border_combo.addItems([
            "无边框", "上下边框", "左右边框", "全边框", "四边加粗"
        ])
        shade_form.addRow("段落边框:", para_border_combo)
        layout.addLayout(shade_form)

        # ---------- 预览 ----------
        preview_label = QLabel(
            "预览：\n这是一段用于预览段落格式的示例文字。\n"
            "调整上方参数可以看到格式变化效果。"
        )
        preview_label.setStyleSheet(
            "QLabel{background:#FAFAFA;padding:12px;"
            "border:1px solid #DDD;border-radius:4px;"
            "font-size:13px;line-height:1.5;}"
        )
        preview_label.setWordWrap(True)
        layout.addWidget(preview_label)

        # ---------- 确定 / 取消 ----------
        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )

        def on_ok():
            self._apply_paragraph_format(
                align_combo.currentText(),
                outline_combo.currentText(),
                line_spacing_combo.currentText(),
                line_spacing_spin.value(),
                before_spin.value(),
                after_spin.value(),
                left_indent_spin.value(),
                right_indent_spin.value(),
                first_line_combo.currentText(),
                first_line_spin.value(),
                para_bg_color["value"],
                para_border_combo.currentText(),
            )
            dlg.accept()

        btns.accepted.connect(on_ok)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        dlg.exec()

    # ==================================================================
    # 段落格式应用
    # ==================================================================
    def _apply_paragraph_format(
        self,
        align,
        outline,
        line_spacing,
        line_spacing_value,
        before,
        after,
        left_indent,
        right_indent,
        first_line_type,
        first_line_value,
        para_bg_color=None,
        para_border="无边框",
    ):
        """应用段落格式到当前选区（无选区时作用于当前段落）"""
        cursor = self.rich_editor.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.BlockUnderCursor)

        cursor.beginEditBlock()
        try:
            bf = QTextBlockFormat()

            # ---------- 对齐 ----------
            align_map = {
                "左对齐": Qt.AlignLeft,
                "居中": Qt.AlignCenter,
                "右对齐": Qt.AlignRight,
                "两端对齐": Qt.AlignJustify,
                "默认": Qt.AlignLeft,
            }
            bf.setAlignment(align_map.get(align, Qt.AlignLeft))

            # ---------- 大纲级别 ----------
            outline_map = {
                "正文": 0,
                "标题 1": 1,
                "标题 2": 2,
                "标题 3": 3,
                "标题 4": 4,
            }
            bf.setHeadingLevel(outline_map.get(outline, 0))

            # ---------- 行距 ----------
            # 关键修复：PySide6 6.6.0 的 setLineHeight 第二个参数必须是 int。
            # QTextBlockFormat.ProportionalHeight 是枚举对象，不能 int() 转换，
            # 直接用 C++ 枚举值：
            #   SingleHeight = 0
            #   ProportionalHeight = 1
            #   FixedHeight = 2
            #   MinimumHeight = 3
            #   LineDistanceHeight = 4
            spacing_map = {
                "单倍行距": 100.0,
                "1.15 倍": 115.0,
                "1.5 倍": 150.0,
                "2 倍": 200.0,
            }

            if line_spacing in spacing_map:
                bf.setLineHeight(
                    float(spacing_map[line_spacing]),
                    _LINE_HEIGHT_PROPORTIONAL,
                )
            elif line_spacing == "固定值":
                bf.setLineHeight(
                    float(line_spacing_value),
                    _LINE_HEIGHT_FIXED,
                )

            # ---------- 段前后 / 缩进 ----------
            bf.setTopMargin(float(before))
            bf.setBottomMargin(float(after))
            bf.setLeftMargin(float(left_indent))
            bf.setRightMargin(float(right_indent))

            # ---------- 首行 / 悬挂缩进 ----------
            if first_line_type == "首行缩进":
                bf.setTextIndent(float(first_line_value))
            elif first_line_type == "悬挂缩进":
                bf.setTextIndent(-float(first_line_value))
            else:
                bf.setTextIndent(0.0)

            # ---------- 段落底纹 ----------
            if para_bg_color:
                bf.setBackground(para_bg_color)

            cursor.mergeBlockFormat(bf)
        finally:
            cursor.endEditBlock()

        self._set_status(tr("auto.beewrite_paragraph_mixin.569491c8", "✅ 段落格式已应用"), 2000)

    # ==================================================================
    # 多级列表菜单
    # ==================================================================
    def _show_multilist_menu(self):
        """多级列表菜单"""
        if self._edit_mode != "rich_text":
            QMessageBox.information(
                self, tr("auto.beewrite_paragraph_mixin.ab3656a9", "提示"), tr("auto.beewrite_paragraph_mixin.09b3badd", "请先切换到所见即所得模式")
            )
            return
        menu = QMenu(self)
        menu.addAction(tr("auto.beewrite_paragraph_mixin.fbc8b5c0", "1. 数字 (1.)")).triggered.connect(
            lambda: self._apply_multilist_style("decimal")
        )
        menu.addAction(tr("auto.beewrite_paragraph_mixin.574311a0", "1) 括号数字")).triggered.connect(
            lambda: self._apply_multilist_style("paren")
        )
        menu.addAction(tr("auto.beewrite_paragraph_mixin.f206c91e", "① 圆圈数字")).triggered.connect(
            lambda: self._apply_multilist_style("circled")
        )
        menu.addAction(tr("auto.beewrite_paragraph_mixin.f26761f2", "Ⅰ. 罗马数字")).triggered.connect(
            lambda: self._apply_multilist_style("roman")
        )
        menu.addAction(tr("auto.beewrite_paragraph_mixin.6e55e336", "A. 大写字母")).triggered.connect(
            lambda: self._apply_multilist_style("upper_alpha")
        )
        menu.addAction(tr("auto.beewrite_paragraph_mixin.0d05b405", "a. 小写字母")).triggered.connect(
            lambda: self._apply_multilist_style("lower_alpha")
        )
        menu.addSeparator()
        menu.addAction(tr("auto.beewrite_paragraph_mixin.f54646da", "⬆️ 提升级别 (Shift+Tab)")).triggered.connect(
            self._multilist_promote
        )
        menu.addAction(tr("auto.beewrite_paragraph_mixin.a1736781", "⬇️ 降低级别 (Tab)")).triggered.connect(
            self._multilist_demote
        )
        menu.addSeparator()
        menu.addAction(tr("auto.beewrite_paragraph_mixin.8668326b", "❌ 取消列表")).triggered.connect(
            self._multilist_remove
        )

        sender = self.sender()
        if sender:
            menu.exec(sender.mapToGlobal(sender.rect().bottomLeft()))
        else:
            menu.exec(self.mapToGlobal(self.rect().center()))

    # ==================================================================
    # 多级列表应用
    # ==================================================================
    def _apply_multilist_style(self, style_name):
        """应用多级列表样式"""
        cursor = self.rich_editor.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.BlockUnderCursor)

        style_map = {
            "decimal": QTextListFormat.ListDecimal,
            "paren": QTextListFormat.ListDecimal,
            "circled": QTextListFormat.ListDecimal,
            "roman": QTextListFormat.ListUpperRoman,
            "upper_alpha": QTextListFormat.ListUpperAlpha,
            "lower_alpha": QTextListFormat.ListLowerAlpha,
        }
        list_style = style_map.get(style_name, QTextListFormat.ListDecimal)

        cursor.beginEditBlock()
        try:
            list_format = QTextListFormat()
            list_format.setStyle(list_style)
            list_format.setIndent(1)

            if style_name == "circled":
                list_format.setStyle(QTextListFormat.ListDecimal)
                list_format.setNumberPrefix("① ")
                list_format.setNumberSuffix("")
            elif style_name == "paren":
                list_format.setNumberPrefix("")
                list_format.setNumberSuffix(") ")
            elif style_name == "decimal":
                list_format.setNumberPrefix("")
                list_format.setNumberSuffix(". ")

            cursor.createList(list_format)
        finally:
            cursor.endEditBlock()

        self._set_status(tr("auto.beewrite_paragraph_mixin.10f1890f", "✅ 已应用多级列表样式"), 2000)

    # ==================================================================
    # 多级列表级别调整
    # ==================================================================
    def _multilist_promote(self):
        """提升列表级别（缩进减少一级）"""
        cursor = self.rich_editor.textCursor()
        list_obj = cursor.currentList()
        if not list_obj:
            return
        cursor.beginEditBlock()
        try:
            fmt = list_obj.format()
            indent = max(0, fmt.indent() - 1)
            fmt.setIndent(indent)
            list_obj.setFormat(fmt)
        finally:
            cursor.endEditBlock()

    def _multilist_demote(self):
        """降低列表级别（缩进增加一级）"""
        cursor = self.rich_editor.textCursor()
        list_obj = cursor.currentList()
        if not list_obj:
            return
        cursor.beginEditBlock()
        try:
            fmt = list_obj.format()
            fmt.setIndent(fmt.indent() + 1)
            list_obj.setFormat(fmt)
        finally:
            cursor.endEditBlock()

    def _multilist_remove(self):
        """取消当前列表样式"""
        cursor = self.rich_editor.textCursor()
        list_obj = cursor.currentList()
        if not list_obj:
            return
        cursor.beginEditBlock()
        try:
            block_format = cursor.blockFormat()
            block_format.setIndent(0)
            cursor.setBlockFormat(block_format)
            list_obj.remove(cursor.block())
        finally:
            cursor.endEditBlock()