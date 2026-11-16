"""Wave 3 W11：PDF 批注增强/撤销重做/导入导出/保护入口。"""
import json

from pypdf import PdfWriter
from PySide6.QtWidgets import QFileDialog

from beeoffice.plugins.pdf_annotator import PDFAnnotator, Annotation, AnnoRect


def make_pdf(path, pages=1):
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=300, height=400)
    w.write(str(path))


def make_annotator(qtbot, tmp_path):
    pdf = tmp_path / "a.pdf"
    make_pdf(pdf, 2)
    a = PDFAnnotator()
    qtbot.addWidget(a)
    a.open_pdf(str(pdf))
    qtbot.wait(10)
    return a


def test_annotation_width_roundtrip():
    anno = Annotation(0, AnnoRect(1, 2, 30, 40), "highlight", width=5)
    data = anno.to_dict()
    assert data["width"] == 5
    again = Annotation.from_dict(data)
    assert again.width == 5


def test_undo_redo_and_visibility(qtbot, tmp_path):
    a = make_annotator(qtbot, tmp_path)
    a._annotations.append(Annotation(0, AnnoRect(1, 2, 30, 40)))
    a._update_view()
    a._undo_annotation()
    assert len(a._annotations) == 0
    assert len(a._redo_stack) == 1
    a._redo_annotation()
    assert len(a._annotations) == 1
    a._toggle_annotations_visible()
    assert a._annotations_visible is False
    a._toggle_annotations_visible()
    assert a._annotations_visible is True


def test_export_import_annotations(qtbot, tmp_path, monkeypatch):
    a = make_annotator(qtbot, tmp_path)
    a._annotations.append(Annotation(0, AnnoRect(1, 2, 30, 40), "underline"))
    out = tmp_path / "ann.beeanno"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (str(out), "BeeAnno (*.beeanno)")),
    )
    a._export_annotations()
    assert out.exists()
    a._annotations.clear()
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName",
        staticmethod(lambda *a, **k: (str(out), "BeeAnno (*.beeanno)")),
    )
    a._import_annotations()
    assert len(a._annotations) == 1


def test_continuous_toggle(qtbot, tmp_path):
    a = make_annotator(qtbot, tmp_path)
    a._toggle_continuous()
    assert a._continuous is True
    a._toggle_continuous()
    assert a._continuous is False
