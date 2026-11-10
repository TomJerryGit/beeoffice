"""legacy WebDAV 设置/同步入口补测。"""
from PySide6.QtWidgets import QDialog, QMessageBox, QWidget

import pytest

import beeoffice.webdav as wd


@pytest.fixture
def parent(qtbot):
    w = QWidget()
    qtbot.addWidget(w)
    return w


def test_show_webdav_settings_builds_dialog(parent, monkeypatch):
    called = []
    class FakeConfig:
        url = "https://example.test/dav"
        username = "u"
        password = "p"
        auto_sync = False
        enabled = False
        def save(self):
            called.append("save")
    monkeypatch.setattr(wd, "WebDAVConfig", FakeConfig)
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    wd.show_webdav_settings(parent)
    assert called == []


def test_sync_now_disabled(parent, monkeypatch):
    class FakeConfig:
        enabled = False
        url = ""
    class FakeMsg:
        calls = []
    monkeypatch.setattr(wd, "WebDAVConfig", FakeConfig)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: FakeMsg.calls.append(a))
    wd.sync_now(parent)
    assert FakeMsg.calls


def test_sync_now_no_url(parent, monkeypatch):
    class FakeConfig:
        enabled = True
        url = ""
    calls = []
    monkeypatch.setattr(wd, "WebDAVConfig", FakeConfig)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: calls.append(a))
    wd.sync_now(parent)
    assert calls


def test_on_sync_finished(parent, monkeypatch):
    class Dlg:
        def __init__(self): self.closed = False
        def close(self): self.closed = True
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    dlg = Dlg()
    parent._sync_worker = object()
    wd._on_sync_finished(parent, dlg, True, "ok")
    assert dlg.closed
    assert parent._sync_worker is None


def test_sync_now_starts_worker(parent, monkeypatch):
    from PySide6.QtCore import QObject, Signal
    import beeoffice.plugins.webdav_sync as sync_mod

    class FakeConfig:
        enabled = True
        url = "https://example.test/dav"
        username = "u"
        password = "p"

    class FakeWorker(QObject):
        progress = Signal(int)
        finished = Signal(bool, str, int)
        def __init__(self, *args):
            super().__init__()
            self.started = False
        def start(self):
            self.started = True
        def cancel(self):
            pass
        def isRunning(self):
            return self.started

    monkeypatch.setattr(wd, "WebDAVConfig", FakeConfig)
    monkeypatch.setattr(sync_mod, "WebDAVSyncWorker", FakeWorker)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    parent._sync_worker = None
    wd.sync_now(parent)
    assert isinstance(parent._sync_worker, FakeWorker)
    assert parent._sync_worker.started


def test_sync_now_running_worker(parent, monkeypatch):
    class FakeConfig:
        enabled = True
        url = "https://example.test/dav"
        username = "u"
        password = "p"

    class Running:
        def isRunning(self):
            return True

    calls = []
    monkeypatch.setattr(wd, "WebDAVConfig", FakeConfig)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: calls.append(a))
    parent._sync_worker = Running()
    wd.sync_now(parent)
    assert calls
