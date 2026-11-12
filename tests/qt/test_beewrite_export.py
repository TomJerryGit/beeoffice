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


def test_image_path_and_picture_branches(writer, tmp_path):
    from PySide6.QtGui import QTextImageFormat
    # qrc / 空名 / 缺失
    writer._insert_picture_to_para(None, QTextImageFormat())
    fmt = QTextImageFormat(); fmt.setName("qrc:/x.png")
    writer._insert_picture_to_para(None, fmt)
    fmt2 = QTextImageFormat(); fmt2.setName(str(tmp_path / "missing.png"))
    writer._insert_picture_to_para(None, fmt2)
    # 有效图片
    from PIL import Image
    img = tmp_path / "a.png"; Image.new("RGB", (100, 50), "red").save(img)
    from docx import Document
    doc = Document()
    para = doc.add_paragraph()
    fmt3 = QTextImageFormat(); fmt3.setName(str(img)); fmt3.setWidth(40); fmt3.setHeight(20)
    writer._insert_picture_to_para(para, fmt3)
    fmt4 = QTextImageFormat(); fmt4.setName(str(img)); fmt4.setWidth(40)
    writer._insert_picture_to_para(para, fmt4)
    assert len(para.runs) >= 2


def test_header_footer_direct(writer):
    from docx import Document
    assert writer._apply_header_footer(Document()) is False
    writer._header_text = "H"
    writer._footer_text = "F"
    doc = Document()
    assert writer._apply_header_footer(doc) is True
    assert doc.sections[0].header.paragraphs[0].text == "H"
    assert doc.sections[0].footer.paragraphs[0].text == "F"


def test_table_with_image_export(writer, tmp_path):
    from PIL import Image
    from PySide6.QtGui import QTextCursor, QTextImageFormat
    img = tmp_path / "cell.png"; Image.new("RGB", (30, 30), "blue").save(img)
    writer.rich_editor.clear()
    cursor = writer.rich_editor.textCursor()
    table = cursor.insertTable(2, 2)
    table.cellAt(0, 0).firstCursorPosition().insertText("A")
    table.cellAt(0, 1).firstCursorPosition().insertText("B")
    c = table.cellAt(1, 0).firstCursorPosition()
    fmt = QTextImageFormat(); fmt.setName(str(img)); fmt.setWidth(20); fmt.setHeight(20)
    c.insertImage(fmt)
    out = tmp_path / "table_img.docx"
    assert writer._write_docx(str(out)) is True
    assert out.exists()


def test_image_path_exceptions_and_bad_picture(writer, tmp_path):
    import beeoffice.plugins.beewrite_export_mixin as m
    # 当前文件路径属性异常
    class Bad:
        @property
        def _current_file_path(self): raise RuntimeError("bad")
        def get_current_file_dir(self): raise RuntimeError("dir")
        _current_file_dir = None
    b = Bad()
    assert m.ExportMixin._resolve_image_path_for_export(b, "x.png")[0] is None
    # 坏图片
    bad = tmp_path / "bad.png"; bad.write_bytes(b"not image")
    from docx import Document
    doc = Document(); para = doc.add_paragraph()
    from PySide6.QtGui import QTextImageFormat
    fmt = QTextImageFormat(); fmt.setName(str(bad))
    writer._insert_picture_to_para(para, fmt)


def test_export_error_paths(writer, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox
    import beeoffice.plugins.bee_export as be
    warns = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warns.append(a))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.Yes)
    # PDF 异常
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(tmp_path / "x.pdf"), ""))
    monkeypatch.setattr(be, "export_to_pdf", lambda content, path: (_ for _ in ()).throw(RuntimeError("pdf")))
    writer.export_pdf()
    # DOCX 非富文本异常
    writer._switch_mode("markdown")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(tmp_path / "x.docx"), ""))
    monkeypatch.setattr(be, "export_to_docx", lambda content, path: (_ for _ in ()).throw(RuntimeError("docx")))
    writer.export_docx()
    # 富文本导出异常 + 取消
    writer._switch_mode("rich_text")
    monkeypatch.setattr(writer, "_rich_to_docx", lambda path: (_ for _ in ()).throw(RuntimeError("rich")))
    writer.export_rich_docx()
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    writer.export_rich_docx()
    assert warns


