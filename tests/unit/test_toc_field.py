"""P0 硬化：Word 目录导出为 TOC 域。"""
from pathlib import Path
from zipfile import ZipFile

from beeoffice.plugins.beewrite import BeeWriteEditor


def test_toc_export_contains_field(qtbot, tmp_path):
    e = BeeWriteEditor()
    qtbot.addWidget(e)
    e.show()
    e._edit_mode = "rich_text"
    cursor = e.rich_editor.textCursor()
    cursor.insertText("第一章")
    bf = cursor.blockFormat(); bf.setHeadingLevel(1); cursor.setBlockFormat(bf)
    cursor.insertBlock(); cursor.insertText("正文")
    e._update_toc()
    out = tmp_path / "toc.docx"
    e._write_docx(str(out))
    assert out.exists()
    with ZipFile(out) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    assert "TOC" in xml
    assert "fldChar" in xml
