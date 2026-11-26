"""DOCX 修订标记导出（简化）。"""
import zipfile
from beeoffice.plugins.beewrite import BeeWriteEditor


def test_revisions_written_to_docx(qtbot, tmp_path):
    e = BeeWriteEditor(); qtbot.addWidget(e); e.show(); e._edit_mode = "rich_text"
    e.rich_editor.setPlainText("第一行\n第二行")
    e._revision_manager.start_revision("第一行\n第二行")
    e.rich_editor.setPlainText("第一行\n第二行改")
    out = tmp_path / "revisions.docx"
    assert e._write_docx(str(out))
    with zipfile.ZipFile(out) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    assert "w:ins" in xml
    assert "w:del" in xml
