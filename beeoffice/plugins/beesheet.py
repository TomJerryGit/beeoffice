# beeoffice/plugins/beesheet.py
"""
蜜算 BeeSheet —— 主视图（拆分后）

依赖：
  - beesheet_utils / commands / delegate / loaders
  - beesheet_engine / model / dialogs
  - beesheet_formula_mixin / style_mixin / audit_mixin / data_mixin
  - beesheet_chart_mixin     ← 新增（v5.0.5）
  - beesheet_context_menu_mixin ← 新增（v5.0.5）
  - beesheet_rowcol_mixin    ← 新增（v5.0.5）
  - beesheet_ui_mixin        ← 新增（v5.0.5）

v5.0.1 修复：
  - P0-1：补齐 QFormLayout / QCheckBox 导入
          （_show_sort_dialog / _show_find_replace 使用，缺失会导致 NameError）
  - P0-15：大文件分块加载新增取消按钮
          - __init__ 新增 _cancel_load_btn
          - load_large_file 连接 cancelled 信号
          - 新增 _cancel_large_file_load 方法
          - closeEvent 增加 requestInterruption

v5.0.5 拆分（本次）：
  将原 1854 行 beesheet.py 按职责拆分为 4 个新 mixin：
    - ChartMixin        : 图表 + 透视表
    - ContextMenuMixin  : 右键菜单 + 冻结
    - RowColMixin       : 行列插入/删除 + 合并 + 填充
    - UIMixin           : 5 行工具栏 + 表格视图 + 填充柄 + 信息面板
                           + 快捷键 + 加载器/定时器 + 函数参考表

  主文件只保留：
    - __init__（组装）
    - 填充柄事件处理
    - 导入导出
    - 撤销重做 / 排序 / 滚动
    - 状态栏 / 信息面板 / 定位 / 查找替换 / 批注
    - 自然语言解析 + 自动保存
    - closeEvent

  目标行数 < 800（原 1854 行）
"""

import os
import re
import json
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QMessageBox, QDialog, QComboBox, QDialogButtonBox,
    QListWidget, QListWidgetItem, QTextEdit, QInputDialog,
    QApplication, QFormLayout, QCheckBox, QMenu,
)
from PySide6.QtCore import (
    Qt, QTimer, QItemSelectionModel, QItemSelection,
)
from PySide6.QtGui import QColor

from beeoffice.plugins.beesheet_utils import (
    adjust_formula_refs, col_index_to_name, col_name_to_index,
    extract_refs_from_formula,
)
from beeoffice.plugins.beesheet_commands import (
    EditCellCommand, SortCommand, TrimCommand,
)
from beeoffice.plugins.beesheet_loaders import LargeFileLoader
from beeoffice.plugins.beesheet_engine import FormulaEngine
from beeoffice.plugins.beesheet_model import SheetDataModel

# ==================== Mixin 层 ====================
from beeoffice.plugins.beesheet_formula_mixin import FormulaMixin
from beeoffice.plugins.beesheet_style_mixin import StyleMixin
from beeoffice.plugins.beesheet_audit_mixin import AuditMixin
from beeoffice.plugins.beesheet_data_mixin import DataMixin
from beeoffice.plugins.beesheet_chart_mixin import ChartMixin
from beeoffice.plugins.beesheet_context_menu_mixin import ContextMenuMixin
from beeoffice.plugins.beesheet_rowcol_mixin import RowColMixin
from beeoffice.plugins.beesheet_ui_mixin import UIMixin


