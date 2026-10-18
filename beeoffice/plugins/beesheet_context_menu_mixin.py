# beeoffice/plugins/beesheet_context_menu_mixin.py
"""
蜜算右键菜单与冻结 Mixin

职责：
  - _show_fill_menu    : 表格右键菜单（粘贴 / 插入行列 / 删除行列 /
                         合并 / 格式 / 复制 / 批注 / 公式审计）
  - _show_freeze_menu  : 冻结菜单（冻结首行 / 首列 / 前3行 / 前3列 / 到当前单元格）
  - _freeze_row        : 冻结前 N 行
  - _freeze_column     : 冻结前 N 列
  - _freeze_cell       : 冻结到当前单元格（同时冻结行列）
  - _unfreeze_all      : 解除所有冻结

从 beesheet.py 抽取，降低主文件复杂度。

依赖：
  - PySide6（QMenu / QMessageBox）
  - QHeaderView（冻结行/列时设置 Fixed 模式）

注意：
  - 本 Mixin 调用主文件/其他 Mixin 的方法：
      self._smart_paste / self._copy_as_markdown /
      self._copy_selection_as_image         ← DataMixin
      self._show_cell_format_dialog          ← StyleMixin
      self._show_error_helper /
      self._trace_precedents /
      self._trace_dependents /
      self._clear_audit /
      self._translate_current_formula        ← AuditMixin
      self._insert_row_above / _insert_row_below /
      self._insert_col_left / _insert_col_right /
      self._delete_current_row / _delete_current_col /
      self._merge_cells / self._add_comment  ← RowColMixin / 主文件
  - 冻结行列的实际视觉分隔线通过 QHeaderView 的 StyleSheet 实现
"""
from PySide6.QtWidgets import QMenu, QMessageBox, QHeaderView
from PySide6.QtCore import Qt


