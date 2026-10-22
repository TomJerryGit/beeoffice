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
import uuid
import logging
from pathlib import Path
from datetime import datetime

from beeoffice.utils import atomic_write_text, get_app_data_dir

import pandas as pd

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QMessageBox, QDialog, QComboBox, QDialogButtonBox,
    QInputDialog,
    QFormLayout, QCheckBox,
)
from PySide6.QtCore import (
    Qt, QTimer, QItemSelectionModel, QItemSelection, Signal, QThread,
)

from beeoffice.plugins.beesheet_utils import (
    adjust_formula_refs, col_index_to_name, col_name_to_index,
)
from beeoffice.plugins.beesheet_commands import (
    EditCellCommand, SortCommand,
)
from beeoffice.plugins.beesheet_loaders import LargeFileLoader
from beeoffice.plugins.beesheet_engine import FormulaEngine
from beeoffice.plugins.beesheet_model import SheetDataModel
from beeoffice.i18n import tr

# ==================== Mixin 层 ====================
from beeoffice.plugins.beesheet_formula_mixin import FormulaMixin
from beeoffice.plugins.beesheet_style_mixin import StyleMixin
from beeoffice.plugins.beesheet_audit_mixin import AuditMixin
from beeoffice.plugins.beesheet_data_mixin import DataMixin
from beeoffice.plugins.beesheet_chart_mixin import ChartMixin
from beeoffice.plugins.beesheet_context_menu_mixin import ContextMenuMixin
from beeoffice.plugins.beesheet_rowcol_mixin import RowColMixin
from beeoffice.plugins.beesheet_ui_mixin import UIMixin
from beeoffice.plugins.beesheet_print_mixin import SheetPrintMixin
from beeoffice.plugins.beesheet_ai_mixin import SheetAIMixin


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
    SheetPrintMixin,
    SheetAIMixin,
    QWidget,
):
    """蜜算主视图（组装层）"""

    #: 内容变化信号（供标签页的"● 未保存"标记 —— `tab_manager.addTab` 会接它）
    contentChanged = Signal()

    #: 大表阶段 2（后台补全）请求信号。
    #: 阶段 1 在 `_import_file_from_path` 里执行，而它被 `_open_sheet_file` 放到
    #: **工作线程**；工作线程里再调 `AsyncTaskManager.run`，其回调不会落到主线程
    #: 事件循环（PySide6 的 AutoConnection 按连接时线程排队 → 无事件循环的线程
    #: 永远收不到）——实测 30 万行表后台补全"完成但界面永远 1000 行"。
    #: 因此把"启动阶段 2"通过本信号发回主线程，由主线程再启动后台任务。
    phase2_requested = Signal(str)

    FUNCTION_REFERENCE = {}

    # ==================================================================
    # 内容接口（标签页未保存检查用）
    # ==================================================================
    def content(self) -> str:
        """
        返回当前表格的**轻量内容签名**（形状 + 内容哈希）。

        用途只有一个：让 `tab_manager` 能判断"内容变没变"，
        从而在**关标签时提示未保存**（原先蜜算没有这个方法 →
        关标签一路静默丢弃）。

        ⚠️ 为什么返回签名而不是整表 CSV：粘性检查会在**每次关闭标签**时调用，
        几十万行的表做 `to_csv` 是几百毫秒到秒级；而
        `hash_pandas_object` 是向量化的 O(n)，且**对任何单元格改动都敏感**。
        注意它**不是给人看的文本** —— `mobile.py` 的渲染分支有
        `not hasattr(widget, "model")` 守卫，所以蜜算不会拿它当文档内容。
        """
        df = getattr(self.model, "df", None)
        if df is None or getattr(df, "empty", True):
            return ""
        shape = f"{len(df)}x{len(df.columns)}"
        try:
            import hashlib

            import pandas as pd

            digest = hashlib.sha1(
                pd.util.hash_pandas_object(df, index=True).values.tobytes()
            ).hexdigest()[:16]
            return f"{shape}:{digest}"
        except Exception:            # 极端 dtype 等情况下降级为形状
            return shape

    def _on_content_changed(self, *_args):
        """模型有改动 → 通知标签页（点亮"●"未保存标记）。"""
        try:
            self.contentChanged.emit()
        except Exception:            # 控件已销毁时忽略
            pass

    # ==================== 初始化 ====================
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BeeSheet")

        # ---------- 函数参考表（来自 UIMixin） ----------
        self._init_function_reference()

        # ---------- 数据模型 ----------
        self.model = SheetDataModel(self)
        self.model._conditional_formats_ref = self._conditional_formats = {}
        # P0：阶段 2 必须从主线程启动（工作线程启动的 Async 回调收不到）。
        self.phase2_requested.connect(self._start_phase2_full_load)

        # ---------- 撤销 / 重做 ----------
        self._undo_stack, self._redo_stack = [], []
        self._dirty = False

        # ---------- 内容接口（供标签页"未保存检查"用）----------
        # P0 修复：`tab_manager._on_tab_close_request` 靠 `widget.content()`
        # 判断"内容是否变了"，而蜜算原先**没有** `content()` →
        # `initial_content` 被记为 None → **关标签时不提示、直接丢弃**
        # （蜜算自己 5 分钟写一次的会话备份还会在 closeEvent 里被删掉）。
        # 这里补上：`content()` 返回一个**轻量签名**（形状 + 内容哈希），
        # 变化即不同；`contentChanged` 让标签页的"●"未保存标记也能亮。
        self._content_changed_emitted = False
        self.model.dataChanged.connect(self._on_content_changed)
        self.model.layoutChanged.connect(self._on_content_changed)
        self.model.modelReset.connect(self._on_content_changed)

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
        # P1：文件里的冻结窗格状态（**保留**用，不改变界面上"禁用冻结"的现状）
        self._freeze_panes = None
        # P1：批注作者（{(行,列): 作者}）—— 与 `_cell_comments`（文本）分开存，
        # 避免把作者硬编码成假名字覆盖掉文件里的原作者
        self._comment_authors = {}
        # P1：本次会话生成的图表规格（保存时写成**原生 Excel 图表**）
        self._charts = []

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

    # ==================================================================
    # R1：两阶段载入
    #
    # 注意：**安全门 `_ensure_full_data()` 定义在 `DataMixin` 里**
    # （见 `beesheet_data_mixin.py`），不在这里 —— 因为既有的
    # `test_beesheet_export_wiring.py` 用了一个只混入 `DataMixin` 的精简替身
    # 来驱动真实的 `_export_xlsx()`；把门放在视图类上会让那个替身报
    # AttributeError（我第一版就是这么把 4 条既有测试弄挂的）。
    # 放在 mixin 上，替身与真实视图都能用，且只有一处定义。
    # ==================================================================
    #: 阶段 1 只读多少行（目标是"窗口尽快可交互"）
    PHASE1_ROWS = 500
    #: 超过这个大小才走两阶段。
    #: 取 1 MB 的依据：实测 1.4 MB（5000×50）急切载入要 **2.27 s**，
    #: 值得为它做两阶段；更小的文件本身不到 1 秒就开完了，
    #: 走两阶段只会多出复杂度与行为差异。
    LAZY_THRESHOLD_BYTES = 1024 * 1024

    def _start_phase2_full_load(self, path):
        """
        阶段 2：后台读完整数据，完成后**整体替换**模型数据。

        安全性来自"加载期间模型只读"（见 `SheetDataModel.flags`）：
        替换时不可能存在用户改动，因此不需要任何"合并/重放编辑"的逻辑
        —— 那种逻辑正是数据损坏的来源。

        ⚠️ 线程约束（2026-10-21 实测修复）：本方法会被 `_import_file_from_path`
        在**工作线程**里调用；如果直接在该线程 `AsyncTaskManager.run`，完成回调
        永远不会落到主线程（30 万行表永远只显示首屏 1000 行）。因此这里检测
        线程：非主线程 → 发 `phase2_requested` 信号回主线程，再由主线程启动。
        """
        if QThread.currentThread() is not self.thread():
            self.phase2_requested.emit(str(path))
            return

        from beeoffice.async_task import AsyncTaskManager
        from beeoffice.plugins.beesheet_workbook import read_workbook

        # 2026-10-21：进入主线程后再启动后台任务，并给出可见进度提示
        self._set_status(tr("msg.sheet_loading_full"), 0)

        def load_full():
            workbook = read_workbook(path, max_rows=200001)
            df = workbook.sheets[0].df if workbook.sheets else None
            return workbook, df

        def on_result(result):
            workbook, df = result
            model = getattr(self, "model", None)
            if model is None or df is None:
                return
            # 用户可能已经切走了工作表/关了标签：只在仍处于"部分载入"时替换
            if model.is_fully_loaded:
                return
            model.complete_full_dataframe(df)
            self._workbook = workbook
            self._load_full_workbook = workbook
            rows = len(model._loaded_df)
            self._set_status(f"✅ 已加载完整数据（{rows} 行）", 4000)

        def on_error(error):
            model = getattr(self, "model", None)
            if model is not None and not model.is_fully_loaded:
                model.load_error = f"完整数据加载失败：{error}"
                self._set_status(
                    "⚠️ 只加载了前 "
                    f"{self.PHASE1_ROWS} 行且补全失败，"
                    "编辑与保存已禁用",
                    0,
                )

        AsyncTaskManager.run(load_full, on_result=on_result, on_error=on_error)

    # ==================================================================
    # 导入
    # ==================================================================
    def _import_file_from_path(self, path):
        """从路径导入 CSV / Excel（自动检测编码，限制 20 万行）"""
        try:
            ext = os.path.splitext(path)[1].lower()
            # R1：默认不走两阶段（小文件没必要，避免改变既有行为）；
            # 下面 xlsx 分支会按文件大小重新判定。
            # 必须在这里初始化：CSV 分支不会进入 xlsx 分支，
            # 否则后面引用 `lazy` 会 NameError（我第一版就漏了这一步）。
            lazy = False
            if ext == '.csv':
                import chardet
                with open(path, 'rb') as f:
                    raw = f.read(10000)
                df = pd.read_csv(
                    path,
                    encoding=chardet.detect(raw).get('encoding', 'utf-8'),
                    nrows=200001
                )
            else:
                # 保真度阶段 A（docs/fidelity.md 根因 1 第一刀）：
                # 原先 `pd.read_excel(...)` **只读首张工作表、且公式全丢**
                # （实测 9 项特征丢 8 项：sheets 2→1、formulas 4→0）。
                # 现在用 beesheet_workbook 读**全部**工作表与每格公式，
                # 首张表进模型（当前只编辑一张），其余留在工作簿对象里，
                # 导出时原样写回。
                workbook = None
                try:
                    from beeoffice.plugins.beesheet_workbook import (
                        read_workbook,
                    )

                    # R1：**两阶段载入**。大文件先只读前 PHASE1_ROWS 行，
                    # 让窗口尽快可交互；完整数据随后在后台补齐
                    # （期间模型只读，见 _start_phase2_full_load 的说明）。
                    lazy = self._should_lazy_load(path)
                    if lazy:
                        workbook = read_workbook(
                            path, max_rows=self.PHASE1_ROWS
                        )
                    else:
                        workbook = read_workbook(path, max_rows=200001)
                    df = (
                        workbook.sheets[0].df
                        if workbook.sheets else pd.DataFrame()
                    )
                except Exception as e:  # noqa: BLE001 - 回退不应中断导入
                    logging.warning(
                        f"工作簿读取失败，回退为只读首张表: {e}"
                    )
                    workbook = None
                    lazy = False
                    # ⚠️ 引擎按扩展名选：`.xls` 必须走 xlrd（openpyxl 只认 .xlsx）。
                    # 原先写死 `engine='openpyxl'` → 对话框里列着的 .xls
                    # 一选就"导入失败"（审计报告 §2.10 的"假装支持"）。
                    from beeoffice.plugins.beesheet_workbook import (
                        pick_excel_engine,
                    )

                    df = pd.read_excel(
                        path, engine=pick_excel_engine(path), nrows=200001
                    )
            total_rows = len(df)
            if total_rows > 200000:
                if QMessageBox.question(
                    self, "提示", f"文件有{total_rows}行，仅加载前20万行？",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
                ) == QMessageBox.Yes:
                    df = df.head(200000)
            if lazy:
                # 阶段 1：先显示前 PHASE1_ROWS 行（模型此时**只读**），
                # 随后后台补全；补全前禁止编辑，于是阶段 2 的替换永远安全。
                self.model.set_partial_dataframe(df)
            else:
                self.model.set_full_dataframe(df)
            self.table_view.setModel(self.model)
            self._undo_stack.clear()
            self._redo_stack.clear()
            self._auto_resize_columns()

            # 记住工作簿（导出时把全部工作表与公式写回）
            self._workbook = workbook
            self._active_sheet_name = workbook.active if workbook else ""

            # P1：记住"当前文件"，这样 Ctrl+S / 自动保存 / 保存前备份
            # 才有目标（原先蜜算从不设路径 → 上述三件事对蜜算全部失效）。
            self.set_current_file_path(path)

            # P1：读回视图侧格式（加粗/数字格式/合并/批注）——
            # 只写不读会变成"存了却看不到"，用户会以为保存坏了。
            self._load_view_styles_from(
                path, getattr(self, "_active_sheet_name", "") or ""
            )

            sheet_count = len(workbook.sheets) if workbook else 1
            formula_count = workbook.formula_count if workbook else 0
            extra = ""
            if sheet_count > 1:
                extra += f"，含 {sheet_count} 张工作表"
            if formula_count:
                extra += f"，保留 {formula_count} 个公式"
            self._set_status(
                (
                    f"已显示前 {len(df)} 行，正在后台加载完整数据…" if lazy
                    else f"已加载：{len(df)} 行 × {len(df.columns)} 列{extra}"
                ),
                0 if lazy else 5000,
            )
            if lazy:
                # 记下阶段 2 的加载器（供 _ensure_full_data 兜底调用），
                # 并立刻启动后台补全。
                self.model._full_loader = self._make_full_loader(path)
                self._start_phase2_full_load(path)
        except Exception as e:
            QMessageBox.warning(self, "导入失败", str(e))

    def _should_lazy_load(self, path) -> bool:
        """
        是否走两阶段载入（R1）。

        只对**大 xlsx**启用：
          · CSV 用 `pd.read_csv` 本来就快，且块读取路径不同，不在本次范围；
          · 小文件一次性读完毫无问题，改走两阶段只会增加复杂度与行为差异。
        """
        try:
            ext = os.path.splitext(path)[1].lower()
            if ext not in ('.xlsx', '.xlsm'):
                return False
            return os.path.getsize(path) > self.LAZY_THRESHOLD_BYTES
        except OSError:
            return False

    def _make_full_loader(self, path):
        """
        阶段 2 的**同步**加载器（供 `_ensure_full_data` 在用户发起写操作时兜底调用）。
        后台补全用的是 `_start_phase2_full_load` 里的同类逻辑。
        """
        def load_full():
            from beeoffice.plugins.beesheet_workbook import read_workbook

            workbook = read_workbook(path, max_rows=200001)
            if workbook.sheets:
                self._workbook = workbook
                self._load_full_workbook = workbook
                return workbook.sheets[0].df
            return None

        return load_full

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
        # R1 安全门：排序会重排整表，必须在数据完整时做
        if not self._ensure_full_data("排序"):
            return
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

    def _on_chunk_ready(self, ci, chunk_df):
        """
        主线程：把工作线程准备好的分块合并进模型。

        优化规划 §2.4：`ChunkLoader` 在工作线程里只准备数据，模型的写入
        必须回到主线程做——否则会与用户正在进行的单元格编辑竞争，
        用户的修改可能被整体覆盖。
        """
        applied = self.model.apply_chunk(ci, chunk_df)
        if applied:
            self.model.layoutChanged.emit()
        # '整张表加载完毕' 的判定放在主线程（原先由工作线程读 loading_progress）
        if not self.model.is_streaming:
            self._on_all_loaded()

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
        if values:
            self.status_label.setText(
                f"计数:{len(values)} | 求和:{sum(values):,.2f} | "
                f"平均:{sum(values)/len(values):,.2f} | "
                f"空值:{empty}"
            )
        else:
            self.status_label.setText(
                f"选中:{len(indexes)} | 空值:{empty}"
            )

    def _set_status(self, msg, timeout=0):
        """
        在状态标签上显示消息
        :param msg: 消息文本
        :param timeout: 超时自动清空（毫秒），0 表示不自动清空
        """
        self.status_label.setText(msg)
        if timeout > 0:
            # ⚠️ 不能用 `QTimer.singleShot(timeout, lambda: ...)`：
            # 回调会**脱离控件生命周期**，控件先被销毁时定时器仍会触发 →
            # `RuntimeError: Internal C++ object (QLabel) already deleted`
            # （门禁 `sheet-lazy-safety` 在删除标签后当场抓到）。
            # 改成**控件自己持有**的单发定时器：控件销毁时定时器一并销毁，
            # 回调不可能再碰已删除的对象（与 `app.py` 里的状态栏同一套做法）。
            timer = getattr(self, "_status_clear_timer", None)
            if timer is None:
                timer = QTimer(self)
                timer.setSingleShot(True)
                timer.timeout.connect(self._clear_status_label)
                self._status_clear_timer = timer
            timer.stop()
            timer.start(timeout)

    def _clear_status_label(self):
        """清空状态栏（由自持有定时器调用；控件已销毁时静默忽略）。"""
        try:
            self.status_label.setText("")
        except RuntimeError:      # 控件已销毁 —— 不该发生，兜一层不报错
            pass

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
                # P1：记下作者（来自设置里的用户名），保存时写进文件。
                # 没有用户名就留空 —— 保存时会保住文件里原有的作者，
                # 绝不硬编码一个假名字把原作者覆盖掉。
                self._comment_authors[ck] = self._comment_author_name()
            elif ck in self._cell_comments:
                del self._cell_comments[ck]
                self._comment_authors.pop(ck, None)
            self.model.dataChanged.emit(idx, idx)

    def _comment_author_name(self) -> str:
        """批注作者名（设置里的用户名；没设就空着）。"""
        try:
            from beeoffice.settings import AppSettings

            name = getattr(AppSettings(), "user_name", "") or ""
        except Exception:  # noqa: BLE001
            name = ""
        return str(name).strip()

    # ==================== 自动保存 ====================
    def _backup_dir(self):
        """
        本次表格会话的备份目录（优化规划 §1.8）。

        原实现写在 ~/.beeoffice_backups/：完整表格内容（可能是工资表、客户名单）
        以明文 JSON 长期驻留用户主目录，跨文档共享，关闭文档与程序都不清理。
        现在改为应用数据目录下的**会话**子目录，并在关闭文档时删除。
        """
        if getattr(self, "_backup_session_dir", None) is None:
            base = get_app_data_dir() / "sheet_backups"
            try:
                base.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logging.error(f"创建备份目录失败: {e}")
            self._backup_session_dir = base / uuid.uuid4().hex[:8]
        return self._backup_session_dir

    def _auto_save(self):
        """自动保存（每 5 分钟，写入应用数据目录下的会话备份目录）"""
        if not self._dirty:
            return
        try:
            backup_dir = self._backup_dir()
            backup_dir.mkdir(parents=True, exist_ok=True)
            bp = backup_dir / (
                f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            df = self._trim_empty_tail(self.model.df.copy())
            payload = df.to_json(orient='split', force_ascii=False)

            # 原子写。失败必须让用户看见——原实现是 `except Exception: pass`，
            # 备份失败完全静默，用户会一直以为有备份，实际什么都没有。
            if not atomic_write_text(bp, payload):
                self._set_status("⚠ 自动备份失败（详见日志）", 5000)
                return

            self._dirty = False
            # 只保留最近 10 个备份
            for old in sorted(backup_dir.glob("backup_*.json"))[:-10]:
                try:
                    old.unlink()
                except Exception:
                    pass
        except Exception as e:
            logging.error(f"自动备份失败: {e}")
            try:
                self._set_status("⚠ 自动备份失败（详见日志）", 5000)
            except Exception:
                pass

    def _cleanup_backups(self):
        """删除本次会话的备份目录（关闭文档时调用）。"""
        d = getattr(self, "_backup_session_dir", None)
        if d is None:
            return
        try:
            import shutil
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
            logging.info(f"已清理表格自动备份目录: {d}")
        except Exception as e:
            logging.error(f"清理备份目录失败: {e}")
        finally:
            self._backup_session_dir = None

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

        # 优化规划 §1.8：删除本次会话的自动备份
        # （原实现把表格明文长期留在 ~/.beeoffice_backups/，关文档也不清理）
        self._cleanup_backups()

        event.accept()