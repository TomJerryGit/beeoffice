# beeoffice/plugins/beesheet_commands.py
"""
蜜算撤销/重做命令类
每个命令都实现 execute(model) 和 undo(model) 两个方法
"""


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