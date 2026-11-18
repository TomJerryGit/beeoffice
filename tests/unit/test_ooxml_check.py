"""OOXML 完整性校验工具测试。"""
import sys
from pathlib import Path

from docx import Document
from openpyxl import Workbook
from pptx import Presentation

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from ooxml_check import check_file  # noqa: E402


def test_check_valid_office_files(tmp_path):
    docx = tmp_path / "a.docx"
    Document().save(docx)
    xlsx = tmp_path / "a.xlsx"
    Workbook().save(xlsx)
    pptx = tmp_path / "a.pptx"
    Presentation().save(pptx)
    for path in (docx, xlsx, pptx):
        result = check_file(path)
        assert result["ok"], result


def test_check_corrupt_zip(tmp_path):
    bad = tmp_path / "bad.docx"
    bad.write_bytes(b"not a zip")
    assert check_file(bad)["ok"] is False


def test_check_missing_part(tmp_path):
    import zipfile
    path = tmp_path / "missing.docx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("_rels/.rels", "<Relationships/>")
    result = check_file(path)
    assert result["ok"] is False
    assert any("word/document.xml" in e for e in result["errors"])
