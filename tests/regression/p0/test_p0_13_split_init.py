# tests/test_p0_regression/test_p0_13_split_init.py
"""P0-13 回归：分屏容器不触发未保存提示"""
from PySide6.QtWidgets import QWidget
import pytest


def test_split_tab_marked_none(qtbot):
    from beeoffice.tab_manager import TabManager
    tm = TabManager()
    qtbot.addWidget(tm)
    w = QWidget()
    tm.addTab(w, "分屏")
    assert tm._tab_initial_content[id(w)] is None


def test_split_tab_close_no_prompt(qtbot, monkeypatch):
    from beeoffice.tab_manager import TabManager
    from PySide6.QtWidgets import QMessageBox

    tm = TabManager()
    qtbot.addWidget(tm)
    w = QWidget()
    tm.addTab(w, "分屏")
    idx = tm.indexOf(w)

    call_count = {"n": 0}
    def fake_question(*a, **k):
        call_count["n"] += 1
        return QMessageBox.Yes
    monkeypatch.setattr(QMessageBox, "question", staticmethod(fake_question))

    tm._on_tab_close_request(idx)
    assert call_count["n"] == 0
