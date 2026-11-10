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
