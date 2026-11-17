"""P0 硬化：题注/交叉引用导出为 Word 域。"""
from zipfile import ZipFile

from beeoffice.plugins.beewrite import BeeWriteEditor


def test_caption_and_crossref_fields(qtbot, tmp_path):
    e = BeeWriteEditor()
    qtbot.addWidget(e)
    e.show()
    e._edit_mode = "rich_text"
    e._captions = [{"kind": "图", "text": "架构图"}]
    e.rich_editor.setPlainText("图 1：架构图\n见图 1")
    out = tmp_path / "captions.docx"
    assert e._write_docx(str(out)) is True
    with ZipFile(out) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    assert "SEQ 图" in xml
    assert "REF BeeCaption_Fig_1" in xml
    assert "bookmarkStart" in xml
