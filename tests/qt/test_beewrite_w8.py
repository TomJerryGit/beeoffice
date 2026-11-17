"""Wave 2 W8：视图工具/注释 DOCX 导出/20 页性能基线。"""
import time
from docx import Document

from beeoffice.plugins.beewrite import BeeWriteEditor


def make_editor(qtbot):
    e = BeeWriteEditor()
    qtbot.addWidget(e)
    e.show()
    e._edit_mode = "rich_text"
    return e


def test_view_toggles(qtbot):
    e = make_editor(qtbot)
    e._toggle_grid_lines()
    assert e._grid_lines_on is True
    e._toggle_grid_lines()
    assert e._grid_lines_on is False
    e._toggle_ruler()
    assert e._ruler_visible is True
    e._toggle_ruler()
    assert e._ruler_visible is False
    e._toggle_fullscreen()
    e._toggle_fullscreen()


def test_footnotes_export_to_docx(qtbot, tmp_path):
    e = make_editor(qtbot)
    e.rich_editor.setPlainText("正文[F1][E1]")
    e._footnotes = ["第一条脚注"]
    e._endnotes = ["第一条尾注"]
    out = tmp_path / "notes.docx"
    assert e._write_docx(str(out)) is True
    from zipfile import ZipFile
    with ZipFile(out) as z:
        assert "word/footnotes.xml" in z.namelist()
        assert "word/endnotes.xml" in z.namelist()
        notes = z.read("word/footnotes.xml").decode("utf-8")
        ends = z.read("word/endnotes.xml").decode("utf-8")
        body = z.read("word/document.xml").decode("utf-8")
    assert "第一条脚注" in notes
    assert "第一条尾注" in ends
    assert "footnoteReference" in body


def test_20_paragraph_export_performance(qtbot, tmp_path):
    e = make_editor(qtbot)
    lines = [f"第 {i} 页内容" for i in range(1, 21)]
    e.rich_editor.setPlainText("\n".join(lines))
    out = tmp_path / "perf.docx"
    start = time.perf_counter()
    assert e._write_docx(str(out)) is True
    elapsed = time.perf_counter() - start
    assert elapsed < 20
    doc = Document(str(out))
    assert len([p for p in doc.paragraphs if p.text.strip()]) == 20
