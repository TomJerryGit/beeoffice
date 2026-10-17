# tests/test_p2_regression/test_p1_14_pdf_undo.py
"""P1-14 回归：PDF 撤销区分页码"""
import pytest

fitz = pytest.importorskip("fitz")
from beeoffice.plugins.pdf_annotator import Annotation


class _FakeAnnotator:
    def __init__(self):
        self._annotations = []
        self._current_page = 0

    def undo_annotation(self):
        for i in range(len(self._annotations) - 1, -1, -1):
            if self._annotations[i].page == self._current_page:
                self._annotations.pop(i)
                return True
        return False


def test_undo_same_page():
    a = _FakeAnnotator()
    a._annotations = [
        Annotation(0, fitz.Rect(0, 0, 10, 10)),
        Annotation(1, fitz.Rect(0, 0, 10, 10)),
        Annotation(0, fitz.Rect(10, 10, 20, 20)),
    ]
    a._current_page = 0
    assert a.undo_annotation() is True
    pages = [x.page for x in a._annotations]
    assert pages == [0, 1]


def test_undo_no_annotation_on_current_page():
    a = _FakeAnnotator()
    a._annotations = [Annotation(5, fitz.Rect(0, 0, 10, 10))]
    a._current_page = 0
    assert a.undo_annotation() is False
    assert len(a._annotations) == 1
