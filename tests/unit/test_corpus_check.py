"""语料库完整性检查测试。"""
import json
import sys
from pathlib import Path

from docx import Document

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from corpus_check import check_manifest  # noqa: E402


def test_manifest_ready_docx(tmp_path):
    docx = tmp_path / "word.docx"
    Document().save(docx)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "samples": [{"id": "w1", "path": "word.docx"}]
    }), encoding="utf-8")
    result = check_manifest(manifest)
    assert result["ok"] is True
    assert result["ready"] == 1
    assert result["failed"] == 0
