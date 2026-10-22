# tests/fidelity/test_docx_header_footer_5_1.py
"""5.1：页眉页脚编辑（对话框 + 视图字段 + DOCX 导出文字）。"""
from docx import Document
from PySide6.QtWidgets import QLineEdit

from beeoffice.plugins.bee_export import apply_header_footer
from beeoffice.plugins.beewrite_doc_mixin import DocMixin
from beeoffice.plugins.beewrite_page_extras import HeaderFooterDialog


class _Fake:
    def __init__(self):
        self._docx_header_text = ""
        self._docx_footer_text = ""
        self._docx_section_parts = [
            {"header_linked": True, "footer_linked": True,
             "header_xml": "<w:p/>", "footer_xml": "<w:p/>"},
        ]
        self._status = []
        self.contentChanged = type(
            "S", (), {"emit": staticmethod(lambda: None)}
        )()

    def _set_status(self, text, *_a):
        self._status.append(text)


def test_dialog_values(qapp):
    dlg = HeaderFooterDialog("旧页眉", "旧页脚")
    dlg._header_edit.setText("新页眉")
    dlg._footer_edit.setText("新页脚")
    assert dlg.values() == ("新页眉", "新页脚")
    assert isinstance(dlg._header_edit, QLineEdit)


def test_apply_updates_first_section(qapp):
    fake = _Fake()
    DocMixin._apply_header_footer_texts(fake, "H", "F")
    assert fake._docx_header_text == "H"
    assert fake._docx_footer_text == "F"
    entry = fake._docx_section_parts[0]
    assert entry["header_text"] == "H"
    assert entry["footer_text"] == "F"
    assert entry["header_xml"] == ""
    assert entry["footer_linked"] is False
    assert any("页眉/页脚" in s for s in fake._status)


def test_docx_export_writes_header_footer_text(tmp_path):
    doc = Document()
    assert apply_header_footer(doc, header_text="页眉文字", footer_text="页脚文字")
    out = tmp_path / "hf.docx"
    doc.save(str(out))
    reopened = Document(str(out))
    section = reopened.sections[0]
    assert section.header.paragraphs[0].text == "页眉文字"
    assert section.footer.paragraphs[0].text == "页脚文字"
