# tests/fidelity/test_docx_toc_field_5_4.py
"""5.4：DOCX 自动目录 TOC 域（可更新，不是静态文字）。"""
from docx import Document

from beeoffice.plugins.bee_export import export_to_docx
from beeoffice.plugins.beewrite_doc_mixin import DocMixin


class _Fake:
    def __init__(self):
        self._docx_toc_field = False
        self._status = []
        self.contentChanged = type(
            "S", (), {"emit": staticmethod(lambda: None)}
        )()

    def _set_status(self, text, *_a):
        self._status.append(text)


def _instr_texts(path):
    doc = Document(str(path))
    xml = doc.element.body.xml
    return xml


def test_toc_field_exported_when_requested(tmp_path):
    out = tmp_path / "toc.docx"
    md = "# 第一章\n\n正文\n\n## 1.1 小节\n\n内容\n"
    assert export_to_docx(md, str(out), toc_field=True) is True
    xml = _instr_texts(out)
    assert "TOC" in xml and "fldChar" in xml
    assert "1-3" in xml


def test_no_toc_field_by_default(tmp_path):
    out = tmp_path / "plain.docx"
    assert export_to_docx("# 标题\n\n正文\n", str(out)) is True
    assert "TOC \\o" not in _instr_texts(out)


def test_enable_toc_field_sets_flag(qapp):
    fake = _Fake()
    DocMixin._enable_toc_field(fake)
    assert fake._docx_toc_field is True
    assert any("目录域" in s for s in fake._status)
