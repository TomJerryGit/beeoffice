"""app 深层分支：PDF/同步/移动端/监控入口。"""
from PySide6.QtWidgets import QMessageBox, QWidget

import pytest

from beeoffice.app import BeeApp


@pytest.fixture
def app(qtbot):
    window = BeeApp()
    qtbot.addWidget(window)
    return window


def test_open_pdf_pages(app, monkeypatch):
    import beeoffice.plugins.pdf_pages_dialog as mod
    calls = []

    class FakeDialog(QWidget):
        def __init__(self, parent):
            super().__init__(parent)
            calls.append("init")
        def show(self):
            calls.append("show")

    monkeypatch.setattr(mod, "PdfPagesDialog", FakeDialog)
    dialog = app._open_pdf_pages()
    assert isinstance(dialog, FakeDialog)
    assert app._pdf_pages_dialog is dialog
    assert "show" in calls


def test_open_pdf_annotator(app, monkeypatch, tmp_path):
    import beeoffice.plugins.pdf_annotator as mod
    calls = []

    class FakeAnnotator(QWidget):
        def open_pdf(self, path):
            calls.append(path)
        def show(self):
            calls.append("show")

    monkeypatch.setattr(mod, "PDFAnnotator", FakeAnnotator)
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF")
    app._open_pdf_annotator(str(pdf))
    assert calls == [str(pdf), "show"]


def test_show_webdav_settings(app, monkeypatch):
    import beeoffice.cloud_settings as mod
    called = []
    monkeypatch.setattr(mod, "show_cloud_settings", lambda parent: called.append(parent))
    app._show_webdav_settings()
    assert called == [app]


def test_sync_now_without_storage(app, monkeypatch):
    import beeoffice.cloud as mod
    calls = []
    monkeypatch.setattr(mod, "get_cloud_storage", lambda: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: calls.append(a))
    app._sync_now()
    assert calls


def test_open_mobile_download(app, monkeypatch):
    import webbrowser
    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url))
    app._open_mobile_download()
    assert "github.com" in opened[0]


def test_start_mobile_server(app, monkeypatch):
    import beeoffice.mobile as mod
    started = []

    class FakeServer:
        def __init__(self, parent):
            self.parent = parent
        def start(self):
            started.append(True)

    monkeypatch.setattr(mod, "MobileServer", FakeServer)
    app.mobile_server = None
    app._start_mobile_server()
    assert started
    assert isinstance(app.mobile_server, FakeServer)
