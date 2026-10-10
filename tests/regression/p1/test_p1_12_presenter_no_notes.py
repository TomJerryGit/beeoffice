# tests/test_p2_regression/test_p1_12_presenter_no_notes.py
"""
P1-12 回归：蜜演无备注时点「演讲者模式」应显示引导提示，
            而不是无任何反应。

背景：
  原 _start_presenter_mode 只在 `any(self._speaker_notes)` 时才创建
  _notes_window。无备注时点击按钮，用户看不到任何反馈。

修复：
  无论是否有备注都创建窗口；无备注时显示引导提示 QLabel；
  _current_note_label / _next_preview 置 None（避免后续访问崩溃）。

测试策略：
  1. 无备注场景：_notes_window 被创建、引导提示存在、
     _current_note_label 为 None
  2. _update_presenter_view 在 None 时不崩溃

v5.0.5 优化：
  改用 conftest.py 里统一的 beeshow_view fixture，
  显式释放 QWebEngineView profile，消除启动/退出时的警告：
      Release of profile requested but WebEnginePage still not deleted.
"""


def _prepare(view, notes):
    """配置 BeeShowView 的幻灯片与备注。"""
    view._slides_html = ["<h1>第一页</h1>", "<h1>第二页</h1>"]
    view._slide_titles = ["第一页", "第二页"]
    view._speaker_notes = notes
    return view


def test_presenter_mode_without_notes_creates_window(beeshow_view):
    """P1-12：无备注时也应创建 _notes_window。"""
    view = _prepare(beeshow_view, ["", ""])
    view._start_presenter_mode()

    assert getattr(view, "_notes_window", None) is not None, (
        "P1-12：无备注时 _start_presenter_mode 仍应创建窗口。"
        "原实现只在有备注时才创建，导致点击无反应"
    )
    assert view._notes_window.isVisible()
    # 无备注时这两个属性应为 None（避免后续访问崩溃）
    assert view._current_note_label is None
    assert view._next_preview is None


def test_presenter_mode_with_notes_populates_labels(beeshow_view):
    """P1-12：有备注时应显示备注 + 下一页预览。"""
    view = _prepare(beeshow_view, ["备注1", "备注2"])
    view._start_presenter_mode()

    assert view._notes_window is not None
    assert view._current_note_label is not None
    assert view._next_preview is not None


def test_update_presenter_view_handles_none(beeshow_view):
    """
    P1-12：_update_presenter_view 在 _current_note_label / _next_preview
            为 None 时不应崩溃。

    原实现在无备注场景下直接访问 _current_note_label.setText 会抛
    AttributeError。
    """
    view = _prepare(beeshow_view, [""])
    view._start_presenter_mode()

    # 手动调用（正常情况下由 progress_bar.valueChanged 触发）
    view._update_presenter_view()   # 不应抛异常


def test_presenter_mode_has_progress_bar_in_both_cases(beeshow_view):
    """P1-12：有无备注都应有进度条。"""
    # 无备注
    view = _prepare(beeshow_view, [""])
    view._start_presenter_mode()
    assert hasattr(view, "_progress_bar")
    assert view._progress_bar is not None

    view._stop_play()

    # 有备注
    view2 = _prepare(beeshow_view, ["备注"])
    view2._start_presenter_mode()
    assert hasattr(view2, "_progress_bar")
    assert view2._progress_bar is not None