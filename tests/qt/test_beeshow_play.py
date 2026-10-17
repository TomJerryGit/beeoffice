# tests/test_beeshow_play.py
"""蜜演播放功能测试"""
import pytest
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeyEvent


class TestStartPlay:
    def test_start_play_requires_slides(self, qtbot):
        from beeoffice.plugins.beeshow import BeeShowView
        view = BeeShowView()
        qtbot.addWidget(view)
        view._slides_html = []
        view._is_playing = False
        view._start_play()
        assert not view._is_playing

    def test_start_play_resets_to_first(self, qtbot):
        from beeoffice.plugins.beeshow import BeeShowView
        view = BeeShowView()
        qtbot.addWidget(view)
        view._slides_html = ["<h1>A</h1>", "<h1>B</h1>"]
        view._slide_titles = ["A", "B"]
        view._speaker_notes = ["", ""]
        view._current_slide = 1
        try:
            view._start_play()
            assert view._current_slide == 0
        finally:
            view._stop_play()


class TestPlayNavigation:
    def test_right_key_advances(self, qtbot):
        from beeoffice.plugins.beeshow import BeeShowView
        view = BeeShowView()
        qtbot.addWidget(view)
        view._slides_html = ["<h1>A</h1>", "<h1>B</h1>"]
        view._slide_titles = ["A", "B"]
        view._speaker_notes = ["", ""]
        view._is_playing = True
        view._current_slide = 0
        evt = QKeyEvent(QEvent.KeyPress, Qt.Key_Right, Qt.NoModifier)
        view.keyPressEvent(evt)
        assert view._current_slide == 1
