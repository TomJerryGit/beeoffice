"""GUI 覆盖率批次：Beewrite 超链接/图片/公式/文本框插入。"""
import pytest
from PIL import Image
from PySide6.QtWidgets import QDialog, QMessageBox

from beeoffice.plugins.beewrite import BeeWriteEditor


@pytest.fixture
def editor(qtbot, monkeypatch):
    ed = BeeWriteEditor()
    qtbot.addWidget(ed)
    ed._switch_mode("rich_text")
    ed.rich_editor.setPlainText("hello world")
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    return ed


class FakeDialog:
    text = "文本"
    url = "https://example.com"
    result_path = ""
    def __init__(self, *a, **k): pass
    def exec(self): return QDialog.Accepted
    def get_text(self): return self.text
    def get_url(self): return self.url
    def get_result_path(self): return self.result_path
    def get_config(self): return {"text": "x"}


def test_insert_hyperlink_markdown(editor, monkeypatch):
    import beeoffice.plugins.beewrite_link_mixin as m
    editor._switch_mode("markdown")
    monkeypatch.setattr(m, "HyperlinkDialog", FakeDialog)
    editor._insert_hyperlink()
    assert "https://example.com" in editor.markdown_editor.toPlainText()


def test_insert_hyperlink_rich(editor, monkeypatch):
    import beeoffice.plugins.beewrite_link_mixin as m
    monkeypatch.setattr(m, "HyperlinkDialog", FakeDialog)
    editor._insert_hyperlink()
    assert "文本" in editor.rich_editor.toPlainText()


def test_insert_hyperlink_cancel(editor, monkeypatch):
    import beeoffice.plugins.beewrite_link_mixin as m
    class Reject(FakeDialog):
        def exec(self): return QDialog.Rejected
    monkeypatch.setattr(m, "HyperlinkDialog", Reject)
    before = editor.rich_editor.toPlainText()
    editor._insert_hyperlink()
    assert editor.rich_editor.toPlainText() == before


def test_insert_image(editor, monkeypatch, tmp_path):
    import beeoffice.plugins.beewrite_link_mixin as m
    img = tmp_path / "a.png"
    Image.new("RGB", (800, 600), "blue").save(img)
    class ImgDlg(FakeDialog):
        result_path = str(img)
    monkeypatch.setattr(m, "ImageEditorDialog", ImgDlg)
    editor._insert_image()
    assert editor._count_document_images() >= 1


def test_insert_formula(editor, monkeypatch, tmp_path):
    import beeoffice.plugins.beewrite_link_mixin as m
    img = tmp_path / "f.png"
    Image.new("RGB", (50, 200), "white").save(img)
    class FmtDlg(FakeDialog):
        result_path = str(img)
    monkeypatch.setattr(m, "FormulaDialog", FmtDlg)
    editor._insert_formula()
    assert editor._count_document_images() >= 1


def test_insert_textbox(editor, monkeypatch):
    import beeoffice.plugins.beewrite_link_mixin as m
    calls = []
    monkeypatch.setattr(m, "TextBoxDialog", FakeDialog)
    monkeypatch.setattr(m, "insert_textbox", lambda ed, cfg: calls.append(cfg))
    editor._insert_textbox()
    assert calls == [{"text": "x"}]


def test_insert_non_rich_info(editor, monkeypatch):
    import beeoffice.plugins.beewrite_link_mixin as m
    calls = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: calls.append(a))
    editor._switch_mode("markdown")
    editor._insert_image()
    editor._insert_formula()
    editor._insert_textbox()
    assert len(calls) == 3
