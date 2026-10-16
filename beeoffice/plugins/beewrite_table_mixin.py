# beeoffice/plugins/beewrite_table_mixin.py
"""
蜜写表格 Mixin

职责：
  - 表格菜单
    * _show_table_menu
  - 行 / 列操作（工具栏 / 菜单入口）
    * _table_insert_row / _table_insert_col
    * _table_delete_row / _table_delete_col
  - 合并 / 拆分
    * _table_merge_cells / _table_split_cell
    * _cell_merge_toolbar / _cell_split_toolbar
  - 单元格颜色
    * _table_cell_bg / _table_cell_fg / _cell_bg_toolbar
  - 表格属性
    * _table_properties
  - 复制为 Markdown
    * _copy_table_as_markdown
  - 表格样式预设
    * _apply_table_style / _set_row_color / _set_table_cells_color
    * _set_three_line_borders / _make_cell_fmt
  - 单元格对齐
    * _cell_align / _apply_cell_align
  - Markdown 表格可视化编辑
    * _detect_md_table_at_cursor / _parse_md_table / _render_md_table
    * _replace_lines / _on_md_double_click
    * _md_get_table_context / _md_add_row_below / _md_add_row_above
    * _md_add_col_right / _md_add_col_left
  - Excel 数据插入
    * _insert_excel_data / _insert_from_beesheet / _insert_from_file
  - 基础插入（代理到 RichTextEditor）
    * _insert_table_dialog / _insert_horizontal_line
    * _insert_page_break / _insert_section_break / _insert_date

依赖：
  - PySide6（QMenu / QDialog / QFormLayout / QComboBox / QSpinBox /
             QDialogButtonBox / QColorDialog / QMessageBox / QPushButton /
             QApplication / QTextCursor / QTextCharFormat / QTextBlockFormat /
             QTextTableFormat / QFont / QColor / Qt）
  - beewrite_utils（detect_md_table_at_cursor / parse_md_table /
                    render_md_table）
  - beewrite_md_table_dialog（MarkdownTableEditorDialog）

说明：
  - 本 Mixin 处理「编辑器外部」的表格命令（工具栏 / 菜单 / Markdown 源码表格）
  - 「编辑器内部」的表格操作（Tab 跳格 / 右键菜单）由 RichTextEditor 负责
  - 不导入其他 beewrite_* Mixin，避免循环依赖
"""
from pathlib import Path

from PySide6.QtWidgets import (
    QMenu,
    QDialog,
    QFormLayout,
    QComboBox,
    QSpinBox,
    QDialogButtonBox,
    QColorDialog,
    QMessageBox,
    QPushButton,
    QApplication,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QFont,
    QColor,
    QTextCursor,
    QTextCharFormat,
    QTextBlockFormat,
    QTextTableFormat,
)

from beeoffice.plugins.beewrite_utils import (
    detect_md_table_at_cursor,
    parse_md_table,
    render_md_table,
)
from beeoffice.plugins.beewrite_md_table_dialog import (
    MarkdownTableEditorDialog,
)


