# tests/test_p0_regression/test_p0_02_play_window.py
"""
P0-2 回归：_PlayWindow 应把键盘事件转发给 BeeShowView。

背景：
  蜜演全屏播放时创建一个独立的 QWebEngineView（_PlayWindow）。
  独立窗口有自己的键盘焦点，BeeShowView.keyPressEvent 收不到事件，
  导致所有快捷键（翻页 / ESC / L / B / P / R）失效。

修复：
  新增 _PlayWindow 类，重写 keyPressEvent / keyReleaseEvent，
  转发给 owner（BeeShowView）处理。

测试策略：
  1. 直接构造 _PlayWindow(view)
  2. 发送 QKeyEvent
  3. 断言 view 的状态被更新（如 _current_slide 前进 / _is_playing 变 False）

v5.0.5：
  - 复用 conftest.py 里的 beeshow_view fixture
  - _PlayWindow 显式清理（setParent(None) + deleteLater + qtbot.wait），
    避免 QWebEngineView profile 释放警告
"""
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeyEvent


def _cleanup_play_window(window, qtbot):
    """显式清理 _PlayWindow，释放 WebEngine profile。"""
    try:
        window.setParent(None)
        window.deleteLater()
        qtbot.wait(50)
    except Exception:
        pass


# ==================== 类存在性 ====================

def test_play_window_class_exists():
    """P0-2：beeshow.py 应导出 _PlayWindow 类。"""
    from beeoffice.plugins.beeshow import _PlayWindow

    assert _PlayWindow is not None, (
        "P0-2：beeshow.py 未导出 _PlayWindow 类。"
        "全屏播放时键盘事件无法转发，所有快捷键会失效"
    )
    assert isinstance(_PlayWindow, type)


# ==================== 键盘事件转发 ====================

def test_play_window_forwards_keypress_to_owner(beeshow_view, qtbot):
    """P0-2：_PlayWindow.keyPressEvent 应转发给 owner。"""
    from beeoffice.plugins.beeshow import _PlayWindow

    view = beeshow_view
    view._slides_html = ["<h1>A</h1>", "<h1>B</h1>"]
    view._slide_titles = ["A", "B"]
    view._speaker_notes = ["", ""]
    view._is_playing = True
    view._current_slide = 0

    window = _PlayWindow(view)
    try:
        # 按右键 → 前进一页
        evt = QKeyEvent(QEvent.KeyPress, Qt.Key_Right, Qt.NoModifier)
        window.keyPressEvent(evt)

        assert view._current_slide == 1, (
            "P0-2：_PlayWindow 未转发 keyPressEvent 给 owner。"
            "全屏播放时翻页快捷键会失效"
        )

        # 按左键 → 后退一页
        evt2 = QKeyEvent(QEvent.KeyPress, Qt.Key_Left, Qt.NoModifier)
        window.keyPressEvent(evt2)
        assert view._current_slide == 0
    finally:
        _cleanup_play_window(window, qtbot)


def test_play_window_forwards_escape_to_owner(beeshow_view, qtbot):
    """P0-2：_PlayWindow ESC 应触发 owner._stop_play。"""
    from beeoffice.plugins.beeshow import _PlayWindow

    view = beeshow_view
    view._slides_html = ["<h1>A</h1>"]
    view._slide_titles = ["A"]
    view._speaker_notes = [""]
    view._is_playing = True

    window = _PlayWindow(view)
    try:
        evt = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
        window.keyPressEvent(evt)

        assert view._is_playing is False, (
            "P0-2：_PlayWindow ESC 应停止播放"
        )
    finally:
        _cleanup_play_window(window, qtbot)


# ==================== 无 owner 兜底 ====================

def test_play_window_without_owner_falls_back(qtbot):
    """P0-2：_PlayWindow 无 owner 时应回退到父类实现（不崩）。"""
    from beeoffice.plugins.beeshow import _PlayWindow

    window = _PlayWindow(None)
    qtbot.addWidget(window)

    try:
        evt = QKeyEvent(QEvent.KeyPress, Qt.Key_Right, Qt.NoModifier)
        # 无 owner 时走 QWebEngineView.keyPressEvent，不抛异常即通过
        window.keyPressEvent(evt)
    finally:
        _cleanup_play_window(window, qtbot)