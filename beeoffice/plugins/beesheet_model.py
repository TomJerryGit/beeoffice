# beeoffice/plugins/beesheet_model.py
r"""
蜜算数据模型：支持分块加载、条件格式、样式渲染

v5.0.1 修复（P1-1）：
  - _init_empty 默认列名改用 col_index_to_name，
    修复原实现 chr(65 + i) 在 cols > 26 时产生 [ \ ] 等乱码
  - 新增顶部导入：from beeoffice.plugins.beesheet_utils import col_index_to_name
"""
import numpy as np
import pandas as pd
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PySide6.QtGui import QColor, QFont

from beeoffice.plugins.beesheet_utils import col_index_to_name

# ==================== P0-B：热路径常量 ====================
# `data()` / `flags()` 一帧会被调用数千次（实测 2000×20 时每帧 1512 次 data +
# 216 次 flags），所以这些每帧重复求值的东西一律预先算好。
# 注意：不改行为，只去掉重复计算。
_FLAGS_READONLY = Qt.ItemIsEnabled | Qt.ItemIsSelectable
_FLAGS_EDITABLE = Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

_ROLE_DISPLAY = Qt.ItemDataRole.DisplayRole
_ROLE_FONT = Qt.ItemDataRole.FontRole
_ROLE_BACKGROUND = Qt.ItemDataRole.BackgroundRole
_ROLE_ALIGNMENT = Qt.ItemDataRole.TextAlignmentRole
_ROLE_TOOLTIP = Qt.ItemDataRole.ToolTipRole
_ALIGN_RIGHT = Qt.AlignRight | Qt.AlignVCenter
_ALIGN_LEFT = Qt.AlignLeft | Qt.AlignVCenter
_ALIGN_MAP = {
    'left': Qt.AlignLeft | Qt.AlignVCenter,
    'center': Qt.AlignCenter,
    'right': Qt.AlignRight | Qt.AlignVCenter,
}

#: 判断"是不是数字"要用它，**不能只用 (int, float)**
#: —— 走 numpy 视图后取到的是 `np.int64`/`np.float64`，
#: 而 NumPy 标量**不是** Python int/float，只写 (int, float) 会让数字不再右对齐。
_NUMERIC_TYPES = (int, float, np.integer, np.floating)