class ContextMenuMixin:
    """蜜算右键菜单与冻结相关功能的 Mixin"""

    # ==================== 表格右键菜单 ====================
    def _show_fill_menu(self, pos):
        """表格区域右键菜单"""
        menu = QMenu(self)

        # ---------- 粘贴 ----------
        menu.addAction("📋 粘贴").triggered.connect(self._smart_paste)
        menu.addSeparator()

        # ---------- 插入行列 ----------
        insert_menu = menu.addMenu("➕ 插入")
        insert_menu.addAction("在上方插入行").triggered.connect(
            self._insert_row_above)
        insert_menu.addAction("在下方插入行").triggered.connect(
            self._insert_row_below)
        insert_menu.addAction("在左侧插入列").triggered.connect(
            self._insert_col_left)
        insert_menu.addAction("在右侧插入列").triggered.connect(
            self._insert_col_right)

        # ---------- 删除行列 ----------
        delete_menu = menu.addMenu("➖ 删除")
        delete_menu.addAction("删除当前行").triggered.connect(
            self._delete_current_row)
        delete_menu.addAction("删除当前列").triggered.connect(
            self._delete_current_col)

        menu.addSeparator()

        # ---------- 单元格操作 ----------
        menu.addAction("🔗 合并单元格").triggered.connect(self._merge_cells)
        menu.addAction("🎨 设置单元格格式").triggered.connect(
            self._show_cell_format_dialog)
        menu.addAction("📋 复制为Markdown").triggered.connect(
            self._copy_as_markdown)
        menu.addAction("🖼️ 复制为图片").triggered.connect(
            self._copy_selection_as_image)
        menu.addAction("💬 添加批注").triggered.connect(self._add_comment)

        menu.addSeparator()

        # ---------- 错误单元格：查看错误详情 ----------
        cur = self.table_view.currentIndex()
        if cur.isValid():
            v = str(self.model.get_value(cur.row(), cur.column()))
            if v.startswith('#ERROR') or v.startswith('#N/A'):
                menu.addAction("⚠ 查看错误详情").triggered.connect(
                    lambda: self._show_error_helper(
                        (cur.row(), cur.column()), v
                    )
                )
                menu.addSeparator()

        # ---------- 公式审计 ----------
        audit_menu = menu.addMenu("🔍 公式审计")
        audit_menu.addAction("追踪引用单元格  Ctrl+[").triggered.connect(
            self._trace_precedents)
        audit_menu.addAction("追踪从属单元格  Ctrl+]").triggered.connect(
            self._trace_dependents)
        audit_menu.addAction("清除审计高亮").triggered.connect(
            self._clear_audit)
        audit_menu.addSeparator()
        audit_menu.addAction("📖 翻译公式").triggered.connect(
            self._translate_current_formula)

        menu.exec(pos)

    # ==================== 冻结菜单 ====================
    def _show_freeze_menu(self):
        """冻结菜单（由工具栏按钮触发）"""
        menu = QMenu(self)
        menu.addAction("📌 冻结首行").triggered.connect(
            lambda: self._freeze_row(0))
        menu.addAction("📌 冻结首列").triggered.connect(
            lambda: self._freeze_column(0))
        menu.addAction("📌 冻结到当前单元格").triggered.connect(
            self._freeze_cell)
        menu.addAction("📌 冻结前3行").triggered.connect(
            lambda: self._freeze_row(2))
        menu.addAction("📌 冻结前3列").triggered.connect(
            lambda: self._freeze_column(2))
        menu.exec(self.sender().mapToGlobal(
            self.sender().rect().bottomLeft()))

    # ==================== 冻结实现 ====================
    def _freeze_column(self, column):
        """冻结前 N 列（0 基 column 参数，内部 +1 转数量）"""
        self._frozen_cols = column + 1
        for i in range(self._frozen_cols):
            self.table_view.horizontalHeader().setSectionResizeMode(
                i, QHeaderView.Fixed)
        self.table_view.horizontalHeader().setStyleSheet(
            "QHeaderView::section:last { border-right: 3px solid #FFB300; }"
        )
        self._update_status()
        self._set_status(f"📌 已冻结前 {self._frozen_cols} 列", 3000)

    def _freeze_row(self, row):
        """冻结前 N 行（0 基 row 参数，内部 +1 转数量）"""
        self._frozen_rows = row + 1
        for i in range(self._frozen_rows):
            self.table_view.verticalHeader().setSectionResizeMode(
                i, QHeaderView.Fixed)
        # P1-18：只改 resizeMode 只是"锁住行高"，滚动时照样被顶走。
        # 首行是最常用场景，这里真正浮一个只显示第 0 行的视图。
        install = getattr(self, "_install_frozen_row", None)
        if row == 0 and install is not None:
            install()
        self._update_status()
        self._set_status(f"📌 已冻结前 {self._frozen_rows} 行", 3000)

    def _freeze_cell(self):
        """冻结到当前单元格：同时冻结所在行以上 + 列左侧"""
        idx = self.table_view.currentIndex()
        if idx.isValid():
            self._frozen_rows = idx.row() + 1
            self._frozen_cols = idx.column() + 1
            for i in range(self._frozen_cols):
                self.table_view.horizontalHeader().setSectionResizeMode(
                    i, QHeaderView.Fixed)
            for i in range(self._frozen_rows):
                self.table_view.verticalHeader().setSectionResizeMode(
                    i, QHeaderView.Fixed)
            self.table_view.horizontalHeader().setStyleSheet(
                "QHeaderView::section:last { border-right: 3px solid #FFB300; }"
            )
            self._update_status()
            self._set_status(
                f"📌 已冻结 {self._frozen_rows} 行 × "
                f"{self._frozen_cols} 列", 3000
            )

    def _unfreeze_all(self):
        """解除所有冻结的行列"""
        self._frozen_rows = 0
        self._frozen_cols = 0
        remove = getattr(self, "_remove_frozen_row", None)
        if remove is not None:
            remove()
        hh = self.table_view.horizontalHeader()
        vh = self.table_view.verticalHeader()
        for i in range(self.model.columnCount()):
            hh.setSectionResizeMode(i, QHeaderView.Interactive)
        for i in range(self.model.rowCount()):
            vh.setSectionResizeMode(i, QHeaderView.Interactive)
        hh.setStyleSheet("")
        self._update_status()
        self._set_status("✅ 已解冻所有行列", 3000)