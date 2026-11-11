"""GUI 覆盖率批次：TabManager 关闭/分屏/拖放/右键。"""
import os
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox, QPlainTextEdit, QWidget

from beeoffice.tab_manager import TabManager


class FakeParent(QWidget):
    def __init__(self):
        super().__init__()
        self.recent = []
        self._updated = 0
        self.tab_manager = None
    def _open_recent(self, path):
        self.recent.append(path)
    def _update_recent_menu(self):
        self._updated += 1


def make_tm(qtbot, parent=None):
    tm = TabManager(parent)
    qtbot.addWidget(tm)
    if parent is not None:
        parent.tab_manager = tm
    return tm


def test_close_unsaved_yes_no(qtbot, monkeypatch):
    tm = make_tm(qtbot)
    w = QPlainTextEdit("abc")
    tm.addTab(w, "w")
    w.setPlainText("changed")
    tm.setCurrentWidget(w)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    n = tm.count()
    tm._on_tab_close_request(tm.currentIndex())
    assert tm.count() == n
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    tm._on_tab_close_request(tm.currentIndex())
    assert tm.count() == n - 1


def test_close_initial_none(qtbot):
    tm = make_tm(qtbot)
    w = QWidget()
    tm.addTab(w, "container")
    assert tm._tab_initial_content[id(w)] is None
    tm._on_tab_close_request(tm.indexOf(w))
    assert tm.indexOf(w) < 0


def test_close_other_tabs(qtbot):
    tm = make_tm(qtbot)
    keep = QPlainTextEdit("k")
    a = QPlainTextEdit("a")
    b = QPlainTextEdit("b")
    for w, t in [(keep, "keep"), (a, "a"), (b, "b")]:
        tm.addTab(w, t)
    tm._close_other_tabs(tm.indexOf(keep))
    assert tm.widget(0) is keep or tm.count() == 1
    assert tm.indexOf(a) < 0 and tm.indexOf(b) < 0


def test_split_current(qtbot):
    tm = make_tm(qtbot)
    w = QPlainTextEdit("x")
    tm.addTab(w, "w")
    tm.setCurrentWidget(w)
    n = tm.count()
    tm.split_with_current()
    assert tm.count() == n
    assert tm.tabText(tm.currentIndex()) == "分屏"


def test_open_text_file(qtbot, monkeypatch, tmp_path):
    parent = FakeParent()
    class FakeSettings:
        def __init__(self): self.recent = []
        def add_recent_file(self, path): self.recent.append(path)
    parent.settings = FakeSettings()
    qtbot.addWidget(parent)
    tm = make_tm(qtbot, parent)
    f = tmp_path / "a.md"
    f.write_text("hello", encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(f), ""))
    tm.open_file()
    assert tm.count() >= 2
    assert parent.settings.recent == [str(f)]
    # 表格文件委托给主窗口
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(tmp_path / "a.xlsx"), ""))
    tm.open_file()
    assert parent.recent[-1].endswith("a.xlsx")
    # 取消
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    tm.open_file()


class FakeMime:
    def __init__(self, urls=None):
        self._urls = urls or []
    def hasFormat(self, fmt): return False
    def hasUrls(self): return bool(self._urls)
    def urls(self): return self._urls


class FakeUrl:
    def __init__(self, path): self.path = path
    def toLocalFile(self): return self.path


class DragEvent:
    def __init__(self, urls=None):
        self._mime = FakeMime(urls)
        self.accepted = False
    def mimeData(self): return self._mime
    def acceptProposedAction(self): self.accepted = True


def test_drop_urls(qtbot, tmp_path):
    parent = FakeParent()
    class FakeSettings:
        def __init__(self): self.recent = []
        def add_recent_file(self, path): self.recent.append(path)
    parent.settings = FakeSettings()
    qtbot.addWidget(parent)
    tm = make_tm(qtbot, parent)
    f = tmp_path / "a.md"
    ev = DragEvent([FakeUrl(str(f))])
    tm.dropEvent(ev)
    assert ev.accepted and parent.recent == [str(f)]
    # 非 URL 事件由父类处理，这里不构造不完整的 Qt 事件


def test_find_tab_and_changed_title(qtbot):
    parent = FakeParent()
    qtbot.addWidget(parent)
    tm = make_tm(qtbot, parent)
    assert tm._find_tab_by_id(id(tm)) is tm
    assert tm._find_tab_by_id(12345) is None
    tm.setCurrentIndex(0)
    assert "蜜蜂办公" in parent.windowTitle()


class FakeAction:
    def __init__(self, text):
        self.text = text
        self.callback = None
        self.triggered = self
    def connect(self, fn): self.callback = fn
    def trigger(self):
        if self.callback: self.callback()


class FakeMenu:
    def __init__(self, *a, **k): self.actions = []
    def addAction(self, text):
        a = FakeAction(text); self.actions.append(a); return a
    def addSeparator(self): pass
    def exec(self, *a, **k): pass


def test_context_menu(qtbot, monkeypatch):
    import beeoffice.tab_manager as mod
    tm = make_tm(qtbot)
    w = QPlainTextEdit("x")
    tm.addTab(w, "w")
    monkeypatch.setattr(mod, "QMenu", FakeMenu)
    rect = tm.tabBar().tabRect(tm.indexOf(w))
    tm._show_tab_context_menu(rect.center())
    # 无标签位置
    tm._show_tab_context_menu(QPoint(-100, -100))
