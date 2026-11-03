"""PDF 后端适配层：工厂、Fitz 兼容实现、pypdf 骨架。"""
import fitz
import pytest

from beeoffice.pdf_backend import (
    FitzBackend,
    PdfBackend,
    PdfBackendError,
    PypdfBackend,
    backend_names,
    get_backend,
)


def _make_pdf(path, pages=3):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=200, height=200)
        page.insert_text((40, 40), f"P{i + 1}")
    doc.save(str(path))
    doc.close()


def test_factory_default_and_env(monkeypatch):
    assert isinstance(get_backend(), FitzBackend)
    monkeypatch.setenv("BEEOFFICE_PDF_BACKEND", "pypdf")
    assert isinstance(get_backend(), PypdfBackend)
    assert backend_names() == ["fitz", "pypdf"]
    with pytest.raises(PdfBackendError):
        get_backend("nope")


def test_fitz_backend_page_count_and_render(tmp_path):
    src = tmp_path / "a.pdf"
    _make_pdf(src, 3)
    backend = FitzBackend()
    assert backend.page_count(src) == 3
    out = backend.render_page_png(src, 2, tmp_path / "page2.png")
    assert (tmp_path / "page2.png").is_file()
    assert out["page"] == 2


def test_fitz_backend_delegates_merge(tmp_path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    out = tmp_path / "merged.pdf"
    _make_pdf(a, 2)
    _make_pdf(b, 1)
    info = FitzBackend().merge_pdfs([a, b], out)
    assert out.is_file()
    assert info["pages"] == 3


def test_pypdf_backend_is_instantiable():
    backend = PypdfBackend()
    assert backend.name == "pypdf"


def test_all_backends_implement_interface():
    for cls in (FitzBackend, PypdfBackend):
        assert issubclass(cls, PdfBackend)
        for name in PdfBackend.__abstractmethods__:
            assert getattr(cls, name) is not None
