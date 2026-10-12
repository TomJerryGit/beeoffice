# beeoffice/plugins/beeshow_play_mixin.py
"""
蜜演全屏播放 / 演讲者模式 / 排练计时 Mixin

职责：
  - _start_play            : 全屏播放（P0-2 用 _PlayWindow 转发键盘）
  - _stop_play             : 停止播放（v5.0.5：getattr 判空 + 显式置 None）
  - _show_play_slide       : 渲染当前页到播放窗口（v5.0.5：None 保护）
  - _update_timer          : 更新计时标签
  - _start_presenter_mode  : 演讲者视图（P1-12：无备注也显示引导）
  - _update_presenter_view : 刷新演讲者视图（P1-12：None 保护）
  - _on_progress_changed   : 进度条变化
  - keyPressEvent          : 全屏快捷键（翻页 / ESC / F / B / L / P / R）
  - toggle_rehearsal / start_rehearsal / stop_rehearsal / reset_rehearsal
  - _update_rehearsal_time

v5.1 增量汇总：
  - 任务 2.1：_show_play_slide 拼入版式 CSS
  - 任务 5.1：_show_play_slide 注入动态数字 JS
  - 任务 4.3：_show_play_slide 末尾广播翻页
  - 任务 5.2：动画下拉框加"平滑"；"平滑"模式下注入 morph JS

依赖：
  - time
  - PySide6（QTimer / QWidget / QVBoxLayout / QLabel / QSlider /
             QTextEdit / QMessageBox / Qt）
  - beeshow_constants（SLIDE_THEMES / _PlayWindow）

关键修复：
  - P0-2  : 使用 _PlayWindow 转发键盘事件，修复全屏快捷键失效
  - P1-12 : 演讲者模式无备注时也显示引导提示（原来点击无反应）
  - v5.0.5:
      * __init__ 里初始化 _play_window = None（在 beeshow.py 中）
      * _show_play_slide 开头 None 保护
      * _stop_play 用 getattr 判空 + 关闭后显式置 None
      * keyPressEvent 分层判空：翻页/ESC 不依赖 _play_window
        （修复测试中 _is_playing=True 但 _play_window=None 的场景）
      * _stop_play 的 _play_timer.stop() 加 try/except 防二次关闭异常

注意：
  - 不导入其他 beeshow_* Mixin，避免循环依赖
  - _set_status 由 NotesMixin 提供，本 Mixin 直接调用 self._set_status(...)
"""

import time

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QSlider, QTextEdit, QMessageBox,
)
from PySide6.QtCore import QTimer, Qt

from beeoffice.plugins.beeshow_constants import SLIDE_THEMES, _PlayWindow


