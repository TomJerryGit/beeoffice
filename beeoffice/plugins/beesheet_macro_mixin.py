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

            count = len(RECORDER)
            if count == 0:
                self._set_status(
                    tr("sheet.macro.empty", "没有可播放的宏，请先录制"), 4000
                )
                return

            applied = RECORDER.play(model)
            self._set_status(
                tr("sheet.macro.played", "宏已播放：{n} 个动作").format(
                    n=applied
                ), 4000
            )
        except Exception as e:
            logging.error(f"播放宏失败: {e}")
            self._set_status(
                tr("sheet.macro.play_failed", "播放宏失败"), 3000
            )