def test_save_template_error(writer, monkeypatch):
    from PySide6.QtWidgets import QInputDialog, QMessageBox
    import beeoffice.resources.template_manager as tm
    warns = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warns.append(a))
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("", False))
    writer.save_as_template()
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("n", True))
    class TM:
        def save_as_template(self, n, c): return False
    monkeypatch.setattr(tm, "TemplateManager", TM)
    writer.save_as_template()
    class Bad:
        def __init__(self): raise RuntimeError("bad")
    monkeypatch.setattr(tm, "TemplateManager", Bad)
    writer.save_as_template()
    assert len(warns) == 2


def test_write_md_and_tab_title_errors(writer, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    warns = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warns.append(a))
    monkeypatch.setattr(writer, "content", lambda: (_ for _ in ()).throw(RuntimeError("content")))
    assert writer._write_md("C:/x.md") is False
    class BadParent:
        def sync_tab_title(self, *a): raise RuntimeError("sync")
        def notify_self_save(self, *a): raise RuntimeError("notify")
    monkeypatch.setattr(writer, "_find_main_window", lambda: BadParent())
    writer._update_tab_title("C:/x.md")
    writer._notify_self_save("C:/x.md")
    assert warns


def test_header_footer_exception(writer):
    class BadDoc:
        class Sec:
            class Header:
                @property
                def paragraphs(self): raise RuntimeError("header")
            header = Header()
            footer = Header()
        sections = [Sec()]
    writer._header_text = "H"
    assert writer._apply_header_footer(BadDoc()) is False


def test_image_path_current_dir_and_bad_objects(writer, tmp_path):
    from PySide6.QtGui import QTextBlockFormat, QTextCharFormat, QTextImageFormat
    from docx import Document
    img = tmp_path / "b.png"
    from PIL import Image
    Image.new("RGB", (10, 10), "red").save(img)
    writer._current_file_path = None
    writer.get_current_file_dir = lambda: tmp_path
    assert Path(writer._resolve_image_path_for_export("b.png")[0]) == img
    class BadImage:
        def name(self): raise RuntimeError("bad")
    writer._insert_picture_to_para(None, BadImage())
    class BadPara:
        def __getattr__(self, name): raise RuntimeError("bad")
    class BadDoc:
        def add_table(self, *a): raise RuntimeError("table")
    class BadTable:
        def rows(self): raise RuntimeError("rows")


def test_open_externally_non_windows(writer, monkeypatch):
    import beeoffice.plugins.beewrite_export_mixin as m
    calls = []
    monkeypatch.setattr(m.sys, "platform", "linux")
    monkeypatch.setattr(m.subprocess, "run", lambda *a, **k: calls.append(a))
    writer._open_file_externally("x.md")
    assert calls
    monkeypatch.setattr(m.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
    writer._open_file_externally("x.md")


def test_block_and_char_format_appliers(writer):
    from PySide6.QtGui import QColor, QFont, QTextBlockFormat, QTextCharFormat
    from PySide6.QtCore import Qt
    from docx import Document
    doc = Document()
    bf = QTextBlockFormat()
    bf.setAlignment(Qt.AlignHCenter)
    bf.setLineHeight(150, 1)
    bf.setTopMargin(10); bf.setBottomMargin(8)
    bf.setLeftMargin(5); bf.setRightMargin(4)
    bf.setTextIndent(12)
    bf.setBackground(QColor("#FFFF00"))
    para = doc.add_paragraph("hello")
    writer._apply_block_format_to_para(para, bf)
    # 固定行距
    bf2 = QTextBlockFormat(); bf2.setLineHeight(20, 2)
    writer._apply_block_format_to_para(doc.add_paragraph("x"), bf2)
    # 悬挂缩进
    bf3 = QTextBlockFormat(); bf3.setTextIndent(-10)
    writer._apply_block_format_to_para(doc.add_paragraph("y"), bf3)
    # 字符格式
    cf = QTextCharFormat()
    cf.setFontWeight(QFont.Bold)
    cf.setFontItalic(True)
    cf.setFontUnderline(True)
    cf.setForeground(QColor("#FF0000"))
    cf.setFontFamily("Arial")
    cf.setFontPointSize(14)
    run = doc.add_paragraph().add_run("x")
    writer._apply_char_format_to_run(run, cf)
    assert run.bold is True
