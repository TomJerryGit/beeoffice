# beeoffice/plugins/beesheet_rowcol_mixin.py
"""
蜜算行列操作与填充 Mixin

职责：
  - 插入行/列
    * _insert_row_above / _insert_row_below
    * _insert_col_left  / _insert_col_right
  - 删除行/列
    * _delete_current_row / _delete_current_col
  - 合并单元格
    * _merge_cells
  - 填充
    * _shortcut_fill_down  / _shortcut_fill_right
    * _fill_down           / _fill_right
      （支持公式相对引用自动调整）

从 beesheet.py 抽取，降低主文件复杂度。

依赖：
  - pandas（pd.DataFrame / pd.concat）
  - col_index_to_name（列索引 → 字母）
  - adjust_formula_refs（公式相对引用调整）
  - FormulaEngine（公式求值）

注意：
  - 所有方法依赖 self.model / self.table_view /
    self._formula_cells / self._set_status / self._merged_cells 等，
    由 BeeSheetView 主类提供
  - _fill_down / _fill_right 遇到公式单元格时，
    会通过 adjust_formula_refs 调整相对引用后重新求值
"""
import pandas as pd

from beeoffice.plugins.beesheet_utils import (
    col_index_to_name,
    adjust_formula_refs,
)
from beeoffice.plugins.beesheet_engine import FormulaEngine


