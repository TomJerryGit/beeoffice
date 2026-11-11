"""BeeShow 评论 Mixin 补测。"""
import pytest
from PySide6.QtWidgets import QInputDialog, QMessageBox, QPlainTextEdit, QWidget

from beeoffice.plugins.beeshow_comment_mixin import CommentMixin


class FakeShow(CommentMixin, QWidget):
    def __init__(self):
        QWidget.__init__(self)
        self._init_comments_state()
        self._editor = QPlainTextEdit()
        self._slides_html = ["# 一", "# 二"]
        self._slide_titles = ["一", "二"]
        self._current_slide = 0
        self.status = []
    def _set_status(self, text, ms=0): self.status.append(text)
    def _update_preview(self): pass
    def _refresh_comment_panel(self): pass


@pytest.fixture
def show(qtbot, monkeypatch):
    obj = FakeShow()
    qtbot.addWidget(obj)
    qtbot.addWidget(obj._editor)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    return obj


def test_counts_and_find(show):
    show._slide_comments = {0: [{"id": 1, "resolved": False}], 1: [{"id": 2, "resolved": True}]}
    assert show._get_comment_count() == 2
    assert show._get_unresolved_comment_count() == 1
    assert show._find_comment(2)[1] == 1
    assert show._find_comment(99) == (None, None)
    assert show._find_comment_page(1) == 0


def test_sync_and_load(show):
    show._editor.setPlainText("# 一\n---\n# 二")
    show._slide_comments = {0: [{"id": 1, "author": "a", "text": "c", "time": "t", "resolved": False}]}
    show._sync_comments_to_editor()
    text = show._editor.toPlainText()
    assert "<!-- comments:" in text
    show._load_comments_from_editor(text)
    assert show._slide_comments[0][0]["text"] == "c"
    assert show._comment_next_id == 2


def test_load_bad_json(show):
    show._load_comments_from_editor("# x\n<!-- comments: not-json -->")
    assert show._slide_comments == {}


def test_add_comment(show, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getMultiLineText", lambda *a, **k: ("评论内容", True))
    show._add_comment()
    assert show._slide_comments[0][0]["text"] == "评论内容"
    assert "comments:" in show._editor.toPlainText()


def test_add_comment_cancel(show, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getMultiLineText", lambda *a, **k: ("", False))
    show._add_comment()
    assert show._slide_comments == {}


def test_edit_delete_resolve(show, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    show._slide_comments = {0: [{"id": 1, "author": "a", "text": "old", "time": "t", "resolved": False}]}
    show._comment_next_id = 2
    monkeypatch.setattr(QInputDialog, "getMultiLineText", lambda *a, **k: ("new", True))
    show._edit_comment(1)
    assert show._slide_comments[0][0]["text"] == "new"
    show._toggle_comment_resolved(1)
    assert show._slide_comments[0][0]["resolved"] is True
    show._delete_comment(1)
    assert show._slide_comments == {}


def test_sync_comments_to_editor_empty(show):
    show._slide_comments = {}
    show._editor.setPlainText("# 一\n---\n# 二")
    show._sync_comments_to_editor()
    assert "comments:" not in show._editor.toPlainText()
