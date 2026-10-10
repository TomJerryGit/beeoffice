# tests/test_p2_regression/test_p1_14_pdf_undo_real.py
"""
P1-14 回归：PDFAnnotator._undo_annotation 真实实现（不再用 Fake）。

背景：
  test_p1_14_pdf_undo.py 里用 _FakeAnnotator 重新实现了一遍
  undo 逻辑，只能验证"我对逻辑的理解正确"，无法验证
  PDFAnnotator._undo_annotation 实际代码。

修复（P1-14）：
  从"只删最后一个"改为"删当前页最后一个"。
  原实现 self._annotations.pop() 不看页码，用户在第 3 页点撤销
  会误删第 5 页最后一条。

测试策略：
  直接实例化真实的 PDFAnnotator，手动塞 _annotations，
  monkeypatch _update_view 为 no-op（避免依赖真实 PDF 文档），
  调用 _undo_annotation，断言行为。
"""
import pytest

fitz = pytest.importorskip("fitz")


@pytest.fixture
def pdf_annotator(qtbot):
    """
    构造一个空的 PDFAnnotator 实例。

    不打开真实 PDF，只测 _undo_annotation 的列表操作逻辑。
    _doc 保持 None，_update_view 会自动早退。
    """
    from beeoffice.plugins.pdf_annotator import PDFAnnotator
    annotator = PDFAnnotator()
    qtbot.addWidget(annotator)
    yield annotator
    try:
        annotator.close()
    except Exception:
        pass


def _make_annotation(page):
    """构造一个指定页的批注。"""
    from beeoffice.plugins.pdf_annotator import Annotation
    return Annotation(page, fitz.Rect(0, 0, 10, 10))


# ==================== 真实实现测试 ====================

def test_undo_annotation_removes_last_on_current_page(pdf_annotator):
    """
    P1-14：当前页有多条批注时，_undo_annotation 应删除当前页的
            最后一条，而不是列表里的最后一条。
    """
    pdf_annotator._doc = None
    pdf_annotator._annotations = [
        _make_annotation(0),
        _make_annotation(1),
        _make_annotation(0),   # 当前页最后一条
        _make_annotation(2),
        _make_annotation(1),   # 列表里最后一条，但不在当前页
    ]
    pdf_annotator._current_page = 0

    pdf_annotator._undo_annotation()

    pages = [a.page for a in pdf_annotator._annotations]
    assert pages == [0, 1, 2, 1], (
        f"P1-14：应删除当前页（第 0 页）的最后一条批注，"
        f"而不是列表最后一条（第 1 页）。实际: {pages}"
    )


def test_undo_annotation_no_annotation_on_current_page(
    pdf_annotator, monkeypatch
):
    """
    P1-14：当前页无批注时，应弹提示而非误删其他页。
    """
    from PySide6.QtWidgets import QMessageBox

    infos = []
    monkeypatch.setattr(
        QMessageBox, "information",
        staticmethod(
            lambda parent, title, message, *a, **k:
            infos.append((title, message))
        ),
    )

    pdf_annotator._doc = None
    pdf_annotator._annotations = [
        _make_annotation(3),
        _make_annotation(4),
    ]
    pdf_annotator._current_page = 0   # 当前页无批注

    pdf_annotator._undo_annotation()

    # 列表应保持不变
    assert len(pdf_annotator._annotations) == 2, (
        "P1-14：当前页无批注时不应删除任何条目"
    )
    assert [a.page for a in pdf_annotator._annotations] == [3, 4]

    # 应有提示
    assert infos, "当前页无批注时应弹提示"
    assert any("没有" in msg or "可撤销" in msg
               for _, msg in infos), (
        f"提示应说明当前页无批注。实际: {infos}"
    )


def test_undo_annotation_on_empty_list(pdf_annotator, monkeypatch):
    """P1-14：批注列表为空时，应弹提示而非崩溃。"""
    from PySide6.QtWidgets import QMessageBox

    infos = []
    monkeypatch.setattr(
        QMessageBox, "information",
        staticmethod(lambda *a, **k: infos.append(a)),
    )

    pdf_annotator._doc = None
    pdf_annotator._annotations = []
    pdf_annotator._current_page = 0

    pdf_annotator._undo_annotation()   # 不应抛异常

    assert infos, "空列表也应弹提示"
    assert len(pdf_annotator._annotations) == 0


def test_undo_annotation_multiple_times_removes_in_reverse(
    pdf_annotator
):
    """P1-14：连续撤销同一页的多条批注，应按后进先出删除。"""
    pdf_annotator._doc = None
    pdf_annotator._annotations = [
        _make_annotation(0),   # a
        _make_annotation(0),   # b
        _make_annotation(0),   # c
    ]
    pdf_annotator._current_page = 0

    pdf_annotator._undo_annotation()   # 删 c
    assert len(pdf_annotator._annotations) == 2

    pdf_annotator._undo_annotation()   # 删 b
    assert len(pdf_annotator._annotations) == 1

    pdf_annotator._undo_annotation()   # 删 a
    assert len(pdf_annotator._annotations) == 0