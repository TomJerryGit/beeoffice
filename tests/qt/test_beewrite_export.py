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
