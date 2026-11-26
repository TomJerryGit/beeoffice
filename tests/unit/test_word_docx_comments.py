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


def test_comments_read_back(qtbot, tmp_path):
    from beeoffice.plugins.beewrite_docx_comments import read_comments_from_docx
    e = BeeWriteEditor(); qtbot.addWidget(e); e.show(); e._edit_mode = "rich_text"
    e.rich_editor.setPlainText("Hello native comment world")
    e._comment_manager.add("回读批注", 6, 11, excerpt="native")
    out = tmp_path / "read-comments.docx"
    assert e._write_docx(str(out))
    comments = read_comments_from_docx(out)
    assert len(comments) == 1
    assert comments[0]["text"].strip() == "回读批注"
    assert "native" in comments[0]["excerpt"]
