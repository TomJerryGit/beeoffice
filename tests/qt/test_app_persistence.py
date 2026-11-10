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
        self.save_as_called = 0
        self.template_called = 0
        self.save_result = True
        self._content = ""

    def content(self):
        return self._content

    def save(self):
        self.saved += 1
        return self.save_result

    def save_as(self):
        self.save_as_called += 1

    def save_as_template(self):
        self.template_called += 1


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


def test_save_as_current_and_template(app):
    doc = FakeDoc()
    app.tab_manager.addTab(doc, "fake")
    app.tab_manager.setCurrentWidget(doc)
    app._save_as_current()
    app._save_as_template()
    assert doc.save_as_called == 1
    assert doc.template_called == 1


def test_toggle_high_contrast(app, monkeypatch):
    saved = []
    monkeypatch.setattr(type(app.settings), "save", lambda self: saved.append(True))
    from beeoffice.theme import Theme
    old = Theme.is_high_contrast()
    try:
        app._toggle_high_contrast(True)
        assert app.settings.high_contrast is True
        assert Theme.is_high_contrast() is True
        assert saved
    finally:
        Theme.set_high_contrast(old)


def test_sync_tab_title_and_set_status(app, tmp_path):
    doc = FakeDoc()
    app.tab_manager.addTab(doc, "old")
    app.tab_manager.setCurrentWidget(doc)
    app.sync_tab_title(doc, str(tmp_path / "hello.docx"))
    assert "hello.docx" in app.tab_manager.tabText(app.tab_manager.indexOf(doc))
    assert "hello.docx" in app.windowTitle()
    app.set_global_status("测试状态", 5000)
    assert app.status_label.text() == "测试状态"
    assert app._status_timer.isActive()


def test_tab_close_request_yes(app, monkeypatch):
    doc = FakeDoc()
    app.tab_manager.addTab(doc, "● fake")
    app.tab_manager._tab_initial_content[id(doc)] = "old"
    doc._content = "new"
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    before = app.tab_manager.count()
    app.tab_manager._on_tab_close_request(app.tab_manager.indexOf(doc))
    assert app.tab_manager.count() == before - 1


def test_tab_close_request_no(app, monkeypatch):
    doc = FakeDoc()
    app.tab_manager.addTab(doc, "● fake")
    app.tab_manager._tab_initial_content[id(doc)] = "old"
    doc._content = "new"
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    before = app.tab_manager.count()
    app.tab_manager._on_tab_close_request(app.tab_manager.indexOf(doc))
    assert app.tab_manager.count() == before


def test_make_tab_title_unique(app):
    first = app._make_tab_title("📝 测试")
    app.tab_manager.addTab(FakeDoc(), first)
    second = app._make_tab_title("📝 测试")
    assert second != first or second.endswith(")")


def test_self_save_window(app):
    app.notify_self_save("C:/tmp/x.docx")
    assert app._is_self_save("C:/tmp/x.docx") is True
    assert app._is_self_save("C:/tmp/other.docx") is False


def test_unsaved_content_helpers(app):
    doc = FakeDoc()
    doc._content = "abc"
    assert app._get_widget_content(doc) == "abc"
    app.tab_manager.addTab(doc, "fake")
    app.tab_manager._tab_initial_content[id(doc)] = "abc"
    assert app._has_unsaved_changes(doc) is False
    doc._content = "abcd"
    assert app._has_unsaved_changes(doc) is True


def test_autosave_saves_changed_doc(app, monkeypatch):
    doc = FakeDoc()
    doc._content = "new"
    app.tab_manager.addTab(doc, "fake")
    app.tab_manager.setCurrentWidget(doc)
    app.tab_manager._tab_initial_content[id(doc)] = "old"
    app._autosave()
    assert doc.saved == 1
    assert "自动保存" in app.status_label.text()


def test_next_prev_tab(app):
    d1, d2 = FakeDoc(), FakeDoc()
    app.tab_manager.addTab(d1, "1")
    app.tab_manager.addTab(d2, "2")
    app.tab_manager.setCurrentIndex(0)
    app._next_tab()
    assert app.tab_manager.currentIndex() == 1
    app._prev_tab()
    assert app.tab_manager.currentIndex() == 0


def test_clear_recent(app, monkeypatch):
    app.settings.recent_files = ["C:/a", "C:/b"]
    called = []
    monkeypatch.setattr(app, "_update_recent_menu", lambda: called.append(True))
    monkeypatch.setattr(type(app.settings), "save", lambda self: None)
    app._clear_recent()
    assert app.settings.recent_files == []
    assert called


def test_reset_status_text(app):
    app.status_label.setText("x")
    app._reset_status_text()
    assert app.status_label.text() != "x"


def test_register_plugin_menus(app):
    calls = []

    class P:
        name = "p1"
        def register_menus(self, menu_bar):
            calls.append(menu_bar)

    app.plugin_manager = object()
    app.plugins = [P()]
    app._register_plugin_menus()
    assert calls == [app.menuBar()]


def test_lazy_load_modules(app, monkeypatch):
    import beeoffice.plugin_manager as pm

    class FakeManager:
        def __init__(self, parent):
            self.plugins = []
        def discover_plugins(self):
            self.discovered = True
        def load_plugins(self):
            self.loaded = True

    monkeypatch.setattr(pm, "PluginManager", FakeManager)
    app._lazy_load_modules()
    assert app._modules_loaded is True
    assert app.status_label.text() != ""


def test_update_recent_menu(app):
    app.settings.recent_files = ["C:/a.docx", "C:/b.docx"]
    app._update_recent_menu()
    actions = app.recent_menu.actions()
    assert len(actions) >= 3
    assert any("a.docx" in a.text() for a in actions)
    assert any(a.toolTip() == "C:/a.docx" for a in actions)


def test_check_for_updates_none(app, monkeypatch):
    import beeoffice.update_checker as uc
    from PySide6.QtWidgets import QMessageBox
    calls = []
    monkeypatch.setattr(uc, "check_for_update", lambda v: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: calls.append(a))
    app.check_for_updates()
    assert calls


def test_check_for_updates_error(app, monkeypatch):
    import beeoffice.update_checker as uc
    from PySide6.QtWidgets import QMessageBox
    calls = []
    def fail(v):
        raise uc.UpdateError("bad")
    monkeypatch.setattr(uc, "check_for_update", fail)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: calls.append(a))
    app.check_for_updates()
    assert calls


def test_check_for_updates_available(app, monkeypatch):
    import beeoffice.update_checker as uc
    from PySide6.QtWidgets import QMessageBox
    from PySide6.QtGui import QDesktopServices
    class Info:
        version = "9.9.9"
        html_url = "https://example.test/release"
    monkeypatch.setattr(uc, "check_for_update", lambda v: Info())
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    app.check_for_updates()
    assert opened == ["https://example.test/release"]
