# tests/qt/test_tab_manager_extra.py
"""
TabManager 补充测试：未保存标记 / 重命名 / 复制路径 / 初始内容
覆盖原 test_tab_manager.py 未覆盖的路径。
"""
from PySide6.QtWidgets import QPlainTextEdit, QWidget, QApplication


class TestUnsavedMark:
    def test_mark_unsaved_adds_dot(self, qtbot):
        from beeoffice.tab_manager import TabManager
        tm = TabManager()
        qtbot.addWidget(tm)
        w = QPlainTextEdit()
        tm.addTab(w, "test")
        tm._mark_unsaved(w)
        idx = tm.indexOf(w)
        assert tm.tabText(idx).startswith("● ")

    def test_mark_saved_removes_dot(self, qtbot):
        from beeoffice.tab_manager import TabManager
        tm = TabManager()
        qtbot.addWidget(tm)
        w = QPlainTextEdit()
        tm.addTab(w, "test")
        tm._mark_unsaved(w)
        tm._mark_saved(w)
        idx = tm.indexOf(w)
        assert not tm.tabText(idx).startswith("● ")

    def test_mark_saved_idempotent(self, qtbot):
        from beeoffice.tab_manager import TabManager
        tm = TabManager()
        qtbot.addWidget(tm)
        w = QPlainTextEdit()
        tm.addTab(w, "test")
        tm._mark_saved(w)
        tm._mark_saved(w)
        idx = tm.indexOf(w)
        assert tm.tabText(idx) == "test"


class TestRenameTab:
    def test_rename_keeps_unsaved_prefix(self, qtbot, monkeypatch):
        from beeoffice.tab_manager import TabManager
        from PySide6.QtWidgets import QInputDialog

        tm = TabManager()
        qtbot.addWidget(tm)
        w = QPlainTextEdit()
        tm.addTab(w, "old")
        tm._mark_unsaved(w)

        monkeypatch.setattr(
            QInputDialog, "getText",
            staticmethod(lambda *a, **k: ("new", True)),
        )
        idx = tm.indexOf(w)
        tm._rename_tab(idx)

        text = tm.tabText(idx)
        assert text.startswith("● ")
        assert "new" in text


class TestCopyFilePath:
    def test_copy_path_to_clipboard(self, qtbot, tmp_path):
        from beeoffice.tab_manager import TabManager
        tm = TabManager()
        qtbot.addWidget(tm)
        w = QPlainTextEdit()
        tm.addTab(w, "doc")
        path = str(tmp_path / "doc.md")
        tm.set_tab_file_path(w, path)
        idx = tm.indexOf(w)
        tm._copy_file_path(idx)
        assert QApplication.clipboard().text() == path

    def test_copy_path_no_path(self, qtbot):
        from beeoffice.tab_manager import TabManager
        tm = TabManager()
        qtbot.addWidget(tm)
        w = QPlainTextEdit()
        tm.addTab(w, "no-path")
        before = QApplication.clipboard().text()
        idx = tm.indexOf(w)
        tm._copy_file_path(idx)
        after = QApplication.clipboard().text()
        assert before == after


class TestInitialContent:
    def test_qplaintextedit_records_content(self, qtbot):
        from beeoffice.tab_manager import TabManager
        tm = TabManager()
        qtbot.addWidget(tm)
        w = QPlainTextEdit()
        w.setPlainText("hello")
        tm.addTab(w, "t")
        assert tm._tab_initial_content[id(w)] == "hello"

    def test_qwidget_marked_none(self, qtbot):
        from beeoffice.tab_manager import TabManager
        tm = TabManager()
        qtbot.addWidget(tm)
        w = QWidget()
        tm.addTab(w, "t")
        assert tm._tab_initial_content[id(w)] is None
