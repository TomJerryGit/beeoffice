# tests/test_p0_regression/test_p0_12_close_others.py
"""P0-12 回归：_close_other_tabs 不误关保留标签"""
from PySide6.QtWidgets import QPlainTextEdit


def test_close_others_keeps_target(qtbot, monkeypatch):
    from beeoffice.tab_manager import TabManager
    tm = TabManager()
    qtbot.addWidget(tm)

    w1 = QPlainTextEdit()
    w2 = QPlainTextEdit()
    w3 = QPlainTextEdit()
    tm.addTab(w1, "1")
    tm.addTab(w2, "2")
    tm.addTab(w3, "3")

    target = w2
    target_index = tm.indexOf(target)

    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.Yes)
    )

    tm._close_other_tabs(target_index)

    assert tm.count() == 1
    assert tm.widget(0) is target
