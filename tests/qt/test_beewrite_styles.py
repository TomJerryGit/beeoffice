"""Wave 2 W5：BeeWrite 样式库/清除格式/DOCX 样式往返。"""
from docx import Document

from beeoffice.plugins.beewrite import BeeWriteEditor


def make_editor(qtbot):
    e = BeeWriteEditor()
    qtbot.addWidget(e)
    e.show()
    return e


def select_all(editor):
    editor.rich_editor.selectAll()


def test_apply_heading_and_clear(qtbot):
    e = make_editor(qtbot)
    e.rich_editor.setPlainText("标题")
    select_all(e)
    e._apply_named_style("标题 1")
    block = e.rich_editor.document().firstBlock()
    assert block.blockFormat().headingLevel() == 1
    e._clear_formatting()
    block = e.rich_editor.document().firstBlock()
    assert block.blockFormat().headingLevel() == 0


def test_apply_body_quote_code(qtbot):
    e = make_editor(qtbot)
    for name in ("正文", "引用", "代码"):
        e.rich_editor.setPlainText(name)
        select_all(e)
        e._apply_named_style(name)
        assert e.rich_editor.toPlainText() == name


def test_heading_exports_docx_heading_style(qtbot, tmp_path):
    e = make_editor(qtbot)
    e.rich_editor.setPlainText("第一章")
    select_all(e)
    e._apply_named_style("标题 1")
    e._edit_mode = "rich_text"
    out = tmp_path / "style.docx"
    assert e._write_docx(str(out)) is True
    doc = Document(str(out))
    styles = [p.style.name for p in doc.paragraphs if p.text.strip()]
    assert any("Heading" in s or "标题" in s for s in styles), styles
