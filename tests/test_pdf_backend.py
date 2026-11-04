"""PDF 后端工厂与 pypdf 基础能力。"""
from pathlib import Path

import fitz
import pytest

from beeoffice.pdf_backend import (
    PdfBackend,
    PdfBackendError,
    PypdfBackend,
    backend_names,
    get_backend,
)


def _make_pdf(path, pages=2):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=200, height=200)
        page.insert_text((40, 40), f"P{i + 1}")
    doc.save(str(path))
    doc.close()


def test_factory_default_and_env(monkeypatch):
    assert isinstance(get_backend(), PypdfBackend)
    assert backend_names() == ["pypdf"]
    monkeypatch.setenv("BEEOFFICE_PDF_BACKEND", "pypdf")
    assert isinstance(get_backend(), PypdfBackend)
    with pytest.raises(PdfBackendError):
        get_backend("fitz")


def test_page_count_and_render(tmp_path):
    src = tmp_path / "a.pdf"
    _make_pdf(src, 3)
    backend = PypdfBackend()
    assert backend.page_count(src) == 3
    out = backend.render_page_png(src, 2, tmp_path / "page2.png")
    assert Path(out["out"]).is_file()
    assert out["page"] == 2


def test_interface_complete():
    assert issubclass(PypdfBackend, PdfBackend)
    for name in PdfBackend.__abstractmethods__:
        assert getattr(PypdfBackend, name) is not None
