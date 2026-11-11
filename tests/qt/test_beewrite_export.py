"""BeeWrite 导出补测：MD/DOCX、图片路径、模板。"""
from pathlib import Path

import pytest
from PySide6.QtGui import QTextCursor, QTextImageFormat
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from beeoffice.plugins.beewrite import BeeWriteEditor


@pytest.fixture
def writer(qtbot, monkeypatch, tmp_path):
    ed = BeeWriteEditor()
    qtbot.addWidget(ed)
    ed._switch_mode("rich_text")
    ed.rich_editor.setHtml(
        '<h1>标题</h1><p>正文</p>'
        '<table border="1"><tr><td>a</td><td>b</td></tr></table>'
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    ed._current_file_path = str(tmp_path / "doc.docx")
    return ed


def test_write_md_and_docx(writer, tmp_path):
    md = tmp_path / "a.md"
    assert writer._write_md(str(md)) is True
    assert md.exists() and "标题" in md.read_text(encoding="utf-8")
    docx = tmp_path / "a.docx"
    assert writer._write_docx(str(docx)) is True
    assert docx.exists() and docx.stat().st_size > 0


def test_export_rich_docx(writer, tmp_path, monkeypatch):
    target = tmp_path / "out.docx"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), "")
    )
    writer.export_rich_docx()
    assert target.exists() and target.stat().st_size > 0


def test_image_path_resolution(writer, tmp_path):
    img = tmp_path / "p.png"
    img.write_bytes(b"x")
    resolved, tried = writer._resolve_image_path_for_export(str(img))
    assert Path(resolved) == img
    # 相对路径：基于 _current_file_path 目录
    rel = writer._resolve_image_path_for_export("p.png")
    assert Path(rel[0]) == img
    missing = tmp_path / "missing.png"
    resolved2, tried2 = writer._resolve_image_path_for_export(str(missing))
    assert resolved2 is None
    assert tried2


def test_count_images(writer, tmp_path):
    img = tmp_path / "p.png"
    img.write_bytes(b"x")
    cursor = QTextCursor(writer.rich_editor.document())
    cursor.movePosition(QTextCursor.End)
    fmt = QTextImageFormat()
    fmt.setName(str(img))
    fmt.setWidth(10)
    fmt.setHeight(10)
    cursor.insertImage(fmt)
    assert writer._count_document_images() >= 1


def test_save_as_template(writer, monkeypatch):
    called = []
    class FakeTM:
        def save_as_template(self, name, content):
            called.append((name, content))
            return True
    import beeoffice.resources.template_manager as tm_mod
    monkeypatch.setattr(tm_mod, "TemplateManager", FakeTM)
    monkeypatch.setattr(
        QInputDialog, "getText", lambda *a, **k: ("我的模板", True)
    )
    writer.save_as_template()
    assert called and called[0][0] == "我的模板"


def test_save_dispatch_and_cancel(writer, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    # 当前 .md 直接写
    md = tmp_path / "cur.md"
    writer._doc_kind = "markdown"
    writer._current_file_path = str(md)
    assert writer.save() is True and md.exists()
    # 当前 .docx 直接写
    docx = tmp_path / "cur.docx"
    writer._doc_kind = "word"
    writer._current_file_path = str(docx)
    assert writer.save() is True and docx.exists()
    # 取消另存
    writer._current_file_path = None
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    assert writer._save_as_md() is False
    assert writer._save_as_docx() is False


def test_save_extension_added(writer, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    writer._current_file_path = None
    target = tmp_path / "noext"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    assert writer._save_as_md() is True
    assert (tmp_path / "noext.md").exists()
    target2 = tmp_path / "noext2"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target2), ""))
    writer._current_file_path = None
    assert writer._save_as_docx() is True
    assert (tmp_path / "noext2.docx").exists()


def test_export_pdf_branches(writer, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    import beeoffice.plugins.bee_export as be
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    writer.export_pdf()  # 取消
    target = tmp_path / "out.pdf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    monkeypatch.setattr(be, "export_to_pdf", lambda content, path: True)
    writer.export_pdf()
    monkeypatch.setattr(be, "export_to_pdf", lambda content, path: False)
    writer.export_pdf()


def test_export_docx_non_rich(writer, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    import beeoffice.plugins.bee_export as be
    writer._switch_mode("markdown")
    target = tmp_path / "out.docx"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    monkeypatch.setattr(be, "export_to_docx", lambda content, path: True)
    writer.export_docx()
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    writer.export_docx()


def test_open_file_externally(writer, monkeypatch):
    import beeoffice.plugins.beewrite_export_mixin as m
    called = []
    monkeypatch.setattr(m.os, "startfile", lambda p: called.append(p), raising=False)
    writer._open_file_externally("C:/x.docx")


def test_rich_docx_table_image_header_footer(writer, tmp_path):
    from PIL import Image
    from PySide6.QtGui import QTextCursor, QTextImageFormat
    img = tmp_path / "p.png"
    Image.new("RGB", (80, 60), "red").save(img)
    writer.rich_editor.setHtml(
        '<h2>标题</h2><table border="1"><tr><td>a</td><td>b</td></tr>'
        '<tr><td>1</td><td>2</td></tr></table>'
    )
    cursor = QTextCursor(writer.rich_editor.document())
    cursor.movePosition(QTextCursor.End)
    fmt = QTextImageFormat()
    fmt.setName(str(img))
    fmt.setWidth(20)
    fmt.setHeight(15)
    cursor.insertImage(fmt)
    writer.rich_editor.setTextCursor(cursor)
    writer._header_text = "页眉"
    writer._footer_text = "页脚"
    writer._page_settings["orientation"] = "landscape"
    out = tmp_path / "rich.docx"
    assert writer._write_docx(str(out)) is True
    assert out.exists() and out.stat().st_size > 0
    from docx import Document
    doc = Document(str(out))
    assert "页眉" in doc.sections[0].header.paragraphs[0].text
    assert "页脚" in doc.sections[0].footer.paragraphs[0].text
