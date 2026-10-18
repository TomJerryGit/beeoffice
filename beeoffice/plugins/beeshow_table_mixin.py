# beeoffice/plugins/beeshow_table_mixin.py
"""
蜜演表格编辑器（v5.2 · B1）

职责：
  - _show_table_editor  : 打开表格编辑器对话框
  - _edit_current_table : 编辑光标处已有的 Markdown 表格
  - _insert_table_md    : 把生成的 Markdown 表格插入当前页

设计：
  - 弹窗式可视化编辑（不用手写 Markdown）
  - QTableWidget 承载单元格
  - 支持：插入/删除行列、移动行列、表头设置
  - 实时 Markdown 预览
  - 确认后插入到当前页末尾

对标：
  - WPS 演示的「插入表格 + 编辑行列 + 合并单元格」

语法：
  Markdown 表格：
    | 表头1 | 表头2 |
    |------|------|
    | 数据1 | 数据2 |

依赖：
  - re
  - PySide6（QDialog / QVBoxLayout / QHBoxLayout / QTableWidget /
             QTableWidgetItem / QPushButton / QLabel / QTextEdit /
             QCheckBox / QSpinBox / QMessageBox / QDialogButtonBox）

注意：
  - 不导入其他 beeshow_* Mixin
  - 生成的 Markdown 表格由 markdown 库的 tables 扩展渲染
"""

import re
import logging

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QTextEdit, QCheckBox,
    QSpinBox, QDialogButtonBox, QMessageBox, QHeaderView,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from beeoffice.i18n import tr


