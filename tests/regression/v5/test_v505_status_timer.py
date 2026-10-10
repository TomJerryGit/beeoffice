# tests/test_p2_regression/test_v505_status_timer.py
"""
v5.0.5 回归：set_global_status 的延迟重置必须使用绑定生命周期的 QTimer，
            而不是 QTimer.singleShot。

背景：
  原实现用 QTimer.singleShot(timeout, lambda: status_label.setText(...))。
  singleShot 不绑定控件生命周期。窗口关闭后回调仍会执行，
  此时 status_label 已析构 → 抛：
      RuntimeError: Internal C++ object (QLabel) already deleted

修复后：
  - 新增 self._status_timer = QTimer(self)（parent 是 app 本身）
  - set_global_status 改用它
  - closeEvent 显式 stop()
  - _reset_status_text 带 RuntimeError 保护

测试策略：
  与其尝试"复现崩溃"（很难稳定复现），不如断言**结构**：
  - _status_timer 存在且 parent 是 app
  - 不同 timeout 下的启动/停止行为
  - closeEvent 会 stop 定时器
  这些断言能防止未来把实现改回 singleShot。
"""
import pytest
from PySide6.QtCore import QTimer


def test_status_timer_exists_and_owned(app):
    """v5.0.5：_status_timer 应存在且 parent 绑定到 app。"""
    assert hasattr(app, "_status_timer")
    assert isinstance(app._status_timer, QTimer)
    assert app._status_timer.parent() is app, (
        "_status_timer 必须绑定到 app 生命周期。"
        "若 parent 为 None，窗口销毁后定时器仍会触发"
    )
    assert app._status_timer.isSingleShot(), "状态重置应为单次定时器"


def test_set_status_with_timeout_starts_timer(app):
    """v5.0.5：timeout>0 时应启动定时器。"""
    app._status_timer.stop()
    app.set_global_status("测试消息", 100)
    assert app.status_label.text() == "测试消息"
    assert app._status_timer.isActive()


def test_set_status_zero_timeout_does_not_start_timer(app):
    """v5.0.5：timeout=0 时不应启动定时器。"""
    app._status_timer.stop()
    app.set_global_status("常驻消息", 0)
    assert app.status_label.text() == "常驻消息"
    assert not app._status_timer.isActive()


def test_new_status_resets_timer(app):
    """v5.0.5：连续设置消息应复用同一个 timer 并重启。"""
    app.set_global_status("消息1", 5000)
    timer_id = id(app._status_timer)
    app.set_global_status("消息2", 5000)
    assert id(app._status_timer) == timer_id, (
        "应复用同一个 timer 实例，而不是每次创建新的"
    )
    assert app._status_timer.isActive()


def test_close_event_stops_status_timer(app):
    """v5.0.5：closeEvent 应停止状态栏定时器，防止关闭后回调。"""
    app.set_global_status("测试", 10000)
    assert app._status_timer.isActive()

    app.close()
    assert not app._status_timer.isActive(), (
        "closeEvent 应 stop() 状态栏定时器。"
        "否则窗口关闭后回调仍可能触发"
    )


def test_reset_status_text_has_runtime_guard(app, monkeypatch):
    """
    v5.0.5：_reset_status_text 应带 RuntimeError 保护。

    模拟 status_label 已析构的情况：让 setText 抛 RuntimeError，
    断言 _reset_status_text 不向外抛异常。
    """
    def fake_setText(msg):
        raise RuntimeError("Internal C++ object already deleted")

    monkeypatch.setattr(app.status_label, "setText", fake_setText)

    # 不应抛异常
    app._reset_status_text()