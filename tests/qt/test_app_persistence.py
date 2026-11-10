"""结构化补测：app.py 保存/标签/会话恢复。"""
from pathlib import Path

import pytest
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox, QWidget

from beeoffice.app import BeeApp


@pytest.fixture
def app(qtbot):
    window = BeeApp()
    qtbot.addWidget(window)
    return window


class FakeDoc(QWidget):
    def __init__(self):
        super().__init__()
        self.saved = 0
        self.save_result = True

    def save(self):
        self.saved += 1
        return self.save_result


def test_save_current_success(app, monkeypatch):
    doc = FakeDoc()
    app.tab_manager.addTab(doc, "fake")
    app.tab_manager.setCurrentWidget(doc)
    monkeypatch.setattr(app.tab_manager, "_mark_saved", lambda w: None)
    app._save_current()
    assert doc.saved == 1
    assert "已保存" in app.status_label.text()


def test_save_current_failure(app):
    doc = FakeDoc()
    doc.save_result = False
    app.tab_manager.addTab(doc, "fake")
    app.tab_manager.setCurrentWidget(doc)
    app._save_current()
    assert "保存失败" in app.status_label.text()


def test_tab_file_paths_and_mark_saved(app):
    doc = FakeDoc()
    app.tab_manager.addTab(doc, "● fake")
    app.tab_manager.set_tab_file_path(doc, "C:/tmp/fake.docx")
    assert "C:/tmp/fake.docx" in app.tab_manager.get_open_file_paths()
    app.tab_manager._mark_saved(doc)
    assert app.tab_manager.tabText(app.tab_manager.indexOf(doc)) == "fake"


def test_restore_session_yes(app, tmp_path, monkeypatch):
    f1 = tmp_path / "a.docx"
    f2 = tmp_path / "b.docx"
    f1.write_text("x")
    f2.write_text("x")
    app.settings.open_tabs = [str(f1), str(f2), str(tmp_path / "missing.docx")]
    opened = []
    monkeypatch.setattr(app, "_open_recent", lambda p: opened.append(p))
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *a, **k: QMessageBox.Yes,
    )
    app._restore_session()
    assert opened == [str(f1), str(f2)]


def test_restore_session_no_files(app, tmp_path, monkeypatch):
    app.settings.open_tabs = [str(tmp_path / "missing.docx")]
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("不应弹窗")),
    )
    app._restore_session()
    assert True


def test_close_event_persists_open_tabs(app, tmp_path, monkeypatch):
    doc = FakeDoc()
    app.tab_manager.addTab(doc, "fake")
    path = str(tmp_path / "x.docx")
    app.tab_manager.set_tab_file_path(doc, path)
    saved = []
    monkeypatch.setattr(type(app.settings), "save", lambda self: saved.append(True))
    event = QCloseEvent()
    app.closeEvent(event)
    assert path in app.settings.open_tabs
    assert saved
