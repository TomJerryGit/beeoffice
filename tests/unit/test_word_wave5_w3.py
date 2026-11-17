"""Wave5 W3：Word 封面/页面背景。"""
from zipfile import ZipFile
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QInputDialog
from beeoffice.plugins.beewrite import BeeWriteEditor


def make_editor(qtbot):
    e = BeeWriteEditor()
    qtbot.addWidget(e)
    e.show()
    e._edit_mode = "rich_text"
    e.rich_editor.setPlainText("正文")
    return e


def test_insert_cover(qtbot, monkeypatch):
    e = make_editor(qtbot)
    values = iter(["XX 公司年度报告", "2026 年度", "综合管理部"])
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: (next(values), True)))
    e._insert_cover_page()
    text = e.rich_editor.toPlainText()
    assert "XX 公司年度报告" in text
    assert text.find("XX 公司年度报告") < text.find("正文")


def test_page_background_docx(qtbot, tmp_path, monkeypatch):
    e = make_editor(qtbot)
    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor("#FFF3E0")))
    e._set_page_background()
    assert e._page_background == "#fff3e0"
    out = tmp_path / "bg.docx"
    assert e._write_docx(str(out))
    with ZipFile(out) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    assert 'w:background' in xml
    assert "FFF3E0" in xml