# ==================== 主视图 ====================
class BeeSheetView(
    FormulaMixin,
    StyleMixin,
    AuditMixin,
    DataMixin,
    ChartMixin,
    ContextMenuMixin,
    RowColMixin,
    UIMixin,
    QWidget,
):
    """蜜算主视图（组装层）"""

    FUNCTION_REFERENCE = {}

    # ==================== 初始化 ====================
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BeeSheet")

        # ---------- 函数参考表（来自 UIMixin） ----------
        self._init_function_reference()

        # ---------- 数据模型 ----------
        self.model = SheetDataModel(self)
        self.model._conditional_formats_ref = self._conditional_formats = {}

        # ---------- 撤销 / 重做 ----------
        self._undo_stack, self._redo_stack = [], []
        self._dirty = False

        # ---------- 单元格附加数据 ----------
        self._cell_comments = {}
        self._active_filters = {}
        self._merged_cells = {}
        self._last_snapshot = None
        self._formula_cells = {}
        self._data_validations = {}
        self._named_ranges = {}
        self._cell_formats = {}
        self._audit_cells = set()
        self._highlight_cells = set()
        self._table_style = None

        # ---------- 冻结行列计数 ----------
        self._frozen_rows = 0
        self._frozen_cols = 0

        # ---------- 大文件加载器 ----------
        self._large_file_loader = None

        # ---------- 工具栏折叠状态 ----------
        self._toolbar_visible = True

        # ---------- 关联到 model ----------
        self.model._comments_ref = self._cell_comments
        self.model._formulas_ref = self._formula_cells
        self.model._cell_formats_ref = self._cell_formats
        self.model._validations_ref = self._data_validations
        self.model._named_ranges_ref = self._named_ranges
        self.model._audit_cells_ref = self._audit_cells
        self.model._table_style_ref = None
        self.model._get_sheet_data = self._get_sheet_data
        self.model._get_sheet_names = self._get_sheet_names

        # ---------- 冻结视图（禁用：避免表头丢失 bug） ----------
        self._frozen_top = None
        self._frozen_left = None
        self._frozen_corner = None

        # ---------- 参数气泡（来自 UIMixin） ----------
        self._build_param_tip()

        # ---------- 5 行工具栏（来自 UIMixin） ----------
        self._build_all_toolbars()

        # ---------- 主表格 + 填充柄（来自 UIMixin） ----------
        self._build_table_view()

        # ---------- 函数自动补全下拉（来自 UIMixin） ----------
        self._build_completion_popup()

        # ---------- 底部信息面板（来自 UIMixin） ----------
        self._build_info_panel()

        # ---------- 快捷键（来自 UIMixin） ----------
        self._build_shortcuts()

        # ---------- 加载器 + 自动保存定时器（来自 UIMixin） ----------
        self._init_loaders_and_timers()

        # ---------- 组装布局 ----------
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._toolbar_container)
        layout.addWidget(self.table_view)
        layout.addWidget(self._info_panel)

    # ==================== 基础功能 ====================
    def _f2_edit(self):
        """F2：进入单元格编辑"""
        idx = self.table_view.currentIndex()
        if idx.isValid():
            self.table_view.edit(idx)

    def _insert_date_time(self, mode):
        """
        插入当前日期或时间
        :param mode: 'date' 插入日期，'time' 插入时间
        """
        idx = self.table_view.currentIndex()
        if not idx.isValid():
            return
        val = (datetime.now().strftime('%Y-%m-%d') if mode == 'date'
               else datetime.now().strftime('%H:%M:%S'))
        old = self.model.get_value(idx.row(), idx.column())
        self._push_command(
            EditCellCommand(idx.row(), idx.column(), old, val)
        )
        self.model.setData(idx, val)

    def _toggle_toolbars(self, btn):
        """折叠 / 展开插入工具栏（第 2~5 行）"""
        self._toolbar_visible = not self._toolbar_visible
        for tb in [self._t2, self._t3, self._t4, self._t5]:
            for i in range(tb.count()):
                w = tb.itemAt(i).widget()
                if w and w != btn:
                    w.setVisible(self._toolbar_visible)
        btn.setText("▲ 隐藏" if self._toolbar_visible else "▼ 展开")

    # ==================== 事件处理（单元格选择） ====================
    def _on_selection_changed(self):
        """选中区域变化：刷新状态栏 + 填充柄位置"""
        self._update_status()
        self._update_fill_handle_position()

    def _on_cell_clicked(self, index):
        """单击单元格：更新名称框"""
        if index.isValid():
            self._name_box.setText(
                f"{col_index_to_name(index.column())}{index.row()+1}"
            )

    def _on_cell_selected(self, current, previous):
        """当前单元格变化：同步公式栏 / 名称框 / 格式按钮 / 信息面板"""
        if not current.isValid():
            return
        key = (current.row(), current.column())
        # 优先显示公式原文
        if key in self._formula_cells:
            self.formula_bar.setText(self._formula_cells[key])
        else:
            val = self.model.get_value(current.row(), current.column())
            self.formula_bar.setText(str(val) if not pd.isna(val) else "")
        self._name_box.setText(
            f"{col_index_to_name(current.column())}{current.row()+1}"
        )
        if hasattr(self, '_sync_format_buttons'):
            self._sync_format_buttons()
        if hasattr(self, '_update_info_panel'):
            self._update_info_panel()
        if hasattr(self, '_clear_highlight'):
            self._clear_highlight()

    def _on_cell_double_clicked(self, index):
        """双击单元格：错误单元格弹错误助手，否则进入编辑"""
        if not index.isValid():
            return
        key = (index.row(), index.column())
        val = str(self.model.get_value(index.row(), index.column()))
        if val.startswith('#ERROR') or val.startswith('#N/A'):
            self._show_error_helper(key, val)
            return
        self.table_view.edit(index)

    # ==================== 填充柄（事件处理） ====================
    def _update_fill_handle_position(self):
        """根据当前选区右下角，定位填充柄位置"""
        if not hasattr(self, '_fill_handle'):
            return
        sel = self.table_view.selectionModel().selection()
        if not sel or not sel.indexes():
            self._fill_handle.hide()
            return
        indexes = sel.indexes()
        max_row = max(i.row() for i in indexes)
        max_col = max(i.column() for i in indexes)
        idx = self.model.index(max_row, max_col)
        rect = self.table_view.visualRect(idx)
        if not rect.isValid():
            self._fill_handle.hide()
            return
        x = rect.right() - 4
        y = rect.bottom() - 4
        self._fill_handle.move(x, y)
        self._fill_handle.raise_()
        self._fill_handle.show()

    def _fill_handle_press(self, event):
        """填充柄按下：记录起始选区"""
        if event.button() != Qt.LeftButton:
            return
        sel = self.table_view.selectionModel().selection()
        if not sel or not sel.indexes():
            return
        indexes = sel.indexes()
        self._fill_start_range = (
            min(i.row() for i in indexes),
            min(i.column() for i in indexes),
            max(i.row() for i in indexes),
            max(i.column() for i in indexes),
        )
        self._fill_direction = None
        self._fill_target = None
        try:
            self._fill_handle.grabMouse()
        except Exception:
            pass
        event.accept()

    def _fill_handle_move(self, event):
        """填充柄拖动：判定填充方向（下 / 右）"""
        if self._fill_start_range is None:
            return
        try:
            global_pos = event.globalPosition().toPoint()
        except AttributeError:
            global_pos = event.globalPos()
        local_pos = self.table_view.viewport().mapFromGlobal(global_pos)
        idx = self.table_view.indexAt(local_pos)
        if not idx.isValid():
            return
        sr, sc, er, ec = self._fill_start_range
        if idx.row() > er and idx.column() <= ec:
            self._fill_direction = "down"
            self._fill_target = idx.row()
        elif idx.column() > ec and idx.row() <= er:
            self._fill_direction = "right"
            self._fill_target = idx.column()
        else:
            self._fill_direction = None
        event.accept()

    def _fill_handle_release(self, event):
        """填充柄松开：执行填充（支持公式相对引用调整）"""
        try:
            self._fill_handle.releaseMouse()
        except Exception:
            pass
        if self._fill_start_range is None or self._fill_direction is None:
            self._fill_start_range = None
            self._fill_direction = None
            self._fill_target = None
            return
        sr, sc, er, ec = self._fill_start_range
        try:
            if self._fill_direction == "down":
                target = self._fill_target
                for r in range(er + 1, target + 1):
                    for c in range(sc, ec + 1):
                        src_r = sr + ((r - sr - 1) % (er - sr + 1))
                        if (src_r, c) in self._formula_cells:
                            src_formula = self._formula_cells[(src_r, c)]
                            new_formula = adjust_formula_refs(
                                src_formula, r - src_r, 0
                            )
                            result = FormulaEngine.evaluate(
                                new_formula, self.model
                            )
                            # 自动扩展行数
                            while r >= len(self.model._loaded_df):
                                self.model._loaded_df.loc[
                                    len(self.model._loaded_df)
                                ] = [None] * len(self.model._loaded_df.columns)
                                self.model._total_rows = \
                                    len(self.model._loaded_df)
                            self.model._loaded_df.iloc[r, c] = result
                            self._formula_cells[(r, c)] = new_formula
                        else:
                            val = self.model.get_value(src_r, c)
                            while r >= len(self.model._loaded_df):
                                self.model._loaded_df.loc[
                                    len(self.model._loaded_df)
                                ] = [None] * len(self.model._loaded_df.columns)
                                self.model._total_rows = \
                                    len(self.model._loaded_df)
                            self.model._loaded_df.iloc[r, c] = val
                self.model.layoutChanged.emit()
            elif self._fill_direction == "right":
                target = self._fill_target
                for c in range(ec + 1, target + 1):
                    while c >= len(self.model._loaded_df.columns):
                        self.model._loaded_df[
                            f"列{len(self.model._loaded_df.columns)+1}"
                        ] = ''
                        self.model._total_cols = \
                            len(self.model._loaded_df.columns)
                    for r in range(sr, er + 1):
                        src_c = sc + ((c - sc - 1) % (ec - sc + 1))
                        if (r, src_c) in self._formula_cells:
                            src_formula = self._formula_cells[(r, src_c)]
                            new_formula = adjust_formula_refs(
                                src_formula, 0, c - src_c
                            )
                            result = FormulaEngine.evaluate(
                                new_formula, self.model
                            )
                            self.model._loaded_df.iloc[r, c] = result
                            self._formula_cells[(r, c)] = new_formula
                        else:
                            val = self.model.get_value(r, src_c)
                            self.model._loaded_df.iloc[r, c] = val
                self.model.layoutChanged.emit()
            self._recalc_formulas()
            self._set_status(f"✅ 已填充", 2000)
        finally:
            self._fill_start_range = None
            self._fill_direction = None
            self._fill_target = None

    # ==================== 导入 / 导出 ====================
    def _import_file(self):
        """导入文件入口：CSV / Excel / TXT"""
        path, _ = QFileDialog.getOpenFileName(
            self, "导入", "",
            "所有支持格式 (*.csv *.xlsx *.xls *.txt);;所有 (*)"
        )
        if path:
            try:
                size_mb = os.path.getsize(path) / (1024 * 1024)
            except Exception:
                size_mb = 0
            # 大文件提示：>50MB 询问是否分块加载
            if size_mb > 50:
                reply = QMessageBox.question(
                    self, "大文件",
                    f"文件大小 {size_mb:.1f} MB，是否使用分块加载？\n"
                    f"（推荐，可避免界面卡顿）",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
                )
                if reply == QMessageBox.Yes:
                    self.load_large_file(path)
                    return
            if path.endswith('.txt'):
                self._import_text_file(path)
            else:
                self._import_file_from_path(path)

    def load_large_file(self, path, chunk_size=50000):
        """
        大文件分块加载（P0-15：支持取消）

        :param path: 文件路径
        :param chunk_size: 每块行数
        """
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)
        self._cancel_load_btn.setVisible(True)
        self._set_status(f"正在分块加载: {Path(path).name}")

        def on_progress(pct):
            self._progress_bar.setValue(pct)

        def on_finished(full_df):
            self._progress_bar.setVisible(False)
            self._cancel_load_btn.setVisible(False)
            self.model.set_full_dataframe(full_df)
            self.table_view.setModel(self.model)
            self._undo_stack.clear()
            self._redo_stack.clear()
            self._auto_resize_columns()
            self._set_status(
                f"✅ 已加载: {len(full_df):,} 行 × {len(full_df.columns)} 列",
                5000
            )

        def on_error(err):
            self._progress_bar.setVisible(False)
            self._cancel_load_btn.setVisible(False)
            QMessageBox.warning(self, "加载失败", err)
            self._set_status("加载失败", 3000)

        def on_cancelled():
            # P0-15：加载被取消
            self._progress_bar.setVisible(False)
            self._cancel_load_btn.setVisible(False)
            self._set_status("已取消加载", 3000)

        self._large_file_loader = LargeFileLoader(path, chunk_size, self)
        self._large_file_loader.progress_updated.connect(on_progress)
        self._large_file_loader.finished_loading.connect(on_finished)
        self._large_file_loader.error_occurred.connect(on_error)
        self._large_file_loader.cancelled.connect(on_cancelled)
        self._large_file_loader.start()

    def _cancel_large_file_load(self):
        """取消正在进行的加载（P0-15）"""
        if (self._large_file_loader is not None
                and self._large_file_loader.isRunning()):
            self._large_file_loader.requestInterruption()
            self._set_status("正在取消加载...", 2000)

    def _import_text_file(self, path):
        """导入纯文本文件（按 Tab 分列，否则整行一列）"""
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            data = [
                line.strip().split('\t') if '\t' in line else [line.strip()]
                for line in lines if line.strip()
            ]
            df = pd.DataFrame(data)
            self.model.set_full_dataframe(df)
            self.table_view.setModel(self.model)
            self._auto_resize_columns()
            self._set_status(f"已加载文本: {len(df)} 行")
        except Exception as e:
            QMessageBox.warning(self, "导入失败", str(e))

    # ==================== 导入（IO 与 UI 分离） ====================
    def _read_sheet_file(self, path, nrows=200001):
        """
        读取 CSV / Excel 为 DataFrame（**纯 IO，可在后台线程执行**）。

        线程安全（P0）：
            原 _import_file_from_path 同时做 IO 与 UI，被 app.py 丢进
            AsyncTaskManager 后，在 worker 线程里 setModel 并弹 QMessageBox，
            属于跨线程操作 Qt 对象（随机崩溃/界面错乱的来源）。

            现在拆成两半：
              - _read_sheet_file       纯读取，不含任何 Qt 调用 → 后台线程
              - _apply_imported_dataframe  改模型/弹框 → 必须 GUI 线程

        默认只读 200001 行，用于判断是否需要提示截断；
        真正的截断决定在 _apply_imported_dataframe 里做。

        :param nrows: 最多读取的行数（默认 200001）
        :return: DataFrame
        """
        ext = os.path.splitext(path)[1].lower()
        if ext == '.csv':
            import chardet
            with open(path, 'rb') as f:
                raw = f.read(10000)
            return pd.read_csv(
                path,
                encoding=chardet.detect(raw).get('encoding', 'utf-8'),
                nrows=nrows,
            )
        return pd.read_excel(path, engine='openpyxl', nrows=nrows)

    def _apply_imported_dataframe(self, df, path):
        """
        把已读取的 DataFrame 应用到界面（**必须在 GUI 线程执行**）。

        :return: 是否应用成功（用户在"是否截断"对话框里选否时返回 False）
        """
        if len(df) > 200000:
            reply = QMessageBox.question(
                self, "提示", f"文件有{len(df)}行，仅加载前20万行？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
            )
            if reply != QMessageBox.Yes:
                return False
            df = df.head(200000)

        self.model.set_full_dataframe(df)
        self.table_view.setModel(self.model)
        self._undo_stack.clear()
        self._redo_stack.clear()
        # P0-7：新文件不应继承上一个文件的公式缓存，
        # 否则旧坐标上的公式会在重算时覆盖新数据。
        self._formula_cells.clear()
        self._auto_resize_columns()
        self._set_status(f"已加载：{len(df)} 行 × {len(df.columns)} 列")
        return True

    def _import_file_from_path(self, path):
        """
        同步导入（仅供 GUI 线程调用；拖拽、插件菜单等入口使用）。

        后台导入请改用 _read_sheet_file + _apply_imported_dataframe。
        """
        try:
            df = self._read_sheet_file(path)
        except Exception as e:
            QMessageBox.warning(self, "导入失败", str(e))
            return False
        try:
            return self._apply_imported_dataframe(df, path)
        except Exception as e:
            QMessageBox.warning(self, "导入失败", str(e))
            return False

    def _auto_resize_columns(self):
        """自动调整列宽（在 60~300 之间）"""
        h = self.table_view.horizontalHeader()
        for i in range(self.model.columnCount()):
            h.resizeSection(i, min(max(h.sectionSize(i), 60), 300))

    # ==================== 撤销 / 重做 ====================
    def _push_command(self, cmd):
        """压入命令到撤销栈（最多保留 100 条）"""
        cmd.execute(self.model)
        self._undo_stack.append(cmd)
        if len(self._undo_stack) > 100:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self):
        """撤销"""
        if not self._undo_stack:
            self._set_status("无撤销", 2000)
            return
        cmd = self._undo_stack.pop()
        cmd.undo(self.model)
        self._redo_stack.append(cmd)
        self._set_status(f"↩ 撤销({len(self._undo_stack)}步)", 2000)

    def redo(self):
        """重做"""
        if not self._redo_stack:
            self._set_status("无重做", 2000)
            return
        cmd = self._redo_stack.pop()
        cmd.execute(self.model)
        self._undo_stack.append(cmd)
        self._set_status(f"↪ 重做({len(self._redo_stack)}步)", 2000)

    # ==================== 排序 ====================
    def sort_by_column(self, col, ascending=True):
        """按列排序"""
        old = self.model.df.copy()
        self.model._loaded_df = self.model.df.sort_values(
            by=self.model.df.columns[col], ascending=ascending,
            ignore_index=True
        )
        self._push_command(SortCommand(old, self.model._loaded_df))
        self._set_status("已排序")

    def _show_sort_dialog(self):
        """排序对话框（选择列 + 升/降序）"""
        dlg = QDialog(self)
        form = QFormLayout(dlg)
        cc = QComboBox()
        cc.addItems(list(self.model.df.columns))
        form.addRow("列:", cc)
        oc = QComboBox()
        oc.addItems(["升序", "降序"])
        form.addRow("顺序:", oc)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(
            lambda: [self.sort_by_column(cc.currentIndex(),
                                          oc.currentText() == "升序"),
                     dlg.accept()]
        )
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        dlg.exec()

    # ==================== 滚动 ====================
    def _on_scroll_changed(self, value):
        """滚动时触发分块加载 + 更新填充柄"""
        if self.model.is_streaming:
            vp = self.table_view.viewport()
            top = self.table_view.indexAt(vp.rect().topLeft())
            bottom = self.table_view.indexAt(vp.rect().bottomLeft())
            if top.isValid() and bottom.isValid():
                sr = max(0, top.row() - self.model.PRELOAD_MARGIN)
                er = min(self.model._total_rows - 1,
                         bottom.row() + self.model.PRELOAD_MARGIN)
                needed = self.model.needs_chunks_for_range(sr, er)
                if needed:
                    self._chunk_loader.add_chunks(needed)
        if hasattr(self, '_update_fill_handle_position'):
            self._update_fill_handle_position()

    def _on_loading_progress(self, p):
        """分块加载进度"""
        if p < 1.0:
            self._progress_bar.setVisible(True)
            self._progress_bar.setValue(int(p * 100))
        else:
            self._progress_bar.setVisible(False)

    def _on_all_loaded(self):
        """所有分块加载完成"""
        self._auto_resize_columns()
        self._set_status(f"加载完成", 5000)

    # ==================== 状态栏 ====================
    def _update_status(self):
        """刷新状态栏（选中数量 / 求和 / 平均 / 空值 / 冻结信息）"""
        sel = self.table_view.selectionModel().selection()
        if not sel:
            self.status_label.setText("")
            return
        indexes = sel.indexes()
        if not indexes:
            self.status_label.setText("")
            return
        values, empty = [], 0
        for idx in indexes:
            v = self.model.get_value(idx.row(), idx.column())
            if v is None or str(v).strip() == '':
                empty += 1
            else:
                try:
                    values.append(float(v))
                except (ValueError, TypeError):
                    pass
        freeze_info = ""
        if self._frozen_rows > 0 or self._frozen_cols > 0:
            freeze_info = (f" | 📌冻结:{self._frozen_rows}行"
                           f"{self._frozen_cols}列")
        if values:
            self.status_label.setText(
                f"计数:{len(values)} | 求和:{sum(values):,.2f} | "
                f"平均:{sum(values)/len(values):,.2f} | "
                f"空值:{empty}{freeze_info}"
            )
        else:
            self.status_label.setText(
                f"选中:{len(indexes)} | 空值:{empty}{freeze_info}"
            )

    def _set_status(self, msg, timeout=0):
        """
        在状态标签上显示消息
        :param msg: 消息文本
        :param timeout: 超时自动清空（毫秒），0 表示不自动清空
        """
        self.status_label.setText(msg)
        if timeout > 0:
            QTimer.singleShot(timeout,
                              lambda: self.status_label.setText(""))

    def _update_info_panel(self):
        """刷新底部信息面板（坐标 / 值 / 公式 / 批注）"""
        if not hasattr(self, '_info_panel'):
            return
        idx = self.table_view.currentIndex()
        if not idx.isValid():
            self._info_panel.setVisible(False)
            return
        r, c = idx.row(), idx.column()
        key = (r, c)
        cell_ref = f"{col_index_to_name(c)}{r+1}"
        self._info_cell.setText(f"📍 {cell_ref}")
        val = self.model.get_value(r, c)
        if pd.isna(val) or val == '':
            self._info_value.setText("值：（空）")
        else:
            text = str(val)
            if len(text) > 30:
                text = text[:30] + "..."
            self._info_value.setText(f"值：{text}")
        if key in self._formula_cells:
            f = self._formula_cells[key]
            if len(f) > 40:
                f = f[:40] + "..."
            self._info_formula.setText(f"ƒ {f}")
        else:
            self._info_formula.setText("")
        if key in self._cell_comments:
            cmt = self._cell_comments[key]
            if len(cmt) > 30:
                cmt = cmt[:30] + "..."
            self._info_comment.setText(f"💬 {cmt}")
        else:
            self._info_comment.setText("")
        self._info_panel.setVisible(True)

    # ==================== 定位 ====================
    def _show_goto_dialog(self):
        """定位对话框（支持单元格引用 + 命名区域）"""
        dlg = QDialog(self)
        dlg.setWindowTitle("🔍 定位")
        dlg.resize(360, 180)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("输入单元格引用（如 A1、B10、A1:C20）："))
        edit = QLineEdit()
        edit.setPlaceholderText("例如：A1  或  B10:D20")
        cur = self.table_view.currentIndex()
        if cur.isValid():
            edit.setText(
                f"{col_index_to_name(cur.column())}{cur.row()+1}"
            )
        layout.addWidget(edit)

        # 已定义的命名区域下拉
        if self._named_ranges:
            layout.addWidget(QLabel("或选择已定义的名称："))
            name_combo = QComboBox()
            name_combo.addItem("—")
            for name in sorted(self._named_ranges.keys()):
                name_combo.addItem(name)
            layout.addWidget(name_combo)

            def on_name_selected(text):
                if text and text != "—":
                    edit.setText(self._named_ranges[text])
            name_combo.currentTextChanged.connect(on_name_selected)

        bl = QHBoxLayout()
        bl.addStretch()
        ok_btn = QPushButton("定位")
        ok_btn.setStyleSheet(
            "QPushButton{background:#FFB300;color:#000;padding:6px 16px;"
            "border:none;border-radius:4px;font-weight:bold;}"
        )
        ok_btn.clicked.connect(
            lambda: [self._goto_cell(edit.text().strip()), dlg.accept()]
        )
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(dlg.reject)
        bl.addWidget(ok_btn)
        bl.addWidget(cancel_btn)
        layout.addLayout(bl)
        dlg.exec()
        edit.setFocus()

    def _goto_cell(self, ref):
        """跳转到指定单元格或区域"""
        if not ref:
            return
        ref = ref.upper().replace('$', '')
        # 区域引用：A1:B10
        m = re.match(r'^([A-Z]+)(\d+):([A-Z]+)(\d+)$', ref)
        if m:
            c1s, r1s, c2s, r2s = m.groups()
            c1 = col_name_to_index(c1s)
            c2 = col_name_to_index(c2s)
            r1 = int(r1s) - 1
            r2 = int(r2s) - 1
            top_left = self.model.index(r1, c1)
            bottom_right = self.model.index(r2, c2)
            if top_left.isValid() and bottom_right.isValid():
                sel = QItemSelection(top_left, bottom_right)
                self.table_view.selectionModel().select(
                    sel, QItemSelectionModel.ClearAndSelect
                )
                self.table_view.setCurrentIndex(top_left)
                self.table_view.scrollTo(top_left)
                self._set_status(f"✅ 已选中区域 {ref}", 2000)
            return
        # 单单元格：A1
        m = re.match(r'^([A-Z]+)(\d+)$', ref)
        if m:
            cs, rs = m.groups()
            c = col_name_to_index(cs)
            r = int(rs) - 1
            idx = self.model.index(r, c)
            if idx.isValid():
                self.table_view.setCurrentIndex(idx)
                self.table_view.scrollTo(idx)
                self._set_status(f"✅ 已跳转到 {ref}", 2000)
            else:
                self._set_status(f"⚠️ 超出范围：{ref}", 3000)
            return
        QMessageBox.warning(self, "格式错误",
                             "请输入有效的引用（如 A1、B10:D20）")

    # ==================== 自然语言 ====================
    def _nl_to_formula(self):
        """自然语言生成公式（从 NLFormulaParser 解析中文指令）"""
        from beeoffice.plugins.nl_formula import NLFormulaParser
        idx = self.table_view.currentIndex()
        default_hint = ("例如：求和A1到A10  /  平均值B列  /  "
                        "筛选大于100的行  /  如果A1大于10就显示'高'")
        text, ok = QInputDialog.getText(
            self, "💬 自然语言生成公式",
            f"请输入中文指令：\n（{default_hint}）"
        )
        if not ok or not text.strip():
            return
        result = NLFormulaParser.parse(text.strip())
        if not result:
            QMessageBox.warning(
                self, "无法解析",
                "无法理解指令，请尝试：\n\n"
                "• 求和A1到A10\n"
                "• 平均值B列\n"
                "• 最大值A1到A5\n"
                "• 筛选大于100的行\n"
                "• 如果A1大于10就显示'高'\n"
                "• 合并A1和B1"
            )
            return
        # FILTER 指令：走筛选流程
        if result.startswith("FILTER:"):
            parts = result.split(":")
            op = parts[1] if len(parts) > 1 else ""
            value = parts[2] if len(parts) > 2 else ""
            self._apply_nl_filter(op, value)
            return
        # VLOOKUP 提示
        if result == "VLOOKUP":
            QMessageBox.information(
                self, "VLOOKUP",
                "请手动在单元格输入 VLOOKUP 公式：\n\n"
                "=VLOOKUP(查找值, 表范围, 列号, FALSE)"
            )
            return
        if not idx.isValid():
            QMessageBox.information(self, "提示", "请先选择一个单元格")
            return
        old = self.model.get_value(idx.row(), idx.column())
        self._push_command(
            EditCellCommand(idx.row(), idx.column(), old, result)
        )
        self.model.setData(idx, result)
        self.formula_bar.setText(result)
        self._set_status(f"✅ 已生成公式: {result}", 5000)

    def _apply_nl_filter(self, op, value):
        """应用自然语言筛选指令"""
        if not hasattr(self.model, 'df') or self.model.df is None \
           or self.model.df.empty:
            QMessageBox.information(self, "提示", "请先导入数据")
            return
        if not op or not value:
            QMessageBox.information(self, "提示", "筛选条件不完整")
            return
        df = self.model.df
        target_col = df.columns[0]
        try:
            if op in (">", ">=", "<", "<=", "="):
                num_val = float(value)
                series = pd.to_numeric(df[target_col], errors='coerce')
                if op == ">":
                    mask = series > num_val
                elif op == ">=":
                    mask = series >= num_val
                elif op == "<":
                    mask = series < num_val
                elif op == "<=":
                    mask = series <= num_val
                else:
                    mask = series == num_val
            elif op == "contains":
                mask = df[target_col].astype(str).str.contains(
                    value, case=False, na=False
                )
            else:
                mask = df[target_col].astype(str) == value
        except Exception as e:
            QMessageBox.warning(self, "筛选失败", str(e))
            return
        filtered = df[mask].copy()
        if filtered.empty:
            QMessageBox.information(self, "提示", "筛选结果为空")
            return
        self.model._loaded_df = filtered
        self.model.layoutChanged.emit()
        self._set_status(f"✅ 筛选完成：{len(filtered)} 行", 3000)

    # ==================== 查找替换 ====================
    def _show_find_replace(self):
        """查找替换对话框"""
        dlg = QDialog(self)
        dlg.setWindowTitle("查找替换")
        dlg.resize(400, 200)
        layout = QVBoxLayout(dlg)
        form = QFormLayout()
        fi = QLineEdit()
        form.addRow("查找:", fi)
        ri = QLineEdit()
        form.addRow("替换:", ri)
        mc = QCheckBox("区分大小写")
        form.addRow(mc)
        layout.addLayout(form)
        rl = QLabel("")
        layout.addWidget(rl)
        bl = QHBoxLayout()

        def fn():
            """查找：逐单元格匹配，找到后选中"""
            t = fi.text()
            if not t:
                return
            for cn in self.model.df.columns:
                ci = self.model.df.columns.get_loc(cn)
                for ri_idx in range(len(self.model.df)):
                    if re.search(
                        t, str(self.model.get_value(ri_idx, ci)),
                        0 if mc.isChecked() else re.IGNORECASE
                    ):
                        self.table_view.setCurrentIndex(
                            self.model.index(ri_idx, ci)
                        )
                        rl.setText("找到")
                        return
            rl.setText("未找到")

        def ra():
            """全部替换"""
            ft = fi.text()
            rt = ri.text()
            if not ft:
                return
            count = 0
            for cn in self.model.df.columns:
                ci = self.model.df.columns.get_loc(cn)
                for ri_idx in range(len(self.model.df)):
                    cv = str(self.model.get_value(ri_idx, ci))
                    nv = re.sub(
                        ft, rt, cv,
                        flags=0 if mc.isChecked() else re.IGNORECASE
                    )
                    if nv != cv:
                        self.model._loaded_df.iloc[ri_idx, ci] = nv
                        count += 1
            self.model.dataChanged.emit(
                self.model.index(0, 0),
                self.model.index(len(self.model.df) - 1,
                                  len(self.model.df.columns) - 1)
            )
            rl.setText(f"已替换{count}处")

        bl.addWidget(QPushButton("查找", clicked=fn))
        bl.addWidget(QPushButton("替换", clicked=ra))
        bl.addWidget(QPushButton("关闭", clicked=dlg.close))
        layout.addLayout(bl)
        dlg.exec()

    # ==================== 批注 ====================
    def _add_comment(self):
        """为当前单元格添加 / 编辑 / 删除批注"""
        idx = self.table_view.currentIndex()
        if not idx.isValid():
            return
        ck = (idx.row(), idx.column())
        ex = self._cell_comments.get(ck, "")
        text, ok = QInputDialog.getMultiLineText(self, "批注", "批注:", ex)
        if ok:
            if text.strip():
                self._cell_comments[ck] = text.strip()
            elif ck in self._cell_comments:
                del self._cell_comments[ck]
            self.model.dataChanged.emit(idx, idx)

    # ==================== 自动保存 ====================
    def _auto_save(self):
        """自动保存（每 5 分钟，写入 ~/.beeoffice_backups/）"""
        if not self._dirty:
            return
        try:
            backup_dir = Path.home() / ".beeoffice_backups"
            backup_dir.mkdir(exist_ok=True)
            bp = backup_dir / (
                f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            df = self._trim_empty_tail(self.model.df.copy())
            with open(bp, 'w', encoding='utf-8') as f:
                f.write(df.to_json(orient='split', force_ascii=False))
            self._dirty = False
            # 只保留最近 10 个备份
            for old in sorted(backup_dir.glob("backup_*.json"))[:-10]:
                old.unlink()
        except Exception:
            pass

    # ==================== 工具方法 ====================
    def _find_main_window(self):
        """向上查找主窗口（带 tab_manager 的对象）"""
        p = self
        while p:
            if hasattr(p, 'tab_manager'):
                return p
            p = p.parent()
        return None

    def _get_sheet_names(self):
        """获取所有蜜算标签页的名称（供跨表引用使用）"""
        parent = self._find_main_window()
        if not parent or not hasattr(parent, 'tab_manager'):
            return []
        names = []
        for i in range(parent.tab_manager.count()):
            widget = parent.tab_manager.widget(i)
            title = parent.tab_manager.tabText(i)
            clean = title.replace("📊 ", "").replace("● ", "").strip()
            if hasattr(widget, 'model') and hasattr(widget.model, 'df'):
                names.append(clean)
        return names

    def _get_sheet_data(self, sheet_name):
        """根据标签页名称获取 DataFrame（供跨表引用使用）"""
        parent = self._find_main_window()
        if not parent or not hasattr(parent, 'tab_manager'):
            return None
        sheet_name_upper = sheet_name.upper()
        for i in range(parent.tab_manager.count()):
            widget = parent.tab_manager.widget(i)
            title = parent.tab_manager.tabText(i)
            clean = title.replace("📊 ", "").replace("● ", "").strip()
            if (clean.upper() == sheet_name_upper or
                    clean.upper().startswith(sheet_name_upper + "-") or
                    clean.upper().startswith(sheet_name_upper + "_")):
                if hasattr(widget, 'model') and hasattr(widget.model, 'df'):
                    return widget.model.df
        return None

    def _col_index_to_name(self, index):
        """列索引 → 字母（工具方法，供 AuditMixin 等调用）"""
        return col_index_to_name(index)

    def _col_name_to_index(self, col_str):
        """字母 → 列索引（工具方法）"""
        return col_name_to_index(col_str)

    # ==================== 关闭事件 ====================
    def closeEvent(self, event):
        """关闭时清理：停线程 / 停定时器（P0-15：中断大文件加载）"""
        # 停止分块加载线程
        if hasattr(self, '_chunk_loader'):
            self._chunk_loader.stop()
            self._chunk_loader.wait(1000)

        # 中断大文件加载
        if hasattr(self, '_large_file_loader') and \
           self._large_file_loader is not None:
            try:
                # P0-15：请求中断正在进行的加载
                self._large_file_loader.requestInterruption()
                self._large_file_loader.quit()
                self._large_file_loader.wait(2000)
            except Exception:
                pass

        # 停止自动保存定时器
        if hasattr(self, '_auto_save_timer'):
            self._auto_save_timer.stop()

        event.accept()