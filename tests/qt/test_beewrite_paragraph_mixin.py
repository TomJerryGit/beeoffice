"""GUI 覆盖率批次：Beewrite 段落/字符底纹/多级列表。"""
import pytest
from PySide6.QtWidgets import QDialog, QMessageBox

from beeoffice.plugins.beewrite import BeeWriteEditor


@pytest.fixture
def editor(qtbot, monkeypatch):
    ed = BeeWriteEditor()
    qtbot.addWidget(ed)
    ed._switch_mode("rich_text")
    ed.rich_editor.setPlainText("第一段\n第二段")
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    return ed


def test_paragraph_dialog_smoke(editor, monkeypatch):
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)
    editor._show_paragraph_dialog()
    editor._show_char_shade_dialog()


def test_apply_paragraph_format(editor):
    editor._apply_paragraph_format(
        "居中对齐", "正文", "1.5 倍行距", "1.5", "0", "0", "0", "0",
        "无缩进", "0",
    )
    editor._apply_paragraph_format(
        "左对齐", "正文", "固定值", "20", "12", "6", "2", "2",
        "首行缩进", "2", "#FFFF00", "全部边框",
    )


class FakeAction:
    def __init__(self):
        class Sig:
            def connect(self, fn): self.fn = fn
        self.triggered = Sig()


class FakeMenu:
    def __init__(self, *a, **k): pass
    def addAction(self, text): return FakeAction()
    def addSeparator(self): pass
    def addMenu(self, text): return FakeMenu()
    def exec(self, *a, **k): pass


def test_multilist_menu_and_styles(editor, monkeypatch):
    import beeoffice.plugins.beewrite_paragraph_mixin as m
    monkeypatch.setattr(m, "QMenu", FakeMenu)
    editor._show_multilist_menu()
    for style in ("decimal", "paren", "circled", "roman", "upper_alpha", "lower_alpha", "unknown"):
        editor._apply_multilist_style(style)
    editor._multilist_promote()
    editor._multilist_demote()
    editor._multilist_remove()
