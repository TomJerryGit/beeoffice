# -*- coding: utf-8 -*-
"""
蜜演全屏播放：播放窗口必须是顶层窗口（P1）

背景：
    `_PlayWindow(owner)` 以主视图为 parent 构造，但没有 `Qt.Window` 标志，
    因此只是一个子控件。Qt 文档明确：`showFullScreen()` 只对窗口生效。
    结果就是"点了全屏播放，但它只是铺在主界面里"。

本文件用一个断言把这件事锁死：播放窗口 `isWindow()` 必须为 True。
"""
import pytest

pytest.importorskip("PySide6.QtWebEngineWidgets")


def test_play_window_is_top_level(qtbot):
    from beeoffice.plugins.beeshow_constants import _PlayWindow

    class _FakeOwner:
        """最小 owner：_PlayWindow 只需要它做 parent 与事件转发。"""

        def __init__(self):
            from PySide6.QtWidgets import QWidget

            self.widget = QWidget()
            qtbot.addWidget(self.widget)

        def keyPressEvent(self, event):  # pragma: no cover - 仅转发占位
            pass

        def keyReleaseEvent(self, event):  # pragma: no cover
            pass

    owner = _FakeOwner()
    window = _PlayWindow(owner.widget)
    qtbot.addWidget(window)

    assert window.isWindow(), (
        "播放窗口不是顶层窗口，showFullScreen() 不会生效"
    )