# ==================== 表格编辑器对话框 ====================
class TableEditorDialog(QDialog):
    """
    表格编辑器对话框。

    功能：
      - 输入行列数，一键创建空表格
      - 可视化编辑每个单元格
      - 插入 / 删除行列
      - 移动行列
      - 表头开关
      - 实时 Markdown 预览
    """

    def __init__(self, initial_rows=None, parent=None):
        """
        :param initial_rows: 初始二维列表（None 时创建空表格）
        :param parent: 父窗口
        """
        super().__init__(parent)
        self.setWindowTitle(tr("auto.beeshow_table_mixin.cc2775cd", "📊 表格编辑器"))
        self.resize(720, 560)

        self._initial_rows = initial_rows

        layout = QVBoxLayout(self)

        # ===== 顶部：新建选项 =====
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel(tr("auto.beeshow_table_mixin.b9b77381", "行:")))
        self._row_spin = QSpinBox()
        self._row_spin.setRange(1, 50)
        self._row_spin.setValue(3)
        self._row_spin.setMaximumWidth(70)
        top_bar.addWidget(self._row_spin)

        top_bar.addWidget(QLabel(tr("auto.beeshow_table_mixin.f85a5e90", "列:")))
        self._col_spin = QSpinBox()
        self._col_spin.setRange(1, 20)
        self._col_spin.setValue(3)
        self._col_spin.setMaximumWidth(70)
        top_bar.addWidget(self._col_spin)

        btn_new = QPushButton(tr("auto.beeshow_table_mixin.ba9dc330", "🆕 新建"))
        btn_new.clicked.connect(self._on_new_table)
        top_bar.addWidget(btn_new)

        btn_clear = QPushButton(tr("auto.beeshow_table_mixin.323280c8", "🧹 清空内容"))
        btn_clear.clicked.connect(self._on_clear)
        top_bar.addWidget(btn_clear)

        top_bar.addStretch()

        self._header_check = QCheckBox(tr("auto.beeshow_table_mixin.7bbad6ae", "含表头"))
        self._header_check.setChecked(True)
        self._header_check.stateChanged.connect(self._on_header_changed)
        top_bar.addWidget(self._header_check)

        layout.addLayout(top_bar)

        # ===== 中部：表格 =====
        self._table = QTableWidget()
        self._table.setStyleSheet(
            "QTableWidget{border:1px solid #DDD;"
            "gridline-color:#EEE;font-size:13px;}"
            "QTableWidget::item{padding:4px;}"
        )
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self._table.itemChanged.connect(self._on_cell_changed)
        layout.addWidget(self._table, 1)

        # ===== 操作按钮行 =====
        op_bar = QHBoxLayout()

        for text, slot in [
            ("↑ 上插行", lambda: self._insert_row(-1)),
            ("↓ 下插行", lambda: self._insert_row(1)),
            ("← 左插列", lambda: self._insert_col(-1)),
            ("→ 右插列", lambda: self._insert_col(1)),
            ("🗑 删行", self._delete_row),
            ("🗑 删列", self._delete_col),
            ("⬆ 上移", lambda: self._move_row(-1)),
            ("⬇ 下移", lambda: self._move_row(1)),
        ]:
            btn = QPushButton(text)
            btn.setStyleSheet(
                "QPushButton{font-size:12px;padding:4px 8px;}"
            )
            btn.clicked.connect(slot)
            op_bar.addWidget(btn)

        op_bar.addStretch()
        layout.addLayout(op_bar)

        # ===== 底部：Markdown 预览 =====
        layout.addWidget(QLabel(tr("auto.beeshow_table_mixin.01130939", "Markdown 预览：")))
        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setStyleSheet(
            "QTextEdit{background:#FAFAFA;"
            "font-family:Consolas;font-size:12px;padding:6px;}"
        )
        self._preview.setMaximumHeight(120)
        layout.addWidget(self._preview)

        # ===== 底部按钮 =====
        btns = QDialogButtonBox()
        ok_btn = QPushButton(tr("auto.beeshow_table_mixin.70d67f36", "✅ 插入"))
        ok_btn.setStyleSheet(
            "QPushButton{background:#FFB300;color:#000;"
            "padding:6px 16px;border:none;border-radius:4px;"
            "font-weight:bold;}"
            "QPushButton:hover{background:#FFA000;}"
        )
        ok_btn.clicked.connect(self._on_accept)
        btns.addButton(ok_btn, QDialogButtonBox.AcceptRole)

        cancel_btn = QPushButton(tr("auto.beeshow_table_mixin.4d0b4688", "取消"))
        cancel_btn.clicked.connect(self.reject)
        btns.addButton(cancel_btn, QDialogButtonBox.RejectRole)

        layout.addWidget(btns)

        # ===== 初始化 =====
        if initial_rows:
            self._load_rows(initial_rows)
        else:
            self._on_new_table()

    # ==================== 初始化 / 新建 ====================
    def _on_new_table(self):
        """创建空白表格"""
        rows = self._row_spin.value()
        cols = self._col_spin.value()
        self._table.blockSignals(True)
        self._table.setRowCount(rows)
        self._table.setColumnCount(cols)
        for r in range(rows):
            for c in range(cols):
                self._table.setItem(r, c, QTableWidgetItem(""))
        # 设置列头
        self._table.setHorizontalHeaderLabels(
            [f"列{c+1}" for c in range(cols)]
        )
        self._table.blockSignals(False)
        self._update_preview()
        self._update_header_style()

    def _on_clear(self):
        """清空所有单元格内容"""
        for r in range(self._table.rowCount()):
            for c in range(self._table.columnCount()):
                item = self._table.item(r, c)
                if item is not None:
                    item.setText("")
        self._update_preview()

    def _load_rows(self, rows):
        """从二维列表加载"""
        n_rows = len(rows)
        n_cols = max((len(r) for r in rows), default=1)
        self._table.blockSignals(True)
        self._table.setRowCount(n_rows)
        self._table.setColumnCount(n_cols)
        for r in range(n_rows):
            for c in range(n_cols):
                val = rows[r][c] if c < len(rows[r]) else ""
                self._table.setItem(r, c, QTableWidgetItem(str(val)))
        self._table.setHorizontalHeaderLabels(
            [f"列{c+1}" for c in range(n_cols)]
        )
        self._table.blockSignals(False)
        self._update_preview()
        self._update_header_style()

    # ==================== 行列操作 ====================
    def _insert_row(self, offset):
        """在光标行上方(-1)/下方(+1)插入一行"""
        cur_row = self._table.currentRow()
        if cur_row < 0:
            cur_row = self._table.rowCount() - 1
        insert_at = cur_row + (0 if offset < 0 else 1)
        self._table.insertRow(insert_at)
        for c in range(self._table.columnCount()):
            self._table.setItem(insert_at, c, QTableWidgetItem(""))
        self._table.setCurrentCell(insert_at, 0)
        self._update_preview()

    def _insert_col(self, offset):
        """在光标列左侧(-1)/右侧(+1)插入一列"""
        cur_col = self._table.currentColumn()
        if cur_col < 0:
            cur_col = self._table.columnCount() - 1
        insert_at = cur_col + (0 if offset < 0 else 1)
        self._table.insertColumn(insert_at)
        for r in range(self._table.rowCount()):
            self._table.setItem(insert_at, r, QTableWidgetItem(""))
        self._table.setCurrentCell(0, insert_at)
        self._update_preview()

    def _delete_row(self):
        """删除当前行（至少保留一行）"""
        if self._table.rowCount() <= 1:
            QMessageBox.information(self, tr("auto.beeshow_table_mixin.ab3656a9", "提示"), tr("auto.beeshow_table_mixin.201a8dd2", "至少保留一行"))
            return
        cur_row = self._table.currentRow()
        if cur_row < 0:
            return
        self._table.removeRow(cur_row)
        self._update_preview()

    def _delete_col(self):
        """删除当前列（至少保留一列）"""
        if self._table.columnCount() <= 1:
            QMessageBox.information(self, tr("auto.beeshow_table_mixin.ab3656a9", "提示"), tr("auto.beeshow_table_mixin.95d3a0f0", "至少保留一列"))
            return
        cur_col = self._table.currentColumn()
        if cur_col < 0:
            return
        self._table.removeColumn(cur_col)
        self._update_preview()

    def _move_row(self, offset):
        """移动当前行上/下"""
        cur_row = self._table.currentRow()
        target = cur_row + offset
        if cur_row < 0 or target < 0 or target >= self._table.rowCount():
            return
        # 交换内容
        for c in range(self._table.columnCount()):
            item1 = self._table.takeItem(cur_row, c)
            item2 = self._table.takeItem(target, c)
            self._table.setItem(cur_row, c, item2 or QTableWidgetItem(""))
            self._table.setItem(target, c, item1 or QTableWidgetItem(""))
        self._table.setCurrentCell(target, 0)
        self._update_preview()

    # ==================== 表头 ====================
    def _on_header_changed(self):
        """表头开关变化"""
        self._update_header_style()
        self._update_preview()

    def _update_header_style(self):
        """表头行加粗（视觉）"""
        has_header = self._header_check.isChecked()
        font = QFont()
        for c in range(self._table.columnCount()):
            item = self._table.item(0, c)
            if item is not None:
                font.setBold(has_header)
                item.setFont(font)

    # ==================== 单元格变化 ====================
    def _on_cell_changed(self, item):
        """单元格内容变化 → 刷新预览"""
        self._update_preview()

    # ==================== Markdown 预览 ====================
    def _update_preview(self):
        """更新 Markdown 预览"""
        try:
            md = self._build_markdown()
            self._preview.setPlainText(md)
        except Exception as e:
            self._preview.setPlainText(f"（预览失败：{e}）")

    def _build_markdown(self) -> str:
        """根据表格内容生成 Markdown"""
        rows = self._get_grid()
        if not rows:
            return ""

        n_cols = max(len(r) for r in rows)
        out = []
        has_header = self._header_check.isChecked()

        for i, row in enumerate(rows):
            # 补齐列数
            padded = list(row) + [""] * (n_cols - len(row))
            out.append("| " + " | ".join(padded) + " |")
            # 第一行后加分隔行
            if i == 0:
                out.append("|" + "|".join(["---"] * n_cols) + "|")
                if not has_header:
                    # 不含表头时，额外加一个空行作为实际数据行
                    # （避免把第一行当表头）
                    pass

        return "\n".join(out)

    def _get_grid(self):
        """获取表格内容为二维列表"""
        n_rows = self._table.rowCount()
        n_cols = self._table.columnCount()
        rows = []
        for r in range(n_rows):
            row = []
            for c in range(n_cols):
                item = self._table.item(r, c)
                row.append(item.text() if item else "")
            rows.append(row)
        return rows

    # ==================== 确认 ====================
    def _on_accept(self):
        """点击"插入"按钮"""
        rows = self._get_grid()
        if not rows:
            QMessageBox.warning(self, tr("auto.beeshow_table_mixin.ab3656a9", "提示"), tr("auto.beeshow_table_mixin.c12fa40f", "表格为空"))
            return
        # 检查是否所有单元格为空
        if all(not cell.strip() for row in rows for cell in row):
            QMessageBox.warning(self, tr("auto.beeshow_table_mixin.ab3656a9", "提示"), tr("auto.beeshow_table_mixin.162ad18e", "表格内容全为空"))
            return
        self.accept()

    def get_markdown_table(self) -> str:
        """返回生成的 Markdown 表格"""
        return self._build_markdown()

    def get_rows(self) -> list:
        """返回二维列表"""
        return self._get_grid()

    def has_header(self) -> bool:
        """返回是否含表头"""
        return self._header_check.isChecked()


