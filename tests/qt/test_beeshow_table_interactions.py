"""BeeShow 表格交互补测。"""
import pytest
from PySide6.QtWidgets import QDialog, QMessageBox, QPlainTextEdit

from beeoffice.plugins.beeshow_table_mixin import TableMixin


class FakeShow(TableMixin):
    def __init__(self):
        self._editor = QPlainTextEdit()
        self._slides_md = ["# 第一页\n正文", "# 第二页"]
        self._current_slide = 0
        self.status = []
        self.preview_updates = 0
    def _set_status(self, text, ms=0):
        self.status.append(text)
    def _update_preview(self):
        self.preview_updates += 1


@pytest.fixture
def show(qtbot, monkeypatch):
    obj = FakeShow()
    qtbot.addWidget(obj._editor)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    return obj


def test_extract_table(show):
    show._slides_md[0] = "# 标题\n| a | b |\n|---|---|\n| 1 | 2 |"
    assert show._extract_current_table() == [["a", "b"], ["1", "2"]]
    show._slides_md[0] = "no table"
    assert show._extract_current_table() is None


def test_insert_table_md(show):
    show._editor.setPlainText("# 第一页\n正文\n---\n# 第二页")
    show._insert_table_md("| x | y |\n|---|---|\n| 1 | 2 |")
    text = show._editor.toPlainText()
    assert "| x | y |" in text
    assert "| 1 | 2 |" in text
    assert show.preview_updates == 1


def test_replace_current_table(show):
    show._slides_md[0] = "# 标题\n| a | b |\n|---|---|\n| 1 | 2 |\n尾部"
    show._replace_current_table("| c | d |\n|---|---|\n| 3 | 4 |")
    text = show._editor.toPlainText()
    assert "| c | d |" in text
    assert "| a | b |" not in text


def test_show_table_editor_no_slides(show, monkeypatch):
    show._slides_md = []
    calls = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: calls.append(a))
    show._show_table_editor()
    assert calls


def test_show_table_editor_accepted(show, monkeypatch):
    import beeoffice.plugins.beeshow_table_mixin as m
    class FakeDlg:
        def __init__(self, rows, parent): pass
        def exec(self): return QDialog.Accepted
        def get_markdown_table(self): return "| n | m |\n|---|---|\n| 5 | 6 |"
    monkeypatch.setattr(m, "TableEditorDialog", FakeDlg)
    show._show_table_editor()
    assert "| n | m |" in show._editor.toPlainText()


def test_edit_current_table_no_table(show, monkeypatch):
    calls = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: calls.append(a))
    show._edit_current_table()
    assert calls


def test_edit_current_table_accepted(show, monkeypatch):
    import beeoffice.plugins.beeshow_table_mixin as m
    show._slides_md[0] = "| a |\n|---|\n| 1 |"
    class FakeDlg:
        def __init__(self, rows, parent): pass
        def exec(self): return QDialog.Accepted
        def get_markdown_table(self): return "| z |\n|---|\n| 9 |"
    monkeypatch.setattr(m, "TableEditorDialog", FakeDlg)
    show._edit_current_table()
    assert "| z |" in show._editor.toPlainText()
