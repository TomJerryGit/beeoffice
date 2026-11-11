"""GUI 覆盖率批次：BeeWrite/BeeSheet 插件命令入口。"""
import pytest
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from beeoffice.plugins.beewrite_plugin import BeeWritePlugin
from beeoffice.plugins.beesheet_plugin import BeeSheetPlugin


class FakeTabManager:
    def __init__(self):
        self.tabs = []
        self.current = None
    def addTab(self, w, title):
        self.tabs.append((w, title)); self.current = w
    def setCurrentWidget(self, w): self.current = w
    def currentWidget(self): return self.current
    def set_tab_file_path(self, w, path): self.path = path


class FakeParent(QWidget):
    def __init__(self):
        super().__init__()
        self.tab_manager = FakeTabManager()
        self.status = []
    def set_global_status(self, text, timeout=0): self.status.append(text)
    def _add_file_watch(self, path): self.watched = path


class FakePalette:
    def __init__(self): self.commands = []
    def register_command(self, title, desc, fn): self.commands.append((title, desc, fn))


@pytest.fixture
def parent(qtbot):
    p = FakeParent(); qtbot.addWidget(p); return p


def test_beewrite_plugin_basic(parent, monkeypatch):
    p = BeeWritePlugin(parent)
    pal = FakePalette()
    p.register_commands(pal)
    assert len(pal.commands) == 9
    ed = p.new_document()
    assert ed is p._current_editor()
    assert p.new_word_document() is not None
    # 导出入口
    class FakeEd:
        def export_docx(self): self.docx = True
        def export_pdf(self): self.pdf = True
        def export_html(self): self.html = True
    f = FakeEd(); parent.tab_manager.setCurrentWidget(f)
    # _current_editor 只认 BeeWriteEditor，导出走 warn
    calls = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: calls.append(a))
    p.export_docx(); p.export_pdf(); p.export_html()
    assert len(calls) == 3


def test_beewrite_plugin_export_real_editor(parent, monkeypatch):
    p = BeeWritePlugin(parent)
    ed = p.new_document()
    calls = []
    monkeypatch.setattr(ed, "export_docx", lambda: calls.append("docx"))
    monkeypatch.setattr(ed, "export_pdf", lambda: calls.append("pdf"))
    p.export_docx(); p.export_pdf()
    assert calls == ["docx", "pdf"]


def test_beesheet_plugin_basic(parent, monkeypatch):
    p = BeeSheetPlugin(parent)
    pal = FakePalette()
    p.register_commands(pal)
    assert len(pal.commands) == 9
    view = p.new_sheet()
    assert view is p._current_view()
    # 导入
    target = "/tmp/a.csv"
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (target, ""))
    called = []
    monkeypatch.setattr(view, "_import_file_from_path", lambda path: called.append(path))
    p.import_data()
    assert called == [target]
    # 导出
    monkeypatch.setattr(view, "_export_xlsx", lambda: called.append("xlsx"))
    p.export_xlsx()
    assert "xlsx" in called


def test_beesheet_plugin_missing_view(parent, monkeypatch):
    p = BeeSheetPlugin(parent)
    calls = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: calls.append(a))
    p.export_xlsx()
    assert calls
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    p.import_data()  # 无标签 -> 新建后取消


def test_beesheet_plugin_command_dispatch(parent, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    p = BeeSheetPlugin(parent)
    view = p.new_sheet()
    called = []
    monkeypatch.setattr(p, "_generate_chart_fallback", lambda v: called.append("chart"))
    monkeypatch.setattr(view, "_analyze_data", lambda: called.append("analyze"), raising=False)
    monkeypatch.setattr(view, "_nl_to_formula", lambda: called.append("nl"), raising=False)
    monkeypatch.setattr(view, "_toggle_macro_recording", lambda: called.append("record"), raising=False)
    monkeypatch.setattr(view, "_play_macro", lambda: called.append("play"), raising=False)
    p.generate_chart(); p.analyze_data(); p.nl_to_formula()
    p.toggle_macro_recording(); p.play_macro()
    assert called == ["chart", "analyze", "nl", "record", "play"]


def test_beesheet_plugin_clean_data(parent, monkeypatch):
    import pandas as pd
    from PySide6.QtWidgets import QMessageBox
    p = BeeSheetPlugin(parent)
    view = p.new_sheet()
    view.model.set_full_dataframe(pd.DataFrame({"A": [1, 1, 2]}))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    p.clean_data()
    assert len(view.model.df) == 2


def test_beewrite_plugin_toc_ai(parent, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    p = BeeWritePlugin(parent)
    ed = p.new_document()
    called = []
    monkeypatch.setattr(ed, "_insert_toc", lambda: called.append("toc"))
    monkeypatch.setattr(ed, "_ai_continue", lambda: called.append("continue"))
    monkeypatch.setattr(ed, "_ai_polish", lambda: called.append("polish"))
    monkeypatch.setattr(ed, "_ai_summarize", lambda: called.append("summary"))
    p.generate_toc(); p.ai_continue(); p.ai_polish(); p.ai_summarize()
    assert called == ["toc", "continue", "polish", "summary"]


def test_beewrite_plugin_no_editor(parent, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    calls = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: calls.append(a))
    p = BeeWritePlugin(parent)
    p.export_docx(); p.generate_toc(); p.ai_continue(); p.ai_polish(); p.ai_summarize()
    assert len(calls) == 5