# ==================== 表格 Mixin ====================
class TableMixin:
    """蜜演表格编辑器 Mixin"""

    # ==================== 打开表格编辑器 ====================
    def _show_table_editor(self):
        """
        打开表格编辑器对话框。

        确认后，把生成的 Markdown 表格插入到当前页末尾。
        """
        from beeoffice.plugins.beeshow_table_mixin import TableEditorDialog

        if not self._slides_md:
            QMessageBox.information(
                self, tr("auto.beeshow_table_mixin.ab3656a9", "提示"), tr("auto.beeshow_table_mixin.63565334", "请先编写幻灯片内容")
            )
            return

        if not (0 <= self._current_slide < len(self._slides_md)):
            return

        # 检查当前页是否已有表格 → 尝试加载
        initial_rows = self._extract_current_table()

        dlg = TableEditorDialog(initial_rows, self)
        if dlg.exec() != QDialog.Accepted:
            return

        md_table = dlg.get_markdown_table()
        if not md_table:
            return

        self._insert_table_md(md_table)
        self._set_status(tr("auto.beeshow_table_mixin.2e671706", "✅ 表格已插入"), 2000)

    # ==================== 提取当前表格 ====================
    def _extract_current_table(self):
        """
        从当前页 Markdown 提取已有表格（若存在）。

        :return: 二维列表 或 None
        """
        try:
            if not (0 <= self._current_slide < len(self._slides_md)):
                return None

            text = self._slides_md[self._current_slide]
            lines = text.split("\n")

            # 找表格行（以 | 开头结尾）
            table_lines = []
            for line in lines:
                s = line.strip()
                if s.startswith("|") and s.endswith("|"):
                    table_lines.append(s)
                elif table_lines:
                    break

            if not table_lines:
                return None

            # 解析为二维列表
            rows = []
            for line in table_lines:
                inner = line.strip("|")
                # 跳过分隔行
                if all(c in "-:| " for c in inner) and "-" in inner:
                    continue
                cells = [c.strip() for c in inner.split("|")]
                rows.append(cells)

            return rows if rows else None
        except Exception as e:
            logging.error(f"提取表格失败：{e}")
            return None

    # ==================== 插入表格 ====================
    def _insert_table_md(self, md_table: str):
        """
        把 Markdown 表格插入到当前页末尾。

        :param md_table: Markdown 表格文本
        """
        try:
            text = self._editor.toPlainText()
            parts = re.split(r'\n---', text)
            if not (0 <= self._current_slide < len(parts)):
                return

            # 在页末尾追加表格（前后各留空行）
            parts[self._current_slide] = (
                parts[self._current_slide].rstrip()
                + "\n\n"
                + md_table
                + "\n"
            )

            self._editor.blockSignals(True)
            self._editor.setPlainText('\n---\n'.join(parts))
            self._editor.blockSignals(False)
            self._update_preview()
        except Exception as e:
            logging.error(f"插入表格失败：{e}")
            QMessageBox.warning(self, tr("auto.beeshow_table_mixin.4620fab0", "插入失败"), str(e))

    # ==================== 编辑已有表格 ====================
    def _edit_current_table(self):
        """
        编辑当前页已有的表格。

        若无表格，则提示用户使用 _show_table_editor 新建。
        """
        rows = self._extract_current_table()
        if not rows:
            QMessageBox.information(
                self, tr("auto.beeshow_table_mixin.ab3656a9", "提示"),
                "当前页没有表格。\n\n"
                "请使用「📊 表格」按钮新建。"
            )
            return

        # 打开编辑器，加载已有内容
        from beeoffice.plugins.beeshow_table_mixin import TableEditorDialog
        dlg = TableEditorDialog(rows, self)
        if dlg.exec() != QDialog.Accepted:
            return

        md_table = dlg.get_markdown_table()
        if not md_table:
            return

        self._replace_current_table(md_table)
        self._set_status(tr("auto.beeshow_table_mixin.b2153c80", "✅ 表格已更新"), 2000)

    def _replace_current_table(self, new_md_table: str):
        """
        替换当前页的表格（用新的 Markdown 表格）。

        :param new_md_table: 新的 Markdown 表格
        """
        try:
            if not (0 <= self._current_slide < len(self._slides_md)):
                return

            text = self._slides_md[self._current_slide]
            lines = text.split("\n")

            # 找表格范围
            table_start = None
            table_end = None
            for i, line in enumerate(lines):
                s = line.strip()
                if s.startswith("|") and s.endswith("|"):
                    if table_start is None:
                        table_start = i
                    table_end = i

            if table_start is None:
                # 无表格，直接追加
                self._insert_table_md(new_md_table)
                return

            # 替换表格行
            new_lines = (
                lines[:table_start]
                + new_md_table.split("\n")
                + lines[table_end + 1:]
            )
            new_text = "\n".join(new_lines)

            # 写回编辑器
            full_text = self._editor.toPlainText()
            parts = re.split(r'\n---', full_text)
            if self._current_slide < len(parts):
                parts[self._current_slide] = new_text
                self._editor.blockSignals(True)
                self._editor.setPlainText('\n---\n'.join(parts))
                self._editor.blockSignals(False)
                self._update_preview()
        except Exception as e:
            logging.error(f"替换表格失败：{e}")
            QMessageBox.warning(self, tr("auto.beeshow_table_mixin.8f1950e0", "替换失败"), str(e))