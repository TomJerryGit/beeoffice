"""发布门禁：语料检查集成。"""
import json
import sys
from pathlib import Path

from docx import Document

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from release_check import check_corpus  # noqa: E402


def _manifest(tmp_path, ok=True):
    docx = tmp_path / "sample.docx"
    Document().save(docx)
    data = {"samples": [{"id": "w1", "path": "sample.docx"}]}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_corpus_gate_ok(tmp_path):
    assert check_corpus(manifest=_manifest(tmp_path)) == []


def test_corpus_gate_missing_manifest(tmp_path):
    assert check_corpus(manifest=tmp_path / "nope.json")
