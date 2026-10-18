# -*- coding: utf-8 -*-
"""
蜜算宏：录制用户操作并回放（P1-29 → 阶段三 #8 扩展）

v1（前一版）只录制单元格赋值。本版扩成三类动作：

    ("set",    row, col, value)              单元格赋值
    ("format", row, col, key, value)         单元格格式（加粗/对齐/数字格式…）
    ("sheet",  tab_name)                     切换到另一张表（蜜算的多表 = 多个标签页）

设计要点：
    · 动作是**有序**的：先记录 sheet 切换，后续 set/format 就作用在那张表上
    · 回放通过回调注入，录制器本身不依赖 Qt 控件（便于单测）
    · 回放期间不录制（否则回放会污染宏本身）
    · 向后兼容：v1 录制的是 `("set", r, c, v)` 四元组，格式不变，旧宏可直接播放
"""
import logging

try:
    from PySide6.QtCore import Qt
except Exception:  # pragma: no cover - 纯逻辑测试环境
    Qt = None


class MacroRecorder:
    """记录一连串动作，并按顺序回放。"""

    def __init__(self):
        self._actions = []
        self._recording = False
        self._playing = False

    # ---------- 状态 ----------
    @property
    def recording(self) -> bool:
        return self._recording

    @property
    def playing(self) -> bool:
        return self._playing

    @property
    def actions(self):
        return list(self._actions)

    def __len__(self):
        return len(self._actions)

    def counts(self) -> dict:
        """按类型统计动作数，用于回放后给用户一个可读反馈。"""
        result = {"set": 0, "format": 0, "sheet": 0}
        for action in self._actions:
            kind = action[0]
            result[kind] = result.get(kind, 0) + 1
        return result

    # ---------- 录制 ----------
    def start(self):
        self._actions = []
        self._recording = True

    def stop(self) -> int:
        self._recording = False
        return len(self._actions)

    def clear(self):
        self._actions = []

    def record_set(self, row: int, col: int, value):
        """记录一次单元格赋值。连续改同一格只保留最后一次。"""
        if not self._recording or self._playing:
            return
        last = self._actions[-1] if self._actions else None
        if (last is not None and last[0] == "set"
                and last[1] == row and last[2] == col):
            self._actions[-1] = ("set", row, col, value)
        else:
            self._actions.append(("set", row, col, value))

    def record_format(self, row: int, col: int, key: str, value):
        """记录一次单元格格式变更（加粗、对齐、数字格式等）。"""
        if not self._recording or self._playing:
            return
        self._actions.append(("format", row, col, key, value))

    def record_sheet(self, name: str):
        """记录一次工作表切换（蜜算的多表以标签页表示）。"""
        if not self._recording or self._playing or not name:
            return
        last = self._actions[-1] if self._actions else None
        if last is not None and last[0] == "sheet" and last[1] == name:
            return          # 连续切到同一张表没有意义
        self._actions.append(("sheet", name))

    # ---------- 回放 ----------
    def play(self, model, switch_sheet=None, apply_format=None) -> int:
        """
        依次回放动作，返回实际执行的动作数。

        :param model: QAbstractItemModel（提供 index / setData）
        :param switch_sheet: 可选回调 `(name) -> bool`，处理 sheet 动作
        :param apply_format: 可选回调 `(row, col, key, value)`，处理 format 动作

        缺失回调时对应动作会被**跳过并记日志**，而不是抛异常中断整段回放。
        """
        if not self._actions:
            return 0
        if Qt is None:
            logging.error("回放宏失败：Qt 不可用")
            return 0

        self._playing = True
        applied = 0
        try:
            for action in self._actions:
                kind = action[0]
                if kind == "set":
                    _, r, c, value = action
                    model.setData(
                        model.index(r, c), value, Qt.ItemDataRole.EditRole
                    )
                    applied += 1
                elif kind == "format":
                    _, r, c, key, value = action
                    if apply_format is None:
                        logging.warning("宏包含格式动作，但未提供处理回调，已跳过")
                        continue
                    apply_format(r, c, key, value)
                    applied += 1
                elif kind == "sheet":
                    _, name = action
                    if switch_sheet is None:
                        logging.warning("宏包含切换工作表，但未提供处理回调，已跳过")
                        continue
                    if switch_sheet(name):
                        applied += 1
                    else:
                        logging.warning(f"回放到不存在的工作表：{name}")
                else:
                    logging.warning(f"未知宏动作：{kind}")
        finally:
            self._playing = False
        return applied


# 视图侧共用的单例
RECORDER = MacroRecorder()
