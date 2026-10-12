# beeoffice/plugins/beesheet_context_menu_mixin.py
"""
蜜算右键菜单 Mixin

职责：
  - _show_fill_menu    : 表格右键菜单（粘贴 / 插入行列 / 删除行列 /
                         合并 / 格式 / 复制 / 批注 / 公式审计）

从 beesheet.py 抽取，降低主文件复杂度。

依赖：
  - PySide6（QMenu / QMessageBox）

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
from PySide6.QtWidgets import QMenu, QMessageBox
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