class RowColMixin:
    """蜜算行列操作与填充相关功能的 Mixin"""

    # ==================== 插入行 ====================
    def _insert_row_above(self):
        """在当前行上方插入一行空行"""
        idx = self.table_view.currentIndex()
        if not idx.isValid():
            return
        r = idx.row()
        df = self.model._loaded_df
        # 构造一行空数据（列名与当前 df 一致）
        nr = pd.DataFrame([['' for _ in range(len(df.columns))]],
                           columns=df.columns)
        # 拼接：前 r 行 + 新行 + r 之后的行
        self.model._loaded_df = pd.concat(
            [df.iloc[:r], nr, df.iloc[r:]]
        ).reset_index(drop=True)
        self.model._total_rows = len(self.model._loaded_df)
        self.model.layoutChanged.emit()
        self._set_status(f"已在第{r+1}行上方插入", 2000)

    def _insert_row_below(self):
        """在当前行下方插入一行空行"""
        idx = self.table_view.currentIndex()
        if not idx.isValid():
            return
        r = idx.row()
        df = self.model._loaded_df
        nr = pd.DataFrame([['' for _ in range(len(df.columns))]],
                           columns=df.columns)
        # 拼接：前 r+1 行 + 新行 + r+1 之后的行
        self.model._loaded_df = pd.concat(
            [df.iloc[:r+1], nr, df.iloc[r+1:]]
        ).reset_index(drop=True)
        self.model._total_rows = len(self.model._loaded_df)
        self.model.layoutChanged.emit()
        self._set_status(f"已在第{r+1}行下方插入", 2000)

    # ==================== 插入列 ====================
    def _insert_col_left(self):
        """在当前列左侧插入一列空列"""
        idx = self.table_view.currentIndex()
        if not idx.isValid():
            return
        c = idx.column()
        df = self.model._loaded_df
        # 根据当前列索引生成新列名（如 C → "C"，若已存在则加 _1）
        nn = col_index_to_name(c)
        while nn in df.columns:
            nn += "_1"
        df.insert(c, nn, '')
        self.model._loaded_df = df
        self.model._total_cols = len(df.columns)
        self.model.layoutChanged.emit()
        self._set_status("已在左侧插入列", 2000)

    def _insert_col_right(self):
        """在当前列右侧插入一列空列"""
        idx = self.table_view.currentIndex()
        if not idx.isValid():
            return
        c = idx.column()
        df = self.model._loaded_df
        # 根据 c+1 生成新列名（如 C → "D"，若已存在则加 _1）
        nn = col_index_to_name(c + 1)
        while nn in df.columns:
            nn += "_1"
        df.insert(c + 1, nn, '')
        self.model._loaded_df = df
        self.model._total_cols = len(df.columns)
        self.model.layoutChanged.emit()
        self._set_status("已在右侧插入列", 2000)

    # ==================== 删除行/列 ====================
    def _delete_current_row(self):
        """删除当前行（至少保留一行）"""
        idx = self.table_view.currentIndex()
        if not idx.isValid():
            return
        r = idx.row()
        if len(self.model._loaded_df) <= 1:
            self._set_status("至少保留一行", 2000)
            return
        self.model._loaded_df = self.model._loaded_df.drop(
            index=r).reset_index(drop=True)
        self.model._total_rows = len(self.model._loaded_df)
        self.model.layoutChanged.emit()

    def _delete_current_col(self):
        """删除当前列（至少保留一列）"""
        idx = self.table_view.currentIndex()
        if not idx.isValid():
            return
        c = idx.column()
        if len(self.model._loaded_df.columns) <= 1:
            self._set_status("至少保留一列", 2000)
            return
        self.model._loaded_df = self.model._loaded_df.drop(
            columns=[self.model._loaded_df.columns[c]]
        )
        self.model._total_cols = len(self.model._loaded_df.columns)
        self.model.layoutChanged.emit()

    # ==================== 合并单元格 ====================
    def _merge_cells(self):
        """合并当前选区覆盖的单元格（首格保留内容，其余置空）"""
        sel = self.table_view.selectionModel().selection()
        if not sel:
            return
        indexes = sel.indexes()
        if len(indexes) < 2:
            return
        rows = sorted(set(i.row() for i in indexes))
        cols = sorted(set(i.column() for i in indexes))
        r1, r2, c1, c2 = min(rows), max(rows), min(cols), max(cols)
        # 使用 QTableView.setSpan 实现视觉合并
        self.table_view.setSpan(r1, c1, r2 - r1 + 1, c2 - c1 + 1)
        # 记录合并信息，供后续判断（如重复合并、取消合并）
        self._merged_cells[(r1, c1)] = (r2 - r1 + 1, c2 - c1 + 1)
        self._set_status("已合并", 2000)

    # ==================== 填充快捷键 ====================
    def _shortcut_fill_down(self):
        """Ctrl+D：向下填充"""
        # R1 安全门：批量填充会写整列，必须在数据完整时做
        if not self._ensure_full_data("向下填充"):
            return
        sel = self.table_view.selectionModel().selection()
        if not sel:
            return
        indexes = sorted([(i.row(), i.column()) for i in sel.indexes()],
                          key=lambda x: (x[0], x[1]))
        rows = sorted(set(r for r, _ in indexes))
        cols = sorted(set(c for _, c in indexes))
        # 只有单列选中时，向下填充才有明确语义
        if len(cols) == 1 and rows:
            self._fill_down(rows, cols[0])

    def _shortcut_fill_right(self):
        """Ctrl+R：向右填充"""
        # R1 安全门：批量填充会写整行，必须在数据完整时做
        if not self._ensure_full_data("向右填充"):
            return
        sel = self.table_view.selectionModel().selection()
        if not sel:
            return
        indexes = sorted([(i.row(), i.column()) for i in sel.indexes()],
                          key=lambda x: (x[0], x[1]))
        rows = sorted(set(r for r, _ in indexes))
        cols = sorted(set(c for _, c in indexes))
        # 只有单行选中时，向右填充才有明确语义
        if len(rows) == 1 and cols:
            self._fill_right(rows[0], cols)

    # ==================== 填充实现 ====================
    def _fill_down(self, source_rows, col):
        """
        向下填充：将选区最上方单元格的内容 / 公式填充到下方空单元格

        :param source_rows: 选中区域的行索引列表
        :param col: 列索引
        """
        lr = source_rows[-1]
        # 找到选中区域下方的空单元格
        target = [r for r in range(lr + 1, len(self.model.df))
                  if str(self.model.get_value(r, col)).strip() == '']
        if not target:
            return
        src_r = source_rows[0]
        src_key = (src_r, col)
        for tr in target:
            if src_key in self._formula_cells:
                # 公式填充：调整相对引用后重新求值
                new_formula = adjust_formula_refs(
                    self._formula_cells[src_key], tr - src_r, 0
                )
                result = FormulaEngine.evaluate(new_formula, self.model)
                self.model._loaded_df.iloc[tr, col] = result
                self._formula_cells[(tr, col)] = new_formula
            else:
                # 普通值填充：直接复制
                val = self.model.get_value(src_r, col)
                self.model._loaded_df.iloc[tr, col] = val
        self.model.layoutChanged.emit()
        self._set_status(f"已填充 {len(target)} 个单元格", 3000)

    def _fill_right(self, source_row, source_cols):
        """
        向右填充：将选区最左侧单元格的内容 / 公式填充到右侧空单元格

        :param source_row: 选中区域的行索引
        :param source_cols: 选中区域的列索引列表
        """
        lc = source_cols[-1]
        # 找到选中区域右侧的空单元格
        target = [c for c in range(lc + 1, len(self.model.df.columns))
                  if str(self.model.get_value(source_row, c)).strip() == '']
        if not target:
            return
        src_c = source_cols[0]
        src_key = (source_row, src_c)
        for tc in target:
            if src_key in self._formula_cells:
                # 公式填充：调整相对引用后重新求值
                new_formula = adjust_formula_refs(
                    self._formula_cells[src_key], 0, tc - src_c
                )
                result = FormulaEngine.evaluate(new_formula, self.model)
                self.model._loaded_df.iloc[source_row, tc] = result
                self._formula_cells[(source_row, tc)] = new_formula
            else:
                # 普通值填充：直接复制
                val = self.model.get_value(source_row, src_c)
                self.model._loaded_df.iloc[source_row, tc] = val
        self.model.layoutChanged.emit()
        self._set_status(f"已填充 {len(target)} 个单元格", 3000)