# ==================== TableMixin ====================
class TableMixin:
    """蜜写表格 Mixin"""

    # ==================================================================
    # 单元格对齐：字符串 → Qt 常量映射
    # ==================================================================
    _ALIGN_MAP = {
        "left": Qt.AlignLeft,
        "center": Qt.AlignCenter,
        "right": Qt.AlignRight,
    }

    # ==================================================================
    # 表格菜单
    # ==================================================================
    def _show_table_menu(self):
        """表格操作下拉菜单"""
        menu = QMenu(self)

        menu.addAction("➕ 插入表格...").triggered.connect(
            self._insert_table_dialog
        )

        # ---------- 表格样式子菜单 ----------
        style_menu = menu.addMenu("🎨 表格样式")
        style_menu.addAction("⚪ 极简（无边框）").triggered.connect(
            lambda: self._apply_table_style("minimal")
        )
        style_menu.addAction("📏 三线表").triggered.connect(
            lambda: self._apply_table_style("three_line")
        )
        style_menu.addAction("🦓 斑马纹").triggered.connect(
            lambda: self._apply_table_style("zebra")
        )
        style_menu.addAction("📦 卡片式").triggered.connect(
            lambda: self._apply_table_style("card")
        )
        style_menu.addAction("🌙 深色").triggered.connect(
            lambda: self._apply_table_style("dark")
        )
        style_menu.addAction("🐝 琥珀金").triggered.connect(
            lambda: self._apply_table_style("amber")
        )

        # ---------- 若光标在表格中，显示更多操作 ----------
        table = None
        if self._edit_mode == "rich_text":
            cursor = self.rich_editor.textCursor()
            table = cursor.currentTable()

        if table:
            menu.addSeparator()
            menu.addAction("⬆️ 上方插入行").triggered.connect(
                lambda: self._table_insert_row(table, -1)
            )
            menu.addAction("⬇️ 下方插入行").triggered.connect(
                lambda: self._table_insert_row(table, 1)
            )
            menu.addSeparator()
            menu.addAction("⬅️ 左侧插入列").triggered.connect(
                lambda: self._table_insert_col(table, -1)
            )
            menu.addAction("➡️ 右侧插入列").triggered.connect(
                lambda: self._table_insert_col(table, 1)
            )
            menu.addSeparator()
            menu.addAction("🗑️ 删除当前行").triggered.connect(
                lambda: self._table_delete_row(table)
            )
            menu.addAction("🗑️ 删除当前列").triggered.connect(
                lambda: self._table_delete_col(table)
            )
            menu.addSeparator()
            menu.addAction("🔗 合并单元格").triggered.connect(
                lambda: self._table_merge_cells(table)
            )
            menu.addAction("🔲 拆分单元格").triggered.connect(
                lambda: self._table_split_cell(table)
            )
            menu.addSeparator()
            menu.addAction("🎨 单元格背景色").triggered.connect(
                lambda: self._table_cell_bg()
            )
            menu.addAction("🖍️ 单元格文字色").triggered.connect(
                lambda: self._table_cell_fg()
            )
            menu.addSeparator()
            menu.addAction("⚙️ 表格属性").triggered.connect(
                lambda: self._table_properties(table)
            )
            menu.addSeparator()
            menu.addAction("📋 复制为Markdown").triggered.connect(
                lambda: self._copy_table_as_markdown(table)
            )

        sender = self.sender()
        if sender:
            menu.exec(sender.mapToGlobal(sender.rect().bottomLeft()))
        else:
            menu.exec(self.mapToGlobal(self.rect().center()))

    # ==================================================================
    # 行 / 列操作
    # ==================================================================
    def _table_insert_row(self, table, pos):
        """在光标所在行的上方（pos<0）/ 下方（pos>0）插入行"""
        cursor = self.rich_editor.textCursor()
        cell = table.cellAt(cursor)
        if cell.isValid():
            insert_at = cell.row() + (0 if pos < 0 else 1)
            cursor.beginEditBlock()
            try:
                table.insertRows(insert_at, 1)
            finally:
                cursor.endEditBlock()

    def _table_insert_col(self, table, pos):
        """在光标所在列的左侧（pos<0）/ 右侧（pos>0）插入列"""
        cursor = self.rich_editor.textCursor()
        cell = table.cellAt(cursor)
        if cell.isValid():
            insert_at = cell.column() + (0 if pos < 0 else 1)
            cursor.beginEditBlock()
            try:
                table.insertColumns(insert_at, 1)
            finally:
                cursor.endEditBlock()

    def _table_delete_row(self, table):
        """删除光标所在行"""
        cursor = self.rich_editor.textCursor()
        cell = table.cellAt(cursor)
        if cell.isValid():
            if table.rows() <= 1:
                QMessageBox.information(self, "提示", "至少保留一行")
                return
            cursor.beginEditBlock()
            try:
                table.removeRows(cell.row(), 1)
            finally:
                cursor.endEditBlock()

    def _table_delete_col(self, table):
        """删除光标所在列"""
        cursor = self.rich_editor.textCursor()
        cell = table.cellAt(cursor)
        if cell.isValid():
            if table.columns() <= 1:
                QMessageBox.information(self, "提示", "至少保留一列")
                return
            cursor.beginEditBlock()
            try:
                table.removeColumns(cell.column(), 1)
            finally:
                cursor.endEditBlock()

    # ==================================================================
    # 合并 / 拆分
    # ==================================================================
    def _table_merge_cells(self, table):
        """合并当前选区所覆盖的单元格"""
        cursor = self.rich_editor.textCursor()
        if not cursor.hasSelection():
            QMessageBox.information(
                self, "提示", "请先按住鼠标选中要合并的单元格"
            )
            return
        try:
            start = cursor.selectionStart()
            end = cursor.selectionEnd()
            c1 = QTextCursor(self.rich_editor.document())
            c1.setPosition(start)
            c2 = QTextCursor(self.rich_editor.document())
            c2.setPosition(end)
            cell1 = table.cellAt(c1)
            cell2 = table.cellAt(c2)
            if cell1.isValid() and cell2.isValid():
                r1, c1_ = cell1.row(), cell1.column()
                r2, c2_ = cell2.row(), cell2.column()
                r_start, r_end = min(r1, r2), max(r1, r2)
                c_start, c_end = min(c1_, c2_), max(c1_, c2_)
                cursor.beginEditBlock()
                try:
                    table.mergeCells(
                        r_start, c_start,
                        r_end - r_start + 1,
                        c_end - c_start + 1,
                    )
                finally:
                    cursor.endEditBlock()
        except Exception as e:
            QMessageBox.warning(self, "合并失败", str(e))

    def _table_split_cell(self, table):
        """拆分光标所在的合并单元格"""
        cursor = self.rich_editor.textCursor()
        cell = table.cellAt(cursor)
        if cell.isValid():
            rowspan = cell.rowSpan()
            colspan = cell.colSpan()
            if rowspan > 1 or colspan > 1:
                cursor.beginEditBlock()
                try:
                    table.splitCell(
                        cell.row(), cell.column(), rowspan, colspan
                    )
                finally:
                    cursor.endEditBlock()
            else:
                QMessageBox.information(
                    self, "提示", "当前单元格没有合并，无需拆分"
                )

    def _cell_merge_toolbar(self):
        """工具栏「合并」按钮：优先处理光标所在表格"""
        if self._edit_mode != "rich_text":
            QMessageBox.information(
                self, "提示", "请先切换到所见即所得模式"
            )
            return
        cursor = self.rich_editor.textCursor()
        table = cursor.currentTable()
        if table:
            self._table_merge_cells(table)

    def _cell_split_toolbar(self):
        """工具栏「拆分」按钮：优先处理光标所在表格"""
        if self._edit_mode != "rich_text":
            QMessageBox.information(
                self, "提示", "请先切换到所见即所得模式"
            )
            return
        cursor = self.rich_editor.textCursor()
        table = cursor.currentTable()
        if table:
            self._table_split_cell(table)

    # ==================================================================
    # 单元格颜色
    # ==================================================================
    def _table_cell_bg(self):
        """设置单元格背景色"""
        col = QColorDialog.getColor()
        if col.isValid():
            cursor = self.rich_editor.textCursor()
            fmt = QTextCharFormat()
            fmt.setBackground(col)
            cursor.mergeCharFormat(fmt)

    def _table_cell_fg(self):
        """设置单元格文字色"""
        col = QColorDialog.getColor()
        if col.isValid():
            cursor = self.rich_editor.textCursor()
            fmt = QTextCharFormat()
            fmt.setForeground(col)
            cursor.mergeCharFormat(fmt)

    def _cell_bg_toolbar(self):
        """工具栏「底色」按钮"""
        if self._edit_mode != "rich_text":
            QMessageBox.information(
                self, "提示", "请先切换到所见即所得模式"
            )
            return
        self._table_cell_bg()

    # ==================================================================
    # 表格属性
    # ==================================================================
    def _table_properties(self, table):
        """表格属性对话框（对齐 / 边框 / 内边距 / 背景色）"""
        dlg = QDialog(self)
        dlg.setWindowTitle("⚙️ 表格属性")
        form = QFormLayout(dlg)

        # ---------- 对齐 ----------
        align_combo = QComboBox()
        align_combo.addItems(["左对齐", "居中", "右对齐"])
        form.addRow("对齐:", align_combo)

        # ---------- 边框宽度 ----------
        border_spin = QSpinBox()
        border_spin.setRange(0, 10)
        border_spin.setValue(table.format().border() or 1)
        form.addRow("边框宽度:", border_spin)

        # ---------- 单元格内边距 ----------
        cellpad_spin = QSpinBox()
        cellpad_spin.setRange(0, 30)
        cellpad_spin.setValue(table.format().cellPadding())
        form.addRow("单元格内边距:", cellpad_spin)

        # ---------- 背景色 ----------
        bg_btn = QPushButton("选择背景色")
        bg_color = {"value": None}

        def pick_bg():
            c = QColorDialog.getColor()
            if c.isValid():
                bg_color["value"] = c
                bg_btn.setStyleSheet(
                    f"QPushButton{{background:{c.name()};"
                    f"padding:4px;color:#000;}}"
                )

        bg_btn.clicked.connect(pick_bg)
        form.addRow("背景色:", bg_btn)

        # ---------- 按钮 ----------
        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        if dlg.exec() == QDialog.Accepted:
            fmt = table.format()
            align_map = {
                "左对齐": Qt.AlignLeft,
                "居中": Qt.AlignCenter,
                "右对齐": Qt.AlignRight,
            }
            fmt.setAlignment(align_map[align_combo.currentText()])
            fmt.setBorder(border_spin.value())
            fmt.setBorderStyle(QTextTableFormat.BorderStyle_Solid)
            fmt.setCellPadding(cellpad_spin.value())
            if bg_color["value"]:
                fmt.setBackground(bg_color["value"])
            table.setFormat(fmt)

    # ==================================================================
    # 复制为 Markdown
    # ==================================================================
    def _copy_table_as_markdown(self, table):
        """把光标所在表格复制为 Markdown 文本"""
        try:
            rows = table.rows()
            cols = table.columns()
            lines = []
            for r in range(rows):
                cells = []
                for c in range(cols):
                    cell = table.cellAt(r, c)
                    text = cell.firstCursorPosition().block().text()
                    cells.append(text.strip())
                lines.append("| " + " | ".join(cells) + " |")
                if r == 0:
                    lines.append("|" + "|".join(["---"] * cols) + "|")
            md = "\n".join(lines)
            QApplication.clipboard().setText(md)
            self._set_status("✅ 已复制为 Markdown 表格", 3000)
        except Exception as e:
            QMessageBox.warning(self, "复制失败", str(e))

    # ==================================================================
    # 表格样式预设
    # ==================================================================
    def _apply_table_style(self, style_name):
        """应用表格预设样式"""
        if self._edit_mode != "rich_text":
            QMessageBox.information(
                self, "提示", "请先切换到所见即所得模式"
            )
            return
        cursor = self.rich_editor.textCursor()
        table = cursor.currentTable()
        if not table:
            QMessageBox.information(self, "提示", "请把光标放在表格内")
            return

        try:
            fmt = QTextTableFormat()
            fmt.setCellPadding(6)
            fmt.setCellSpacing(0)
            fmt.setBorderStyle(QTextTableFormat.BorderStyle_Solid)
            fmt.setHeaderRowCount(1)

            if style_name == "minimal":
                fmt.setBorder(0)
                self._set_table_cells_color(table, None, None)

            elif style_name == "three_line":
                fmt.setBorder(0)
                fmt.setBorderStyle(QTextTableFormat.BorderStyle_None)
                self._set_table_cells_color(table, None, None)
                self._set_three_line_borders(table)

            elif style_name == "zebra":
                fmt.setBorder(1)
                for r in range(table.rows()):
                    if r == 0:
                        self._set_row_color(table, r, QColor(255, 179, 0))
                    elif r % 2 == 0:
                        self._set_row_color(table, r, QColor(255, 243, 224))

            elif style_name == "card":
                fmt.setBorder(1)
                for r in range(table.rows()):
                    for c in range(table.columns()):
                        cell = table.cellAt(r, c)
                        cell.setFormat(self._make_cell_fmt(
                            QColor(255, 255, 255), 1, QColor(220, 220, 220)
                        ))
                self._set_row_color(table, 0, QColor(245, 245, 245))

            elif style_name == "dark":
                fmt.setBorder(1)
                for r in range(table.rows()):
                    if r == 0:
                        self._set_row_color(
                            table, r, QColor(50, 50, 50),
                            QColor(255, 255, 255)
                        )
                    else:
                        self._set_row_color(
                            table, r,
                            QColor(70, 70, 70) if r % 2 == 0
                            else QColor(60, 60, 60),
                            QColor(230, 230, 230)
                        )

            elif style_name == "amber":
                fmt.setBorder(1)
                for r in range(table.rows()):
                    if r == 0:
                        self._set_row_color(
                            table, r, QColor(255, 179, 0),
                            QColor(80, 40, 0)
                        )
                    elif r % 2 == 0:
                        self._set_row_color(table, r, QColor(255, 243, 224))

            table.setFormat(fmt)
            self._set_status("✅ 已应用表格样式", 2000)
        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self, "样式应用失败", str(e))

    def _set_row_color(self, table, row, bg, fg=None):
        """给指定行设置背景 / 前景色"""
        for c in range(table.columns()):
            cell = table.cellAt(row, c)
            cursor = cell.firstCursorPosition()
            cursor.movePosition(
                QTextCursor.EndOfBlock, QTextCursor.KeepAnchor
            )
            fmt = QTextCharFormat()
            if bg:
                fmt.setBackground(bg)
            if fg:
                fmt.setForeground(fg)
                fmt.setFontWeight(
                    QFont.Bold if row == 0 else QFont.Normal
                )
            cursor.mergeCharFormat(fmt)
            cursor.clearSelection()

    def _set_table_cells_color(self, table, bg, fg):
        """给全表单元格设置背景 / 前景色"""
        for r in range(table.rows()):
            for c in range(table.columns()):
                cell = table.cellAt(r, c)
                cursor = cell.firstCursorPosition()
                cursor.movePosition(
                    QTextCursor.EndOfBlock, QTextCursor.KeepAnchor
                )
                fmt = QTextCharFormat()
                if bg:
                    fmt.setBackground(bg)
                if fg:
                    fmt.setForeground(fg)
                cursor.mergeCharFormat(fmt)
                cursor.clearSelection()

    def _set_three_line_borders(self, table):
        """三线表边框样式"""
        fmt = table.format()
        fmt.setBorder(2)
        fmt.setBorderStyle(QTextTableFormat.BorderStyle_Solid)
        fmt.setCellSpacing(0)
        fmt.setCellPadding(8)
        table.setFormat(fmt)

    def _make_cell_fmt(self, bg, border, border_color):
        """构造单元格格式（Qt 中单元格边框支持有限，此处仅设置背景）"""
        fmt = QTextCharFormat()
        if bg:
            fmt.setBackground(bg)
        return fmt

    # ==================================================================
    # 单元格对齐
    # ==================================================================
    def _cell_align(self, align):
        """
        设置单元格对齐。
        :param align: "left" / "center" / "right"（来自 ToolbarMixin）
                      也兼容传入 Qt.AlignLeft 等常量
        """
        if self._edit_mode != "rich_text":
            QMessageBox.information(
                self, "提示", "请先切换到所见即所得模式"
            )
            return

        # 字符串 → Qt 常量
        if isinstance(align, str):
            align_const = self._ALIGN_MAP.get(align, Qt.AlignLeft)
        else:
            align_const = align

        cursor = self.rich_editor.textCursor()
        table = cursor.currentTable()
        if not table:
            QMessageBox.information(self, "提示", "请把光标放在表格内")
            return

        # 有选区：应用到选区覆盖的所有单元格
        if cursor.hasSelection():
            start = cursor.selectionStart()
            end = cursor.selectionEnd()
            c1 = QTextCursor(self.rich_editor.document())
            c1.setPosition(start)
            c2 = QTextCursor(self.rich_editor.document())
            c2.setPosition(end)
            cell1 = table.cellAt(c1)
            cell2 = table.cellAt(c2)
            if cell1.isValid() and cell2.isValid():
                r1, c1_ = cell1.row(), cell1.column()
                r2, c2_ = cell2.row(), cell2.column()
                for r in range(min(r1, r2), max(r1, r2) + 1):
                    for c in range(min(c1_, c2_), max(c1_, c2_) + 1):
                        self._apply_cell_align(table, r, c, align_const)
                self._set_status("✅ 已设置对齐", 2000)
                return

        # 无选区：只处理光标所在单元格
        cell = table.cellAt(cursor)
        if cell.isValid():
            self._apply_cell_align(
                table, cell.row(), cell.column(), align_const
            )
            self._set_status("✅ 已设置对齐", 2000)

    def _apply_cell_align(self, table, row, col, align):
        """给指定单元格应用对齐"""
        cell = table.cellAt(row, col)
        cursor = cell.firstCursorPosition()
        cursor.movePosition(
            QTextCursor.EndOfBlock, QTextCursor.KeepAnchor
        )
        bf = QTextBlockFormat()
        bf.setAlignment(align)
        cursor.mergeBlockFormat(bf)
        cursor.clearSelection()

    # ==================================================================
    # Markdown 表格：辅助方法（薄封装，转发到 beewrite_utils）
    # ==================================================================
    def _detect_md_table_at_cursor(self):
        """检测光标所在的 Markdown 表格范围（转发）"""
        return detect_md_table_at_cursor(self.markdown_editor)

    def _parse_md_table(self, lines):
        """
        解析 Markdown 表格行（转发），**并顺手记下列对齐**。

        集中在这里做：只要走解析就一定会留下对齐信息，
        后续任何一次整表重渲染（双击编辑、增删行列…）都不会把对齐抹掉
        （审计报告 §2.13：原来分隔行被丢弃 + 渲染硬编码 `---`）。
        """
        from beeoffice.plugins.beewrite_utils import parse_md_table_aligns

        aligns = parse_md_table_aligns(lines)
        if aligns:
            self._md_table_aligns = aligns
        return parse_md_table(lines)

    def _parse_md_table_aligns(self, lines):
        """
        解析表格的**列对齐**（P1：审计 §2.13 的"列对齐被抹掉"）。

        解析一次后记在 `self._md_table_aligns` 上，供后续所有渲染沿用
        （双击编辑、增删行列等都会重新渲染整张表，必须带上对齐）。
        """
        from beeoffice.plugins.beewrite_utils import parse_md_table_aligns

        aligns = parse_md_table_aligns(lines)
        self._md_table_aligns = aligns or []
        return aligns

    def _render_md_table(self, rows, aligns=None):
        """
        渲染 Markdown 表格（转发）。

        :param aligns: 列对齐；不传就沿用**最近一次解析**到的对齐
            （存在 `self._md_table_aligns`），从而"编辑一次不再抹掉对齐"。
        """
        if aligns is None:
            aligns = getattr(self, "_md_table_aligns", None)
        return render_md_table(rows, aligns)

    def _replace_lines(self, start, end, new_text):
        """替换 Markdown 编辑器中的指定行范围"""
        text = self.markdown_editor.toPlainText()
        lines = text.split('\n')
        new_lines = lines[:start] + new_text.split('\n') + lines[end + 1:]
        new_content = '\n'.join(new_lines)

        cursor = self.markdown_editor.textCursor()
        pos = cursor.position()

        self.markdown_editor.blockSignals(True)
        self.markdown_editor.setPlainText(new_content)
        if pos <= len(new_content):
            cursor.setPosition(pos)
            self.markdown_editor.setTextCursor(cursor)
        self.markdown_editor.blockSignals(False)

        self._on_markdown_text_changed()

    # ==================================================================
    # Markdown 表格：双击进入可视化编辑
    # ==================================================================
    def _on_md_double_click(self, event):
        """Markdown 编辑器双击 → 若在表格内，弹出可视化编辑对话框"""
        from PySide6.QtWidgets import QPlainTextEdit

        QPlainTextEdit.mouseDoubleClickEvent(self.markdown_editor, event)

        table_range = self._detect_md_table_at_cursor()
        if not table_range:
            return

        start, end = table_range
        text = self.markdown_editor.toPlainText()
        lines = text.split('\n')
        table_lines = lines[start:end + 1]

        rows = self._parse_md_table(table_lines)
        if not rows:
            return

        dlg = MarkdownTableEditorDialog(rows, self)
        if dlg.exec() != QDialog.Accepted:
            return

        new_md = self._render_md_table(dlg.rows)
        self._replace_lines(start, end, new_md)
        self._set_status("✅ 表格已更新", 2000)

    # ==================================================================
    # Markdown 表格：快捷操作（Alt+方向键）
    # ==================================================================
    def _md_get_table_context(self):
        """获取光标所在 Markdown 表格的上下文"""
        table_range = self._detect_md_table_at_cursor()
        if not table_range:
            self._set_status("⚠️ 光标不在表格内", 2000)
            return None
        start, end = table_range
        text = self.markdown_editor.toPlainText()
        lines = text.split('\n')
        table_lines = lines[start:end + 1]
        rows = self._parse_md_table(table_lines)

        sep_idx = -1
        for i, line in enumerate(table_lines):
            s = line.strip().strip('|')
            if all(c in '-:| ' for c in s) and '-' in s:
                sep_idx = i
                break

        cursor_line = self.markdown_editor.textCursor().blockNumber()
        rel_row = cursor_line - start
        if sep_idx >= 0 and rel_row > sep_idx:
            rel_row -= 1
        if rel_row < 0:
            rel_row = 0

        return {
            "start": start,
            "end": end,
            "rows": rows,
            "rel_row": rel_row,
        }

    def _md_add_row_below(self):
        """在光标所在行下方插入一行"""
        ctx = self._md_get_table_context()
        if not ctx:
            return
        rows = ctx["rows"]
        rel = ctx["rel_row"]
        n_cols = max(len(r) for r in rows) if rows else 1
        insert_at = rel + 1
        if insert_at > len(rows):
            insert_at = len(rows)
        rows.insert(insert_at, [''] * n_cols)
        new_md = self._render_md_table(rows)
        self._replace_lines(ctx["start"], ctx["end"], new_md)
        self._set_status("✅ 已插入一行", 2000)

    def _md_add_row_above(self):
        """在光标所在行上方插入一行"""
        ctx = self._md_get_table_context()
        if not ctx:
            return
        rows = ctx["rows"]
        rel = ctx["rel_row"]
        n_cols = max(len(r) for r in rows) if rows else 1
        rows.insert(rel, [''] * n_cols)
        new_md = self._render_md_table(rows)
        self._replace_lines(ctx["start"], ctx["end"], new_md)
        self._set_status("✅ 已插入一行", 2000)

    def _md_add_col_right(self):
        """在光标所在列右侧插入一列"""
        ctx = self._md_get_table_context()
        if not ctx:
            return
        rows = ctx["rows"]
        cursor = self.markdown_editor.textCursor()
        line_text = cursor.block().text()
        pos_in_line = cursor.positionInBlock()
        pipes_before = line_text[:pos_in_line].count('|')
        col_idx = max(0, pipes_before - 1)
        for r in rows:
            while len(r) <= col_idx + 1:
                r.append('')
            r.insert(col_idx + 1, '')
        new_md = self._render_md_table(rows)
        self._replace_lines(ctx["start"], ctx["end"], new_md)
        self._set_status("✅ 已插入一列", 2000)

    def _md_add_col_left(self):
        """在光标所在列左侧插入一列"""
        ctx = self._md_get_table_context()
        if not ctx:
            return
        rows = ctx["rows"]
        cursor = self.markdown_editor.textCursor()
        line_text = cursor.block().text()
        pos_in_line = cursor.positionInBlock()
        pipes_before = line_text[:pos_in_line].count('|')
        col_idx = max(0, pipes_before - 1)
        for r in rows:
            while len(r) <= col_idx:
                r.append('')
            r.insert(col_idx, '')
        new_md = self._render_md_table(rows)
        self._replace_lines(ctx["start"], ctx["end"], new_md)
        self._set_status("✅ 已插入一列", 2000)

    # ==================================================================
    # 基础插入（代理到 RichTextEditor）
    # ==================================================================
    def _insert_table_dialog(self):
        """插入表格（代理到 RichTextEditor）"""
        if self._edit_mode != "rich_text":
            return
        self.rich_editor.insert_table_dialog()

    def _insert_horizontal_line(self):
        """插入水平分割线（代理到 RichTextEditor）"""
        if self._edit_mode != "rich_text":
            return
        self.rich_editor.insert_horizontal_line()

    def _insert_page_break(self):
        """插入分页符（代理到 RichTextEditor）"""
        if self._edit_mode != "rich_text":
            return
        self.rich_editor.insert_page_break()

    def _insert_section_break(self):
        """插入分节符（代理到 RichTextEditor）"""
        if self._edit_mode != "rich_text":
            return
        self.rich_editor.insert_section_break()

    def _insert_date(self):
        """插入当前日期（代理到 RichTextEditor）"""
        if self._edit_mode != "rich_text":
            return
        self.rich_editor.insert_current_date()

    # ==================================================================
    # Excel 数据插入
    # ==================================================================
    def _insert_excel_data(self):
        """插入 Excel 数据菜单（从蜜算 / 从文件）"""
        if self._edit_mode != "rich_text":
            return
        menu = QMenu(self)
        menu.addAction("📊 从蜜算表格插入数据").triggered.connect(
            self._insert_from_beesheet
        )
        menu.addAction("📂 从 CSV/Excel 文件插入数据").triggered.connect(
            self._insert_from_file
        )
        menu.exec(self.sender().mapToGlobal(
            self.sender().rect().bottomLeft()
        ))

    def _insert_from_beesheet(self):
        """从蜜算表格插入数据"""
        parent = self._find_main_window()
        if not parent:
            return
        sw = None
        for i in range(parent.tab_manager.count()):
            w = parent.tab_manager.widget(i)
            if hasattr(w, 'model') and hasattr(w.model, 'df'):
                sw = w
                break
        if not sw:
            QMessageBox.information(
                self, "提示", "请先打开一个蜜算表格"
            )
            return
        df = sw.model.df
        title = parent.tab_manager.tabText(
            parent.tab_manager.indexOf(sw)
        ).replace("📊 ", "")
        self.rich_editor.insert_dataframe_table(df, title)
        self._set_status(f"已插入蜜算数据: {title}", 3000)

    def _insert_from_file(self):
        """从 CSV / Excel 文件插入数据"""
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self, "选择数据文件", "", "数据文件 (*.csv *.xlsx *.xls)"
        )
        if not path:
            return
        try:
            import pandas as pd
            if path.endswith('.csv'):
                import chardet
                with open(path, 'rb') as f:
                    raw = f.read(10000)
                df = pd.read_csv(
                    path,
                    encoding=chardet.detect(raw).get('encoding', 'utf-8')
                )
            else:
                df = pd.read_excel(path)
            title = Path(path).stem
            self.rich_editor.insert_dataframe_table(df.head(100), title)
            self._set_status(f"已插入文件数据: {title}", 3000)
        except Exception as e:
            QMessageBox.warning(self, "导入失败", str(e))