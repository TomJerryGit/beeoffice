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


def test_demo_batch_ai_dispatch(app):
    class FakeDoc(QWidget):
        def __init__(self):
            super().__init__()
            self.calls = []
        def _start_play(self): self.calls.append("play")
        def _export_pptx(self): self.calls.append("pptx")
        def _analyze_data(self): self.calls.append("analyze")
        def _nl_to_formula(self): self.calls.append("nl")
        def _play_macro(self): self.calls.append("macro_play")
        def _toggle_macro_recording(self): self.calls.append("macro_toggle")
        def _ai_continue(self): self.calls.append("ai_continue")
        def _ai_polish(self): self.calls.append("ai_polish")
        def _ai_summarize(self): self.calls.append("ai_summarize")

    doc = FakeDoc()
    app.tab_manager.addTab(doc, "fake")
    app.tab_manager.setCurrentWidget(doc)
    for method in (app._play_beeshow, app._export_beeshow_pptx,
                   app._analyze_current_sheet, app._nl_formula,
                   app._play_macro, app._toggle_macro,
                   app._ai_continue, app._ai_polish, app._ai_summarize):
        method()
    assert len(doc.calls) == 9


def test_show_plugin_market(app, monkeypatch):
    import beeoffice.plugins.plugin_market as mod
    called = []
    monkeypatch.setattr(mod, "show_plugin_market", lambda parent: called.append(parent))
    app._show_plugin_market()
    assert called == [app]


def test_run_batch_convert_callbacks(app, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    in_dir = tmp_path / "in"; out_dir = tmp_path / "out"
    in_dir.mkdir(); out_dir.mkdir()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        lambda parent, title: str(in_dir if "输入" in title or "input" in title else out_dir))
    captured = {}
    class FakeAsync:
        @staticmethod
        def run(fn, *args, **kwargs):
            captured["fn"] = fn
            captured["kwargs"] = kwargs
    monkeypatch.setattr(type(app), "AsyncTaskManager", FakeAsync, raising=False)
    import beeoffice.app as app_mod
    monkeypatch.setattr(app_mod, "AsyncTaskManager", FakeAsync)
    infos, warns = [], []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: infos.append(a))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warns.append(a))
    app._run_batch_convert(lambda *a: [], "选择输入", "选择输出", "正在转换")
    assert "on_result" in captured["kwargs"]
    captured["kwargs"]["on_result"]([{"status": "ok", "file": "a.docx"}])
    captured["kwargs"]["on_error"](RuntimeError("bad"))
    assert infos and warns


def test_open_recent_missing_and_supported(app, monkeypatch, tmp_path):
    import beeoffice.ui_dialogs as ui
    errors = []
    monkeypatch.setattr(ui, "show_error", lambda *a, **k: errors.append(a))
    missing = str(tmp_path / "gone.xlsx")
    app.settings.recent_files = [missing]
    app._open_recent(missing)
    assert errors
    assert missing not in app.settings.recent_files

    called = []
    app._open_sheet_file = lambda p: called.append(("sheet", p))
    app._open_docx_file = lambda p: called.append(("docx", p))
    app._open_text_file = lambda p: called.append(("text", p))
    for name, target in [("a.xlsx", "sheet"), ("a.docx", "docx"), ("a.md", "text")]:
        f = tmp_path / name
        f.write_text("x", encoding="utf-8")
        app._open_recent(str(f))
    assert [c[0] for c in called] == ["sheet", "docx", "text"]


def test_onboarding_finished(app):
    app.settings.has_completed_onboarding = False
    app._onboarding_overlay = object()
    app._on_onboarding_finished()
    assert app.settings.has_completed_onboarding is True
    assert app._onboarding_overlay is None


def test_shortcuts_overlay(app):
    app._show_shortcuts_overlay()
    assert app._shortcuts_dlg is not None
    app._close_shortcuts_overlay()
    assert app._shortcuts_dlg is None


def test_autosave_fake_widget(app):
    class Fake(QWidget):
        def __init__(self):
            super().__init__()
            self.saved = 0
        def save(self):
            self.saved += 1
            return True
    fake = Fake()
    app.tab_manager.addTab(fake, "fake")
    app.tab_manager.setCurrentWidget(fake)
    app.tab_manager._tab_initial_content[id(fake)] = "old"
    app._get_widget_content = lambda w: "new"
    app._autosave()
    assert fake.saved == 1


def test_open_sheet_file_async(app, monkeypatch, tmp_path):
    class FakeSheet(QWidget):
        def __init__(self):
            super().__init__()
            self.applied = None
        def _read_sheet_file(self, path):
            return "df"
        def _apply_imported_dataframe(self, df, path):
            self.applied = (df, path)
            return True
    fake = FakeSheet()
    def new_sheet():
        app.tab_manager.addTab(fake, "sheet")
        app.tab_manager.setCurrentWidget(fake)
    monkeypatch.setattr(app, "_new_beesheet", new_sheet)
    captured = {}
    class FakeAsync:
        @staticmethod
        def run(fn, *args, **kwargs):
            captured["fn"] = fn
            captured["args"] = args
            captured["kwargs"] = kwargs
    import beeoffice.app as app_mod
    monkeypatch.setattr(app_mod, "AsyncTaskManager", FakeAsync)
    path = str(tmp_path / "a.xlsx")
    app._open_sheet_file(path)
    assert captured["fn"] == fake._read_sheet_file
    captured["kwargs"]["on_result"]("df")
    assert fake.applied == ("df", path)


def test_open_sheet_file_error(app, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QMessageBox
    class FakeSheet(QWidget):
        def _read_sheet_file(self, path):
            return "df"
        def _apply_imported_dataframe(self, df, path):
            raise RuntimeError("bad")
    fake = FakeSheet()
    def new_sheet():
        app.tab_manager.addTab(fake, "sheet")
        app.tab_manager.setCurrentWidget(fake)
    monkeypatch.setattr(app, "_new_beesheet", new_sheet)
    captured = {}
    class FakeAsync:
        @staticmethod
        def run(fn, *args, **kwargs):
            captured["kwargs"] = kwargs
    import beeoffice.app as app_mod
    monkeypatch.setattr(app_mod, "AsyncTaskManager", FakeAsync)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a))
    app._open_sheet_file(str(tmp_path / "a.xlsx"))
    captured["kwargs"]["on_result"]("df")
    assert warnings


def test_open_docx_file_async(app, monkeypatch, tmp_path):
    class FakeWord(QWidget):
        def __init__(self):
            super().__init__()
            self._content = None
        def content(self):
            return self._content or ""
        def set_content(self, content):
            self._content = content
            self.content = content
        def set_current_file_path(self, path):
            self.path = path
        def _switch_mode(self, mode):
            self.mode = mode
        def _enter_paged_edit(self):
            self.paged = True
        def load_annotations(self, path):
            self.annotations = path
        def _update_save_btn_text(self):
            pass
    fake = FakeWord()
    def new_word():
        app.tab_manager.addTab(fake, "word")
        app.tab_manager.setCurrentWidget(fake)
    monkeypatch.setattr(app, "_new_word_doc", new_word)
    captured = {}
    class FakeAsync:
        @staticmethod
        def run(fn, *args, **kwargs):
            captured["kwargs"] = kwargs
    import beeoffice.app as app_mod
    monkeypatch.setattr(app_mod, "AsyncTaskManager", FakeAsync)
    path = str(tmp_path / "a.docx")
    app._open_docx_file(path)
    captured["kwargs"]["on_result"]("# hi")
    assert fake.content == "# hi"
    assert fake.path == path
    assert fake.mode == "rich_text"
