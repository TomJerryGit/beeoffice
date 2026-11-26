"""DOCX 原生批注导出。"""
import zipfile
from docx import Document
from beeoffice.plugins.beewrite import BeeWriteEditor


def test_comments_written_to_docx(qtbot, tmp_path):
    e = BeeWriteEditor(); qtbot.addWidget(e); e.show(); e._edit_mode = "rich_text"
    e.rich_editor.setPlainText("Hello world")
    e._comment_manager.add("看看这里", 6, 11, excerpt="world")
    out = tmp_path / "comments.docx"
    assert e._write_docx(str(out))
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert "word/comments.xml" in names
        assert "commentRangeStart" in z.read("word/document.xml").decode("utf-8")
        assert "看看这里" in z.read("word/comments.xml").decode("utf-8")
    # python-docx 仍能打开
    assert Document(str(out)).paragraphs[0].text.startswith("Hello")
