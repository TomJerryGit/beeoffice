"""BeeShow 同步 Mixin 交互补测。"""
import pytest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QWidget

import beeoffice.plugins.beeshow_sync_mixin as sync_mixin
from beeoffice.plugins.beeshow_sync_mixin import SyncMixin


class FakeServer:
    def __init__(self, *a, **k):
        self.calls = []
        self.viewer_count = 2
    def start(self): return True
    def stop(self): self.stopped = True
    def get_viewer_url(self): return "http://127.0.0.1:8765/?t=abc"
    def broadcast_slide(self, **k): self.calls.append(("slide", k))
    def broadcast_laser(self, *a, **k): self.calls.append(("laser", a, k))
    def broadcast_black_screen(self, v): self.calls.append(("black", v))
    def broadcast_theme(self, t): self.calls.append(("theme", t))


class FakeShow(SyncMixin, QWidget):
    def __init__(self):
        QWidget.__init__(self)
        self._init_sync_state()
        self._slides_html = ["a", "b"]
        self._current_slide = 1
        self.status = []
    def _set_status(self, text, ms=0): self.status.append(text)


@pytest.fixture
def show(qtbot, monkeypatch):
    obj = FakeShow()
    qtbot.addWidget(obj)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    return obj


def test_start_no_slides(show, monkeypatch):
    show._slides_html = []
    calls = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: calls.append(a))
    show._start_sync_mode()
    assert calls


def test_start_and_stop(show, monkeypatch):
    monkeypatch.setattr(sync_mixin, "SyncServer", FakeServer)
    show._show_sync_dialog = lambda: None
    show._start_sync_mode()
    assert show._sync_enabled is True
    assert "8765" in show._sync_url
    assert show._sync_server.calls[0][0] == "slide"
    show._stop_sync_mode()
    assert show._sync_enabled is False
    assert show._sync_url == ""


def test_start_failure(show, monkeypatch):
    class Bad(FakeServer):
        def start(self): return False
    monkeypatch.setattr(sync_mixin, "SyncServer", Bad)
    show._start_sync_mode()
    assert show._sync_enabled is False
    assert show._sync_server is None


def test_toggle(show, monkeypatch):
    monkeypatch.setattr(sync_mixin, "SyncServer", FakeServer)
    show._show_sync_dialog = lambda: None
    show._toggle_sync_mode()
    assert show._sync_enabled is True
    show._toggle_sync_mode()
    assert show._sync_enabled is False


def test_broadcasts_and_throttle(show, monkeypatch):
    show._sync_server = FakeServer()
    show._sync_enabled = True
    show._broadcast_slide()
    show._broadcast_black_screen(True)
    show._broadcast_theme("dark")
    show._last_laser_broadcast = 0
    show._broadcast_laser(0.1, 0.2)
    show._broadcast_laser(0.2, 0.3)  # 节流
    calls = show._sync_server.calls
    assert any(c[0] == "slide" for c in calls)
    assert any(c[0] == "black" for c in calls)
    assert any(c[0] == "theme" for c in calls)
    assert len([c for c in calls if c[0] == "laser"]) == 1
    # 未启用时不广播
    show._sync_enabled = False
    n = len(calls)
    show._broadcast_slide()
    show._broadcast_laser(0.5, 0.5)
    assert len(show._sync_server.calls) == n


def test_dialog_and_copy(show, monkeypatch):
    show._sync_server = FakeServer()
    show._sync_url = "http://x"
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)
    show._show_sync_dialog()
    show._copy_to_clipboard("http://x")
    assert QApplication.clipboard().text() == "http://x"


def test_cleanup(show):
    show._sync_server = FakeServer()
    show._sync_enabled = True
    show._cleanup_sync()
    assert show._sync_server is None
    assert show._sync_enabled is False


def test_sync_error_branches(show, monkeypatch):
    import beeoffice.plugins.beeshow_sync_mixin as m
    class BoomServer:
        def __init__(self, *a, **k): pass
        def start(self): raise RuntimeError("boom")
    monkeypatch.setattr(m, "SyncServer", BoomServer)
    calls = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: calls.append(a))
    show._start_sync_mode()
    assert calls and show._sync_enabled is False
    # stop 抛异常
    class BadStop:
        def stop(self): raise RuntimeError("stop")
    show._sync_server = BadStop()
    show._stop_sync_mode()
    assert show._sync_server is None
    # 广播异常
    class BadBroadcast:
        def broadcast_slide(self, **k): raise RuntimeError("b")
        def broadcast_laser(self, *a, **k): raise RuntimeError("b")
        def broadcast_black_screen(self, *a): raise RuntimeError("b")
        def broadcast_theme(self, *a): raise RuntimeError("b")
    show._sync_server = BadBroadcast()
    show._sync_enabled = True
    show._broadcast_slide()
    show._last_laser_broadcast = 0
    show._broadcast_laser(0.1, 0.2)
    show._broadcast_black_screen(True)
    show._broadcast_theme("dark")
    # 未启用时 black/theme 直接返回
    show._sync_enabled = False
    show._broadcast_black_screen(True)
    show._broadcast_theme("dark")
    # 无服务器 dialog
    show._sync_server = None
    show._show_sync_dialog()


def test_sync_clipboard_and_cleanup_errors(show, monkeypatch):
    class BadClipboard:
        def setText(self, text): raise RuntimeError("clip")
    monkeypatch.setattr("PySide6.QtWidgets.QApplication.clipboard", staticmethod(lambda: BadClipboard()))
    show._copy_to_clipboard("x")
    class BadStop:
        def stop(self): raise RuntimeError("stop")
    show._sync_server = BadStop()
    show._cleanup_sync()
    assert show._sync_server is None