class PlayMixin:
    """蜜演全屏播放 / 演讲者模式 / 排练计时 Mixin"""

    # ==================== 启动播放（P0-2） ====================
    def _start_play(self):
        """
        启动全屏播放。

        流程：
          1. 无幻灯片则直接返回
          2. 创建 _PlayWindow（转发键盘事件到本视图，P0-2）
          3. 启动计时器（每秒刷新时间标签）
          4. 渲染第一页并全屏显示
        """
        if not self._slides_html:
            return

        self._is_playing = True
        self._current_slide = 0
        self._start_time = time.time()
        self._timer_label.show()

        # 优化规划 §2.7：新建播放窗口前先回收上一次的。
        # 原实现每次 F5 都 new 一个 _PlayWindow 并覆盖引用，而它以 self 为 Qt
        # 父对象（子对象只在父对象销毁时才释放）且没有 WA_DeleteOnClose ——
        # close() 只是隐藏。结果每次播放/再播放都会泄漏一个完整的 WebEngine
        # 渲染进程。现在 _PlayWindow 已去父 + WA_DeleteOnClose，这里再兜一次底，
        # 覆盖"用户连按 F5 而没走 _stop_play"的路径。
        previous = getattr(self, "_play_window", None)
        if previous is not None:
            try:
                previous.close()        # WA_DeleteOnClose → 立即销毁并释放
            except RuntimeError:
                pass                        # 底层 C++ 对象已释放
            self._play_window = None

        # P0-2：使用 _PlayWindow 转发键盘事件
        self._play_window = _PlayWindow(self)
        self._play_window.resize(1024, 768)

        self._play_timer = QTimer(self)
        self._play_timer.timeout.connect(self._update_timer)
        self._play_timer.start(1000)

        self._show_play_slide()
        self._play_window.showFullScreen()
        self._play_window.setMouseTracking(True)
        self._play_window.setFocus()

    def _update_timer(self):
        """每秒刷新顶部计时标签（播放态才刷新）"""
        if self._is_playing:
            elapsed = int(time.time() - self._start_time)
            self._timer_label.setText(
                f"⏱ {elapsed//60:02d}:{elapsed%60:02d}"
            )

    # ==================== 停止播放（v5.0.5） ====================
    def _stop_play(self):
        """
        停止全屏播放。

        v5.0.5：
          用 getattr 判空并显式置 None。
          - 原实现 `if hasattr(self, '_play_window')` 在 __init__ 未初始化时
            会假；但一旦 _start_play 被调用后关闭，_play_window 仍持有旧引用，
            二次关闭会抛 RuntimeError。
          - 现在关闭后显式 self._play_window = None。
        """
        self._is_playing = False
        self._timer_label.hide()

        # 停止计时器（加 try/except 防二次关闭异常）
        if hasattr(self, '_play_timer'):
            try:
                self._play_timer.stop()
            except RuntimeError:
                pass

        # 关闭播放窗口（getattr 判空 + 显式置 None）
        play_window = getattr(self, '_play_window', None)
        if play_window is not None:
            try:
                play_window.close()
            except RuntimeError:
                pass
            self._play_window = None

        # 关闭演讲者视图（若有）
        if hasattr(self, '_notes_window'):
            try:
                self._notes_window.close()
            except RuntimeError:
                pass

    # ==================== 渲染播放页（v5.0.5 + v5.1） ====================
    def _show_play_slide(self):
        """
        渲染当前页到全屏播放窗口。

        v5.0.5：开头加 None 保护。
          原实现在 self._play_window 未创建时（例如测试里只设置
          _is_playing = True 就触发 keyPressEvent），
          会抛 AttributeError: 'BeeShowView' object has no attribute
          '_play_window'。

        v5.1 增量：
          - 任务 2.1：拼入版式 CSS
          - 任务 5.1：注入动态数字 JS
          - 任务 5.2：注入 morph JS（仅在"平滑"模式下）
          - 任务 4.3：广播翻页
        """
        # 未进入播放态，不渲染
        if self._play_window is None:
            return

        if 0 <= self._current_slide < len(self._slides_html):
            theme = SLIDE_THEMES[self._current_theme]
            bg = self._custom_bg or theme.get("bg", "#FFF")

            # 动画样式（任务 5.2：加"平滑"映射）
            anim = {
                "无": "",
                "淡入": "fadeIn",
                "滑入": "slideIn",
                "缩放": "zoomIn",
                "平滑": "",  # 平滑由 morph JS 实现，无 CSS 动画
            }[self._anim_combo.currentText()]

            anim_css = ""
            if anim:
                anim_css = (
                    f".slide{{animation:{anim} 0.5s ease-out}}"
                    f"@keyframes {anim}{{from{{opacity:0;"
                    f"transform:translateY(20px)}}"
                    f"to{{opacity:1;transform:translateY(0)}}}}"
                )
                if anim == "slideIn":
                    anim_css = (
                        f".slide{{animation:{anim} 0.5s ease-out}}"
                        f"@keyframes {anim}{{from{{transform:"
                        f"translateX(50px);opacity:0}}"
                        f"to{{transform:translateX(0);opacity:1}}}}"
                    )
                elif anim == "zoomIn":
                    anim_css = (
                        f".slide{{animation:{anim} 0.5s ease-out}}"
                        f"@keyframes {anim}{{from{{transform:"
                        f"scale(0.9);opacity:0}}"
                        f"to{{transform:scale(1);opacity:1}}}}"
                    )

            # 底部控制栏
            elapsed = int(time.time() - self._start_time)
            control_bar = (
                f"""<div style="position:fixed;bottom:0;left:0;right:0;"""
                f"""background:rgba(0,0,0,0.7);color:#FFF;"""
                f"""padding:10px 20px;display:flex;"""
                f"""justify-content:space-between;align-items:center;"""
                f"""font-size:14px;z-index:10000;">"""
                f"""<span>🐝 {self._current_theme}</span>"""
                f"""<span>{self._current_slide+1}/{len(self._slides_html)}</span>"""
                f"""<span>⏱ {elapsed//60:02d}:{elapsed%60:02d}</span>"""
                f"""<span>←→ 翻页 | B 黑屏 | R 排练 | ESC 退出</span>"""
                f"""</div>"""
            )

            # 任务 5.1：动态数字 JS
            dynamic_js = ""
            try:
                dynamic_js = self._get_dynamic_number_js()
            except AttributeError:
                pass

            # 任务 5.2：平滑动画 JS（仅在"平滑"模式下注入）
            morph_js = ""
            morph_ids_js = ""
            try:
                if self._is_morph_mode():
                    morph_js = self._get_morph_js()
                    ids = self._get_morph_ids_for_current_slide()
                    import json as _json
                    morph_ids_js = (
                        f"<script>window.__beeofficeMorphIds = "
                        f"{_json.dumps(ids, ensure_ascii=False)};</script>"
                    )
            except AttributeError:
                pass

            # 任务 2.1：拼入版式 CSS
            full_html = (
                f"""<!DOCTYPE html><html><head><meta charset="utf-8">"""
                f"""<style>{theme['css']}{self._get_layout_css()}"""
                f"""body{{background:{bg};}}{anim_css}</style></head>"""
                f"""<body><div class="slide">"""
                f"""{self._slides_html[self._current_slide]}</div>"""
                f"""{control_bar}{dynamic_js}"""
                f"""{morph_ids_js}{morph_js}</body></html>"""
            )

            self._play_window.setHtml(full_html)

            # 任务 4.3：广播翻页
            try:
                self._broadcast_slide()
            except AttributeError:
                pass

    # ==================== 演讲者模式（P1-12） ====================
    def _start_presenter_mode(self):
        """
        启动演讲者视图（P1-12：无备注时也显示提示）。

        原实现仅在有备注时创建 _notes_window，无备注时点击无反应。
        改为无论是否有备注都创建窗口：
          - 有备注：显示当前页备注 + 下一页预览
          - 无备注：显示引导提示
          - 两种情况都显示进度条
        """
        self._start_play()

        # P1-12：无论是否有备注，都打开演讲者视图
        self._notes_window = QWidget()
        self._notes_window.setWindowTitle("🎤 演讲者视图")
        layout = QVBoxLayout(self._notes_window)

        if any(self._speaker_notes):
            # 有备注：显示备注 + 下一页预览
            layout.addWidget(QLabel("<h2>当前页备注</h2>"))
            self._current_note_label = QLabel(
                self._speaker_notes[0] if self._speaker_notes else ""
            )
            self._current_note_label.setWordWrap(True)
            layout.addWidget(self._current_note_label)

            layout.addWidget(QLabel("<h2>下一页</h2>"))
            self._next_preview = QTextEdit()
            self._next_preview.setReadOnly(True)
            layout.addWidget(self._next_preview)
        else:
            # 无备注：显示引导提示
            tip = QLabel(
                "💡 当前演示文稿还没有备注\n\n"
                "点击工具栏「📝 备注」按钮，\n"
                "可为每张幻灯片添加演讲备注。"
            )
            tip.setAlignment(Qt.AlignCenter)
            tip.setStyleSheet(
                "QLabel{color:#666;font-size:14px;padding:40px;}"
            )
            tip.setWordWrap(True)
            layout.addWidget(tip)

            # 显式置 None，供 _update_presenter_view 判空
            self._current_note_label = None
            self._next_preview = None

        # 进度条（两种情况都有）
        self._progress_bar = QSlider(Qt.Horizontal)
        self._progress_bar.setMaximum(max(0, len(self._slides_html) - 1))
        self._progress_bar.valueChanged.connect(self._on_progress_changed)
        layout.addWidget(self._progress_bar)

        self._notes_window.resize(500, 400)
        self._notes_window.show()
        self._update_presenter_view()

    def _update_presenter_view(self):
        """
        刷新演讲者视图（P1-12：防御性检查 None）。

        无备注模式下 _current_note_label / _next_preview 均为 None，
        需要判空后再访问。
        """
        # 更新当前页备注
        if (hasattr(self, '_current_note_label')
                and self._current_note_label is not None):
            note = (
                self._speaker_notes[self._current_slide]
                if self._current_slide < len(self._speaker_notes)
                else ""
            )
            self._current_note_label.setText(note)

        # 更新下一页预览
        if (hasattr(self, '_next_preview')
                and self._next_preview is not None
                and self._current_slide + 1 < len(self._slides_html)):
            self._next_preview.setHtml(
                self._slides_html[self._current_slide + 1]
            )
        elif (hasattr(self, '_next_preview')
              and self._next_preview is not None):
            # 已是最后一页
            self._next_preview.setHtml(
                "<p style='color:#999'>（已是最后一页）</p>"
            )

        # 更新进度条
        if hasattr(self, '_progress_bar') and self._progress_bar is not None:
            self._progress_bar.setValue(self._current_slide)

    def _on_progress_changed(self, value):
        """进度条拖动：跳转到对应页"""
        if self._is_playing:
            self._current_slide = value
            self._show_play_slide()

    # ==================== 键盘（v5.0.5 分层判空） ====================
    def keyPressEvent(self, event):
        """
        全屏播放键盘事件。

        v5.0.5：分层判空。
          翻页 / ESC 不依赖 _play_window，提前 return；
          其他键统一先判空再处理。
          修复测试中只设置 _is_playing=True 但 _play_window=None
          时按键会抛 AttributeError 的问题。
        """
        # 非播放态：走默认处理
        if not self._is_playing:
            super().keyPressEvent(event)
            return

        key = event.key()

        # ---------- 翻页（不依赖 _play_window） ----------
        if key in (Qt.Key_Right, Qt.Key_Down, Qt.Key_Space, Qt.Key_PageDown):
            self._current_slide = min(
                self._current_slide + 1, len(self._slides_html) - 1
            )
            self._show_play_slide()
            self._update_presenter_view()
            return

        if key in (Qt.Key_Left, Qt.Key_Up, Qt.Key_PageUp):
            self._current_slide = max(self._current_slide - 1, 0)
            self._show_play_slide()
            self._update_presenter_view()
            return

        if key == Qt.Key_Home:
            self._current_slide = 0
            self._show_play_slide()
            return

        if key == Qt.Key_End:
            self._current_slide = len(self._slides_html) - 1
            self._show_play_slide()
            return

        if key == Qt.Key_Escape:
            self._stop_play()
            return

        # ---------- 以下操作需要 _play_window ----------
        if self._play_window is None:
            return

        if key == Qt.Key_F:
            # 全屏切换
            if self._play_window.isFullScreen():
                self._play_window.showNormal()
            else:
                self._play_window.showFullScreen()
        elif key == Qt.Key_B:
            # 黑屏
            self._play_window.setHtml(
                '<html><body style="background:#000;"></body></html>'
            )
        elif key == Qt.Key_R:
            # 排练计时开关
            self.toggle_rehearsal()

    # ==================== 排练计时 ====================
    def toggle_rehearsal(self):
        """切换排练计时状态"""
        if self._rehearsal_timer.isActive():
            self.stop_rehearsal()
        else:
            self.start_rehearsal()

    def start_rehearsal(self):
        """开始排练计时"""
        self._rehearsal_start_time = time.time()
        self.rehearsal_start_time = self._rehearsal_start_time
        self._rehearsal_elapsed = 0
        self._rehearsal_timer.start(100)
        self._rehearsal_label.show()
        self._rehearsal_label.setText("⏱ 排练: 00:00")
        self._set_status("⏱ 排练计时开始", 2000)

    def stop_rehearsal(self):
        """停止排练计时"""
        if self._rehearsal_start_time:
            self._rehearsal_elapsed = time.time() - self._rehearsal_start_time
        self._rehearsal_timer.stop()
        self._rehearsal_start_time = None
        self.rehearsal_start_time = None
        minutes = int(self._rehearsal_elapsed // 60)
        seconds = int(self._rehearsal_elapsed % 60)
        self._rehearsal_label.setText(
            f"⏱ 排练: {minutes:02d}:{seconds:02d}"
        )
        self._set_status(
            f"⏱ 排练总时长: {minutes:02d}:{seconds:02d}", 5000
        )

    def reset_rehearsal(self):
        """重置排练计时"""
        self._rehearsal_timer.stop()
        self._rehearsal_start_time = None
        self.rehearsal_start_time = None
        self._rehearsal_elapsed = 0
        self._rehearsal_label.setText("⏱ 排练: 00:00")
        self._rehearsal_label.hide()

    def _update_rehearsal_time(self):
        """更新排练计时显示（每 100ms 由 _rehearsal_timer 触发）"""
        if self._rehearsal_start_time is None:
            return
        elapsed = time.time() - self._rehearsal_start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        self._rehearsal_label.setText(
            f"⏱ 排练: {minutes:02d}:{seconds:02d}"
        )