# beeoffice/plugins/beesheet_commands.py
"""
蜜算撤销/重做命令类
每个命令都实现 execute(model) 和 undo(model) 两个方法
"""


class DataFrameOpCommand:
    """
    **结构性操作**命令（插入/删除行列）：保存操作前后的整表状态，可撤销。

    为什么用"整表快照"而不是"按参数重放"：
    插入/删除行列会牵动**行号、公式引用、批注/格式的行列映射**，
    按参数重放在复杂边界（合并区、公式引用）上很容易漏掉分支；
    而这类操作是**用户手动触发的少数动作**，快照换来的确定性更值。
    代价是大表上会短暂多占一份内存 —— 这是刻意的取舍，写在这里备查。

    ⚠️ 修的是审计报告 §2.11：插入/删除行列原先**只改 `_loaded_df`**
    （不压撤销栈 → Ctrl+Z 无效；也不过 `_ensure_full_data` 安全门 →
    流式大表会被分块回填覆盖；`_full_df` 与 `_loaded_df` 从此分叉）。
    """

    def __init__(self, before, after, label: str = ""):
        self.before = before
        self.after = after
        self.label = label

    # ---- 内部：把一份快照装回模型（两套数据源一起同步）----
    @staticmethod
    def _apply_snapshot(model, frame):
        model._loaded_df = frame
        # `_full_df` 存在时必须一起更新，否则后台分块回填会用旧表覆盖本次修改
        if getattr(model, "_full_df", None) is not None:
            model._full_df = frame
        model._total_rows = len(frame)
        if hasattr(model, "_total_cols"):
            model._total_cols = len(frame.columns)
        model.layoutChanged.emit()

    def execute(self, m):
        self._apply_snapshot(m, self.after)

    def undo(self, m):
        self._apply_snapshot(m, self.before)


class EditCellCommand:
    """单元格编辑命令"""

    def __init__(self, r, c, old, new):
        """
        :param r: 行索引（0 基）
        :param c: 列索引（0 基）
        :param old: 原值
        :param new: 新值
        """
        self.r = r
        self.c = c
        self.old = old
        self.new = new

    def execute(self, m):
        """执行：设置新值"""
        if self.r < len(m._loaded_df):
            m._loaded_df.iloc[self.r, self.c] = self.new
            m.dataChanged.emit(
                m.index(self.r, self.c),
                m.index(self.r, self.c)
            )

    def undo(self, m):
        """撤销：恢复旧值"""
        if self.r < len(m._loaded_df):
            m._loaded_df.iloc[self.r, self.c] = self.old
            m.dataChanged.emit(
                m.index(self.r, self.c),
                m.index(self.r, self.c)
            )


class SortCommand:
    """排序命令"""

    def __init__(self, old, new):
        """
        :param old: 排序前的 DataFrame（已 copy）
        :param new: 排序后的 DataFrame（已 copy）
        """
        self.old = old.copy()
        self.new = new.copy()

    def execute(self, m):
        """执行：应用排序后的数据"""
        m._loaded_df = self.new.copy()
        m.layoutChanged.emit()

    def undo(self, m):
        """撤销：恢复排序前的数据"""
        m._loaded_df = self.old.copy()
        m.layoutChanged.emit()


class TrimCommand:
    """列数据清理命令（去空格、转数字等）"""

    def __init__(self, col, old):
        """
        :param col: 列索引（0 基）
        :param old: 清理前的 Series（已 copy）
        """
        self.col = col
        self.old = old

    def execute(self, m):
        """执行：对列数据做 strip 处理"""
        cn = m._loaded_df.columns[self.col]
        m._loaded_df[cn] = m._loaded_df[cn].astype(str).str.strip()
        m.dataChanged.emit(
            m.index(0, self.col),
            m.index(len(m._loaded_df) - 1, self.col)
        )

    def undo(self, m):
        """撤销：恢复清理前的列数据"""
        cn = m._loaded_df.columns[self.col]
        m._loaded_df[cn] = self.old
        m.dataChanged.emit(
            m.index(0, self.col),
            m.index(len(m._loaded_df) - 1, self.col)
        )