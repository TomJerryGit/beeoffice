"""DOCX 打开失败时的文本兜底。"""
from docx import Document
from beeoffice.docx_recovery import recover_plain_text


def test_recover_text_from_docx(tmp_path):
    p = tmp_path / "ok.docx"
    d = Document(); d.add_paragraph("第一段"); d.add_paragraph("第二段"); d.save(p)
    assert "第一段" in recover_plain_text(p)
    assert "第二段" in recover_plain_text(p)


def test_recover_bad_zip(tmp_path):
    p = tmp_path / "bad.docx"; p.write_bytes(b"not a zip")
    assert recover_plain_text(p) == ""
