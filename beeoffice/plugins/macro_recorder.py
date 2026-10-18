# -*- coding: utf-8 -*-
"""
蜜算宏：录制单元格编辑并回放（P1-29）

背景：
    菜单里有"录制宏 / 播放宏"，但视图侧 `_toggle_macro_recording`、
    `_play_macro` 两个方法根本不存在，点击后走 hasattr 判断直接跳过——
    用户看到的是"点了没反应"。

范围（v1，克制而真实）：
    只录制**单元格赋值**这一类动作，回放到当前表。
    不做按键级录制、不做脚本语言、不跨表——那些属于后续版本。

设计要点：
    · 连续编辑同一单元格只保留最后一次（拖拽填充不会产生上百条无效动作）
    · 回放期间不重复录制（否则回放会污染宏本身）
    · 单例由视图共用，不依赖全局可变状态散落各处
"""
import logging

try:
    from PySide6.QtCore import Qt
except Exception:  # pragma: no cover - 仅在无 Qt 环境（纯逻辑测试）触发
    Qt = None


class MacroRecorder:
    """记录一串 set(row, col, value)，并按顺序回放。"""

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
        """记录一次单元格赋值。非录制态或回放态直接忽略。"""
        if not self._recording or self._playing:
            return
        last = self._actions[-1] if self._actions else None
        if last is not None and last[0] == "set" and last[1] == row and last[2] == col:
            self._actions[-1] = ("set", row, col, value)
        else:
            self._actions.append(("set", row, col, value))

    # ---------- 回放 ----------
    def play(self, model) -> int:
        """
        把录制的动作依次应用到 model 上，返回实际执行的动作数。

        model 需是 QAbstractItemModel（提供 index / setData）。
        """
        if not self._actions:
            return 0
        if Qt is None:
            logging.error("回放宏失败：Qt 不可用")
            return 0

        self._playing = True
        applied = 0
        try:
            for kind, r, c, value in self._actions:
                if kind != "set":
                    continue
                model.setData(model.index(r, c), value, Qt.ItemDataRole.EditRole)
                applied += 1
        finally:
            self._playing = False
        return applied


# 视图侧共用的单例
RECORDER = MacroRecorder()
