# -*- coding: utf-8 -*-
"""
蜜算宏：视图侧入口（P1-29）

菜单里的"录制宏 / 播放宏"原本调用 `_toggle_macro_recording` 与
`_play_macro`，但这两个方法在视图上并不存在，调用方用 hasattr
判断后静默跳过——用户点了完全没反应。

本混入补齐这两个入口：
    · 录制：开始后记录单元格赋值，再次点击停止并报告动作数
    · 回放：把录制的动作依次写回当前表
    · 有清晰的状态栏提示，避免"点了没反应"
"""
import logging

from beeoffice.i18n import tr


class MacroMixin:
    """给 BeeSheetView 提供宏录制 / 回放入口。"""

    # ---------- 录制 ----------
    def _toggle_macro_recording(self):
        from beeoffice.plugins.macro_recorder import RECORDER

        try:
            if RECORDER.recording:
                count = RECORDER.stop()
                self._set_status(
                    tr("sheet.macro.stopped", "宏录制结束：共 {n} 个动作"
                       ).format(n=count), 4000
                )
            else:
                RECORDER.start()
                self._set_status(
                    tr("sheet.macro.started",
                       "宏录制中……再次点击「录制宏」结束"), 5000
                )
        except Exception as e:
            logging.error(f"切换宏录制失败: {e}")
            self._set_status(tr("sheet.macro.error", "宏录制失败"), 3000)

    # ---------- 回放 ----------
    def _play_macro(self):
        from beeoffice.plugins.macro_recorder import RECORDER

        try:
            if RECORDER.recording:
                self._set_status(
                    tr("sheet.macro.playing_while_recording",
                       "请先结束录制再播放宏"), 4000
                )
                return

            model = getattr(self, "model", None)
            if model is None:
                self._set_status(tr("sheet.macro.error", "宏录制失败"), 3000)
                return

            counts = RECORDER.counts()
            if len(RECORDER) == 0:
                self._set_status(
                    tr("sheet.macro.empty", "没有可播放的宏，请先录制"), 4000
                )
                return

            applied = RECORDER.play(
                model,
                switch_sheet=self._macro_switch_sheet,
                apply_format=self._macro_apply_format,
            )
            self._set_status(
                tr("sheet.macro.played_detail",
                   "宏已播放：{n} 个动作（赋值 {s} / 格式 {f} / 切表 {t}）"
                   ).format(
                       n=applied, s=counts.get("set", 0),
                       f=counts.get("format", 0), t=counts.get("sheet", 0),
                   ), 5000
            )
        except Exception as e:
            logging.error(f"播放宏失败: {e}")
            self._set_status(
                tr("sheet.macro.play_failed", "播放宏失败"), 3000
            )

    # ---------- 回放回调（阶段三 #8） ----------
    def _macro_switch_sheet(self, name: str) -> bool:
        """按标签页标题切换到指定工作表；找不到返回 False（不抛异常）。"""
        try:
            finder = getattr(self, "_find_main_window", None)
            parent = finder() if finder else None
            tm = getattr(parent, "tab_manager", None)
            if tm is None:
                return False
            for i in range(tm.count()):
                widget = tm.widget(i)
                if not (hasattr(widget, "model") and hasattr(widget.model, "df")):
                    continue
                title = (
                    tm.tabText(i)
                    .replace("📊 ", "").replace("● ", "").strip()
                )
                if title == name:
                    tm.setCurrentIndex(i)
                    return True
            logging.warning(f"宏回放：找不到工作表 {name}")
            return False
        except Exception as e:
            logging.error(f"宏回放切换工作表失败: {e}")
            return False

    def _macro_apply_format(self, row: int, col: int, key: str, value):
        """把一条格式动作写回当前工作表。"""
        try:
            k = (row, col)
            if k not in self._cell_formats:
                self._cell_formats[k] = {}
            self._cell_formats[k][key] = value
            idx = self.model.index(row, col)
            self.model.dataChanged.emit(idx, idx)
        except Exception as e:
            logging.error(f"宏回放应用格式失败 ({row},{col},{key}): {e}")
