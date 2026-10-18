# beeoffice/plugins/beesheet_model.py
r"""
蜜算数据模型：支持分块加载、条件格式、样式渲染

v5.0.1 修复（P1-1）：
  - _init_empty 默认列名改用 col_index_to_name，
    修复原实现 chr(65 + i) 在 cols > 26 时产生 [ \ ] 等乱码
  - 新增顶部导入：from beeoffice.plugins.beesheet_utils import col_index_to_name
"""
import pandas as pd
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PySide6.QtGui import QColor, QFont

from beeoffice.plugins.beesheet_utils import col_index_to_name


class SheetDataModel(QAbstractTableModel):
    """表格数据模型"""

    CHUNK_SIZE = 5000
    PRELOAD_MARGIN = 2000
    DEFAULT_ROWS = 1000
    MIN_ROWS = 100

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
        self._init_empty()

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
        # 索引统一成绝对行号：模型按 .iloc 取值，索引必须等于行位置
        self._loaded_df.index = range(len(self._loaded_df))
        self._loaded_chunks.add(0)
        self._is_streaming = fc < self._total_rows
        self.layoutChanged.emit()

    def load_chunk(self, ci):
        """
        加载指定索引的分块。

        修复（P1-16）：模型以"已加载前缀"识别占位行
        （`data()` 里 `r >= len(_loaded_df)` 返回 "⏳"），
        所以已加载数据必须是**连续前缀**。

        原实现只把自己这一块追加到末尾，并用
        `pd.concat(..., ignore_index=False)` 保留原索引：
        跳着加载（先看第 3 块再回第 1 块）时，第 1 块被追加到末尾，
        位置与绝对行号错位 —— 界面上表现为"这一行显示了别的行的数据"。

        现在：从最小的缺失块开始，**把到 ci 为止缺的块一次性补齐**，
        并用 `ignore_index=True` 重建 0..n-1 的位置索引，
        保证 `iloc[r]` 就是第 r 行。
        """
        if ci in self._loaded_chunks or self._full_df is None:
            return False

        loaded_any = False
        for k in range(ci + 1):
            if k in self._loaded_chunks:
                continue
            s = k * self.CHUNK_SIZE
            e = min(s + self.CHUNK_SIZE, self._total_rows)
            if s >= self._total_rows:
                break
            cd = self._full_df.iloc[s:e].copy()
            self._loaded_df = pd.concat(
                [self._loaded_df, cd], ignore_index=True
            )
            self._loaded_chunks.add(k)
            loaded_any = True

        if loaded_any:
            self._is_streaming = (
                len(self._loaded_df) < self._total_rows
            )
        return loaded_any

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
        if not index.isValid():
            return None
        r, c = index.row(), index.column()
        # 超出已加载范围
        if r >= len(self._loaded_df):
            if role == Qt.DisplayRole:
                return "⏳"
            return None

        val = self._loaded_df.iloc[r, c]

        # === 显示值 ===
        if role == Qt.DisplayRole:
            if pd.isna(val) or val == '':
                return ""
            # 图标集
            if self._conditional_formats_ref and c in self._conditional_formats_ref:
                cond_fmt = self._conditional_formats_ref[c]
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
            if self._cell_formats_ref:
                fmt = self._cell_formats_ref.get((r, c))
                if fmt:
                    return self._format_display_value(val, fmt)
            return str(val)

        # === 字体 ===
        if role == Qt.FontRole:
            if self._cell_formats_ref:
                fmt = self._cell_formats_ref.get((r, c))
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

        # === 对齐 ===
        if role == Qt.TextAlignmentRole:
            if self._cell_formats_ref:
                fmt = self._cell_formats_ref.get((r, c))
                if fmt and fmt.get('align'):
                    align_map = {
                        'left': Qt.AlignLeft | Qt.AlignVCenter,
                        'center': Qt.AlignCenter,
                        'right': Qt.AlignRight | Qt.AlignVCenter,
                    }
                    if fmt['align'] in align_map:
                        return align_map[fmt['align']]
            if isinstance(val, (int, float)) and not pd.isna(val):
                return Qt.AlignRight | Qt.AlignVCenter
            return Qt.AlignLeft | Qt.AlignVCenter

        # === 背景色 ===
        if role == Qt.BackgroundRole:
            return self._get_cond_bg(r, c)

        # === 悬浮提示 ===
        if role == Qt.ToolTipRole:
            if self._comments_ref and (r, c) in self._comments_ref:
                return f"💬 {self._comments_ref[(r, c)]}"
            s = str(val) if not pd.isna(val) else ""
            if s.startswith('#ERROR') or s.startswith('#N/A'):
                return s
            if self._formulas_ref and (r, c) in self._formulas_ref:
                return f"{self._formulas_ref[(r, c)]}"
            return s if len(s) > 50 else None

        return None

    def _get_cond_bg(self, r, c):
        """根据各种状态返回单元格背景色"""
        # 1. 错误单元格
        if r < len(self._loaded_df):
            try:
                v = str(self._loaded_df.iloc[r, c])
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
        if not self._conditional_formats_ref or \
           c not in self._conditional_formats_ref:
            return None
        if r >= len(self._loaded_df):
            return None
        fmt = self._conditional_formats_ref[c]
        try:
            if fmt.get("type") == "data_bars":
                val = float(self._loaded_df.iloc[r, c])
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
                val = float(self._loaded_df.iloc[r, c])
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
        r = index.row()
        if r >= len(self._loaded_df):
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable
        return (Qt.ItemIsEnabled | Qt.ItemIsSelectable |
                Qt.ItemIsEditable)

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