class SheetDataModel(QAbstractTableModel):
    """表格数据模型"""

    CHUNK_SIZE = 5000
    PRELOAD_MARGIN = 2000
    DEFAULT_ROWS = 1000

    def __init__(self, parent=None):
        super().__init__(parent)
        self._full_df = None
        self._loaded_df = None
        self._loaded_chunks = set()
        self._total_rows = 0
        self._total_cols = 0
        self._is_streaming = False
        self._real_rows = 0
        self._conditional_formats_ref = {}
        self._highlight_refs = set()
        self._audit_cells_ref = set()
        self._comments_ref = {}
        self._formulas_ref = {}
        self._cell_formats_ref = {}
        self._validations_ref = {}
        self._named_ranges_ref = {}
        self._table_style_ref = None
        self._get_sheet_data = None
        self._get_sheet_names = None
        # P0-B：`_loaded_df` 的 numpy **按列视图**，供 data() 热路径快速取值。
        # 见 `_column_arrays()` —— 按列是为了保证"就地修改也可见"。
        self._mirror_df = None
        self._cols = None
        self._init_empty()

    # ==================== 快速取值（P0-B 性能） ====================
    def _refresh_values(self):
        """让取值镜像失效（下次取值时按需重建）。**每次 `_loaded_df` 变化后调用。**"""
        self._mirror_df = None
        self._cols = None

    def _column_arrays(self):
        """
        取"按列"的 numpy 视图数组。

        **为什么按列而不是整帧**：`df.to_numpy()` 只在**单 dtype** 时是视图；
        混合 dtype（例如文本列 + 数值列，导入的表格很常见）时会**复制**一份 ——
        而 `_loaded_df` 在代码里有约 40 处是**就地修改**（`iloc[...] = `、
        `.loc[...] = `、`.insert` 等），用副本会**显示陈旧值**。
        每一列必然是单一 dtype，`Series.to_numpy()` 就是该列块的**视图**，
        因此任何就地标量写都会同步可见 —— 这是"快"与"对"同时成立的关键。
        （实测：单 dtype 帧的整帧 to_numpy 是视图；混合 dtype 帧不是。）

        失效判定很便宜：对象被替换（`_loaded_df = ...`）或列数变了就重建；
        纯粹的值修改**不需要**重建（视图本来就会同步）。
        """
        df = self._loaded_df
        if df is None:
            return None
        cols = self._cols
        if cols is not None and self._mirror_df is df \
                and len(cols) == len(df.columns):
            return cols
        try:
            cols = [df.iloc[:, i].to_numpy() for i in range(len(df.columns))]
        except Exception:  # noqa: BLE001
            cols = None
        self._cols = cols
        self._mirror_df = df
        return cols

    def _value_at(self, r, c):
        """取单元格值；优先走 numpy 视图，异常时退回 pandas（行为兜底）。"""
        cols = self._column_arrays()
        if cols is not None:
            try:
                return cols[c][r]
            except (IndexError, TypeError):
                pass
        try:
            return self._loaded_df.iat[r, c]
        except Exception:  # noqa: BLE001
            return None

    # ==================== 初始化 ====================
    def _init_empty(self, rows=None, cols=10):
        """
        初始化空表格

        P1-1：用 col_index_to_name 支持超过 26 列（A..Z, AA..AZ, ...）
        """
        if rows is None:
            rows = self.DEFAULT_ROWS
        self._full_df = pd.DataFrame(
            '',
            index=range(rows),
            columns=[col_index_to_name(i) for i in range(cols)]
        )
        self._loaded_df = self._full_df.copy()
        self._total_rows = rows
        self._total_cols = cols
        self._loaded_chunks = {0}
        self._is_streaming = False
        self._real_rows = 0
        self._refresh_values()

    # ==================== 数据设置 ====================
    def set_full_dataframe(self, df):
        """设置完整数据，并自动补齐空行到默认工作区大小"""
        real_rows = len(df)
        self._real_rows = real_rows

        # 如果真实数据小于工作区，末尾补齐空行
        if real_rows < self.DEFAULT_ROWS:
            empty_count = self.DEFAULT_ROWS - real_rows
            empty_df = pd.DataFrame(
                '',
                index=range(empty_count),
                columns=df.columns
            )
            df = pd.concat([df, empty_df], ignore_index=True)

        self._full_df = df
        self._total_rows = len(df)
        self._total_cols = len(df.columns)
        self._loaded_chunks = set()
        fc = min(self.CHUNK_SIZE, self._total_rows)
        self._loaded_df = df.head(fc).copy()
        self._loaded_chunks.add(0)
        self._is_streaming = fc < self._total_rows
        self._refresh_values()
        self.layoutChanged.emit()

    def build_chunk(self, ci):
        """
        读取并返回第 ci 块数据，**不修改模型**（可在工作线程调用）。

        优化规划 §2.4：`ChunkLoader` 是 QThread，原先在工作线程里直接调用
        `load_chunk()`，也就是在工作线程写 `_loaded_df` / `_loaded_chunks`。
        工作线程改模型有两个后果：
          ① 与主线程的单元格编辑竞争 —— 用户刚输入的值可能被
             `pd.concat` 的结果整体覆盖（丢失更新）；
          ② `_loaded_chunks` 被 `set_full_dataframe` 重新绑定时，
             工作线程持有的是旧集合，已加载的块会被"遗忘"而重复加载。
        因此把"取数据"（后台可做）与"合并进模型"（必须主线程）拆开。

        :return: 该块数据的副本；块不存在或无数据时返回 None
        """
        if self._full_df is None or self._total_rows == 0 or ci < 0:
            return None
        s = ci * self.CHUNK_SIZE
        e = min(s + self.CHUNK_SIZE, self._total_rows)
        if s >= self._total_rows:
            return None
        return self._full_df.iloc[s:e].copy()

    def apply_chunk(self, ci, chunk_df):
        """
        把后台准备好的分块合并进模型。

        **只能在主线程调用**：本方法会写 `_loaded_df` / `_loaded_chunks` /
        `_is_streaming`，这些状态同时被视图和编辑逻辑读取。

        :return: 是否真的合并了（重复块或空数据返回 False）
        """
        if chunk_df is None or ci in self._loaded_chunks:
            return False
        if self._loaded_df is None:
            self._loaded_df = chunk_df
        else:
            merged = pd.concat([self._loaded_df, chunk_df], ignore_index=False)
            self._loaded_df = merged[~merged.index.duplicated(keep='last')]
        self._loaded_chunks.add(ci)
        self._is_streaming = (
            len(self._loaded_chunks) * self.CHUNK_SIZE < self._total_rows
        )
        self._refresh_values()
        return True

    def load_chunk(self, ci):
        """
        同步加载指定索引的分块（build + apply 的组合）。

        保留该接口给不在后台线程里调用分块加载的场景使用；
        后台线程请改用 build_chunk()（并让主线程 apply_chunk()）。
        """
        if ci in self._loaded_chunks:
            return False
        return self.apply_chunk(ci, self.build_chunk(ci))

    def needs_chunks_for_range(self, sr, er):
        """返回指定行范围内需要加载的分块索引集合"""
        needed = set()
        for r in range(sr, er + 1):
            ci = r // self.CHUNK_SIZE
            if ci not in self._loaded_chunks:
                needed.add(ci)
        return needed

    # ==================== 属性 ====================
    @property
    def df(self):
        """当前已加载的 DataFrame"""
        return self._loaded_df if self._loaded_df is not None else self._full_df

    @df.setter
    def df(self, v):
        if len(v) <= self.CHUNK_SIZE:
            self._full_df = v
            self._loaded_df = v.copy()
            self._total_rows = len(v)
            self._total_cols = len(v.columns)
            self._loaded_chunks = {0}
            self._is_streaming = False
            self._refresh_values()
        else:
            self.set_full_dataframe(v)

    @property
    def is_streaming(self):
        """是否处于流式加载状态"""
        return self._is_streaming

    @property
    def loading_progress(self):
        """加载进度（0.0 - 1.0）"""
        if self._total_rows == 0:
            return 1.0
        return min(
            len(self._loaded_chunks) * self.CHUNK_SIZE / self._total_rows,
            1.0
        )

    # ==================== Qt 模型接口 ====================
    def rowCount(self, p=QModelIndex()):
        return self._total_rows

    def columnCount(self, p=QModelIndex()):
        return self._total_cols if self._full_df is not None else 0

    def _format_display_value(self, val, fmt):
        """根据格式显示值"""
        num_format = fmt.get('number_format', '常规')
        decimals = fmt.get('decimals', 2)
        try:
            num = float(val)
        except (TypeError, ValueError):
            return str(val)
        if num_format == '数值':
            return f"{num:,.{decimals}f}"
        elif num_format == '货币':
            return f"¥{num:,.{decimals}f}"
        elif num_format == '百分比':
            return f"{num * 100:.{decimals}f}%"
        elif num_format == '千分位':
            return f"{num:,.{decimals}f}"
        return str(val) if not pd.isna(val) else ""

    def data(self, index, role=Qt.DisplayRole):
        # P0-B：热路径。一帧约 1500 次调用，所以这里刻意做了几件事：
        #   · `len(self._loaded_df)` 只算**一次**（它要走 pandas __len__→RangeIndex
        #     __len__，原先每次调用算 3 遍，实测占本函数约 25%）
        #   · role 用**预绑定常量**比较，不再每次访问枚举
        #   · 先处理 Font/Background 这两个不需要取值的 role，早返回
        if not index.isValid():
            return None
        r = index.row()
        c = index.column()
        loaded_rows = len(self._loaded_df)
        if r >= loaded_rows:
            if role == _ROLE_DISPLAY:
                return "⏳"
            return None

        formats = self._cell_formats_ref

        if role == _ROLE_FONT:
            if formats:
                fmt = formats.get((r, c))
                if fmt:
                    f = QFont()
                    if fmt.get('bold'):
                        f.setBold(True)
                    if fmt.get('italic'):
                        f.setItalic(True)
                    if fmt.get('underline'):
                        f.setUnderline(True)
                    return f
            return None

        if role == _ROLE_BACKGROUND:
            return self._get_cond_bg(r, c, loaded_rows)

        val = self._value_at(r, c)

        # === 显示值 ===
        if role == _ROLE_DISPLAY:
            if pd.isna(val) or val == '':
                return ""
            # 图标集
            cond = self._conditional_formats_ref
            if cond and c in cond:
                cond_fmt = cond[c]
                if cond_fmt.get("type") == "icon_set":
                    try:
                        v = float(val)
                        lo, hi = cond_fmt["min"], cond_fmt["max"]
                        if hi > lo:
                            ratio = (v - lo) / (hi - lo)
                            if ratio < 0.33:
                                icon = "🔴 "
                            elif ratio < 0.66:
                                icon = "🟡 "
                            else:
                                icon = "🟢 "
                            if self._cell_formats_ref:
                                fm = self._cell_formats_ref.get((r, c))
                                if fm:
                                    return icon + self._format_display_value(val, fm)
                            return icon + str(val)
                    except:
                        pass
            # 数字格式
            if formats:
                fmt = formats.get((r, c))
                if fmt:
                    return self._format_display_value(val, fmt)
            return str(val)

        # === 对齐 ===
        if role == _ROLE_ALIGNMENT:
            if formats:
                fmt = formats.get((r, c))
                if fmt and fmt.get('align'):
                    mapped = _ALIGN_MAP.get(fmt['align'])
                    if mapped is not None:
                        return mapped
            if isinstance(val, _NUMERIC_TYPES) and not pd.isna(val):
                return _ALIGN_RIGHT
            return _ALIGN_LEFT

        # === 悬浮提示 ===
        if role == _ROLE_TOOLTIP:
            comments = self._comments_ref
            if comments and (r, c) in comments:
                return f"💬 {comments[(r, c)]}"
            s = str(val) if not pd.isna(val) else ""
            if s.startswith('#ERROR') or s.startswith('#N/A'):
                return s
            formulas = self._formulas_ref
            if formulas and (r, c) in formulas:
                return f"{formulas[(r, c)]}"
            return s if len(s) > 50 else None

        return None

    def _get_cond_bg(self, r, c, loaded_rows=None):
        """根据各种状态返回单元格背景色（P0-B：允许传入已算好的行数）"""
        if loaded_rows is None:
            loaded_rows = len(self._loaded_df)
        # 1. 错误单元格
        if r < loaded_rows:
            try:
                v = str(self._value_at(r, c))
                if v.startswith('#ERROR') or v.startswith('#N/A'):
                    return QColor(255, 205, 210, 200)
            except:
                pass

        # 2. 引用高亮（公式栏正在引用）
        if self._highlight_refs and (r, c) in self._highlight_refs:
            return QColor(33, 150, 243, 80)

        # 3. 公式审计高亮
        if self._audit_cells_ref and (r, c) in self._audit_cells_ref:
            return QColor(255, 152, 0, 100)

        # 4. 表格样式
        if self._table_style_ref:
            style = self._table_style_ref
            if r == 0:
                return style.get("header_bg")
            elif style.get("stripe") and (r % 2 == 1):
                return style.get("stripe_bg")

        # 5. 条件格式
        cond = self._conditional_formats_ref
        if not cond or c not in cond:
            return None
        if r >= loaded_rows:
            return None
        fmt = cond[c]
        try:
            if fmt.get("type") == "data_bars":
                val = float(self._value_at(r, c))
                mn, mx = fmt["min"], fmt["max"]
                if mx > mn:
                    ratio = max(0, min(1, (val - mn) / (mx - mn)))
                    return QColor(
                        255,
                        int(255 - ratio * 76),
                        int(255 - ratio * 255),
                        60
                    )
            elif fmt.get("type") == "color_scale":
                val = float(self._value_at(r, c))
                mn, mx = fmt["min"], fmt["max"]
                if mx > mn:
                    ratio = max(0, min(1, (val - mn) / (mx - mn)))
                    if ratio < 0.5:
                        r2 = 244
                        g2 = int(67 + ratio * 2 * (200 - 67))
                        b2 = 54
                    else:
                        r2 = int(255 - (ratio - 0.5) * 2 * (255 - 76))
                        g2 = int(200 + (ratio - 0.5) * 2 * (175 - 200))
                        b2 = int(54 + (ratio - 0.5) * 2 * (80 - 54))
                    return QColor(r2, g2, b2, 180)
        except:
            pass
        return None

    def setData(self, index, value, role=Qt.EditRole):
        """设置单元格数据"""
        if not index.isValid():
            return False
        r, c = index.row(), index.column()
        if r >= len(self._loaded_df):
            return False
        self._loaded_df.iloc[r, c] = value
        if self._full_df is not None:
            self._full_df.iloc[r, c] = value
        if r >= self._real_rows:
            self._real_rows = r + 1
        self.dataChanged.emit(index, index)
        return True

    def flags(self, index):
        """单元格标志"""
        # P0-B：这两个标志值是**常量**，原先每次调用都用 Python 的枚举 `|`
        # 现算（实测 1080 次/帧，每次约 32µs，其中 3240 次 enum.__or__）。
        # 预先算好直接返回。
        if index.row() >= len(self._loaded_df):
            return _FLAGS_READONLY
        return _FLAGS_EDITABLE

    def headerData(self, s, o, role):
        """表头数据"""
        if role == Qt.DisplayRole:
            if o == Qt.Horizontal:
                if self._full_df is not None and \
                   s < len(self._full_df.columns):
                    return self._full_df.columns[s]
                return str(s)
            else:
                return str(s + 1)
        return None

    # ==================== 工具方法 ====================
    def get_value(self, r, c):
        """获取单元格值（优先从已加载数据取，其次从完整数据取）"""
        if r < len(self._loaded_df):
            return self._loaded_df.iloc[r, c]
        if self._full_df is not None and r < len(self._full_df):
            return self._full_df.iloc[r, c]
        return ""