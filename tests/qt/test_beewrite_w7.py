"""Wave 2 W7：脚注/尾注/题注/交叉引用/目录更新/字数统计。"""
from PySide6.QtWidgets import QInputDialog, QMessageBox

from beeoffice.plugins.beewrite import BeeWriteEditor


def make_editor(qtbot):
    e = BeeWriteEditor()
    qtbot.addWidget(e)
    e.show()
    e._edit_mode = "rich_text"
    return e


def test_footnote_and_endnote(qtbot, monkeypatch):
    e = make_editor(qtbot)
    e.rich_editor.setPlainText("正文")
    answers = iter(["脚注内容", "尾注内容"])
    monkeypatch.setattr(
        QInputDialog, "getMultiLineText",
        staticmethod(lambda *a, **k: (next(answers), True)),
    )
    e._insert_footnote()
    e._insert_endnote()
    text = e.rich_editor.toPlainText()
    assert "[1]" in text
    assert "[1]" in text
    assert e._footnotes == ["脚注内容"]
    assert e._endnotes == ["尾注内容"]


def test_caption_and_cross_reference(qtbot, monkeypatch):
    e = make_editor(qtbot)
    e.rich_editor.setPlainText("正文")
    monkeypatch.setattr(
        QInputDialog, "getItem",
        staticmethod(lambda *a, **k: ("图", True)),
    )
    monkeypatch.setattr(
        QInputDialog, "getText",
        staticmethod(lambda *a, **k: ("架构图", True)),
    )
    e._insert_caption()
    assert "图 1：架构图" in e.rich_editor.toPlainText()
    labels = ["图 1：架构图"]
    monkeypatch.setattr(
        QInputDialog, "getItem",
        staticmethod(lambda *a, **k: (labels[0], True)),
    )
    e._insert_cross_reference()
    assert "图 1" in e.rich_editor.toPlainText()


def test_update_toc(qtbot):
    e = make_editor(qtbot)
    cursor = e.rich_editor.textCursor()
    cursor.insertText("第一章")
    bf = cursor.blockFormat()
    bf.setHeadingLevel(1)
    cursor.setBlockFormat(bf)
    cursor.insertBlock()
    cursor.insertText("正文")
    e._update_toc()
    text = e.rich_editor.toPlainText()
    assert "目录" in text
    assert "第一章" in text


def test_word_count_dialog(qtbot, monkeypatch):
    e = make_editor(qtbot)
    e.rich_editor.setPlainText("你好 world 测试")
    captured = []
    monkeypatch.setattr(
        QMessageBox, "information",
        staticmethod(lambda *a, **k: captured.append(a)),
    )
    e._show_word_count_dialog()
    assert captured
    assert "字数" in str(captured[0])
