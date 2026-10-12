# beeoffice/plugins/heading_numbering.py
"""
标题编号（优化规划 §3.3 消重）

原先这段"多级计数器"算法在**两处逐字重复**：

  - `beewrite_crossref.CrossRefManager.scan_headings()`
  - `beewrite_outline.OutlinePanel._scan_headings()`（Qt 分支）

两处都是同一套：`counters = [0] * 6` → `counters[level-1] += 1` →
把下级计数器清零 → `".".join(str(counters[i]) for i in range(level)
if counters[i] > 0)`。

本模块是**唯一实现**，且不依赖 Qt，因此可以用纯函数测试覆盖边界情况
（跳级、连续同级、超过 6 级）。

编号规则（与抽取前的两处实现保持一致）：

| 层级序列 | 编号 |
|---|---|
| 1 | `1` |
| 1, 2 | `1`, `1.1` |
| 1, 2, 3 | `1`, `1.1`, `1.1.1` |
| 1, 1 | `1`, `2`（同级递增，下级清零） |
| 1, 2, 1 | `1`, `1.1`, `2`（回到 1 级后 2 级计数清零） |
| 3（跳级） | `1`（只显示有计数的层级，与抽取前一致） |
"""

#: 支持的最大标题层级（与原实现的 6 个计数器一致）
MAX_HEADING_LEVEL = 6


class HeadingNumberer:
    """按出现顺序为标题层级编号。"""

    def __init__(self, max_level: int = MAX_HEADING_LEVEL):
        self.max_level = max_level
        self._counters = [0] * max_level

    def next_number(self, level: int) -> str:
        """
        传入一个标题层级（1..max_level），返回它的编号字符串。

        非法层级（<1 或 >max_level）不计数并返回空串 —— 调用方据此跳过。

        :param level: 标题层级
        :return: 形如 "1" / "1.1" / "1.1.1" 的编号
        """
        if not isinstance(level, int) or level < 1 or level > self.max_level:
            return ""
        self._counters[level - 1] += 1
        # 下级计数器清零（出现新的上级标题后，其下级重新从 1 开始）
        for i in range(level, self.max_level):
            self._counters[i] = 0
        return ".".join(
            str(self._counters[i])
            for i in range(level)
            if self._counters[i] > 0
        )

    def reset(self) -> None:
        """重置全部计数器（换文档 / 重新扫描时调用）。"""
        self._counters = [0] * self.max_level


def numbers_for_levels(levels) -> list:
    """
    便捷纯函数：给一串层级，返回对应的编号列表。

    >>> numbers_for_levels([1, 2, 2, 1])
    ['1', '1.1', '1.2', '2']

    :param levels: 可迭代的层级（int）
    :return: 编号字符串列表（非法层级处为空串）
    """
    numberer = HeadingNumberer()
    return [numberer.next_number(lv) for lv in levels]
