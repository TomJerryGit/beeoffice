# tests/unit/test_validation_kit.py
"""`tools/validation_kit.py`（外部验证证据采集）的纯逻辑回归。"""
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.validation_kit import (   # noqa: E402
    build_command, build_evidence, build_markdown, file_record,
    run_command, sha256_file, write_evidence,
)


def test_sha_and_file_record(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text("x,y\n1,2\n", encoding="utf-8")
    record = file_record(path)
    assert record["exists"] is True and record["size"] > 0
    assert record["sha256"] == sha256_file(path)
    missing = file_record(tmp_path / "nope.csv")
    assert missing["exists"] is False


def test_build_command_per_task():
    exe = "beecmd.exe"
    assert build_command(exe, "convert", ["a.csv"], out_file="a.xlsx",
                         to="xlsx") == [
        "beecmd.exe", "convert", "a.csv", "--to", "xlsx", "-o", "a.xlsx",
    ]
    assert build_command(exe, "merge", ["a.xlsx", "b.xlsx"],
                         out_file="sum.xlsx")[-1] == "sum.xlsx"
    assert build_command(exe, "clean", ["d.csv"], out_file="c.xlsx",
                         plan="p.json")[-2:] == ["--plan", "p.json"]
    ai = build_command(exe, "ai", ["a.md"], out_file="s.md",
                       api_base="http://127.0.0.1:11434/v1",
                       model="llama3.2")
    assert "summarize" in ai and "--model" in ai


def test_run_command_captures_output_and_exit(tmp_path):
    result = run_command([
        sys.executable, "-c",
        "import sys; print('hello'); sys.exit(3)",
    ])
    assert result["exit_code"] == 3
    assert "hello" in result["stdout"]


def test_build_evidence_and_markdown(tmp_path):
    src = tmp_path / "in.csv"
    src.write_text("a,b\n", encoding="utf-8")
    out = tmp_path / "out.xlsx"
    out.write_bytes(b"fake-xlsx")
    evidence = build_evidence(
        "beecmd.exe", "convert",
        ["beecmd.exe", "convert", "in.csv", "--to", "xlsx"],
        {"exit_code": 0, "stdout": "✅ ok", "stderr": "", "elapsed_s": 1.2},
        [src], str(out),
    )
    assert evidence["ok"] is True
    text = build_markdown(evidence)
    assert "外部验证证据" in text
    assert "in.csv" in text and "out.xlsx" in text
    assert "✅" in text


def test_write_evidence_json_md_and_zip(tmp_path):
    src = tmp_path / "in.csv"
    src.write_text("x\n", encoding="utf-8")
    out = tmp_path / "out.csv"
    out.write_text("y\n", encoding="utf-8")
    evidence = build_evidence(
        "beecmd.exe", "convert", ["beecmd.exe"], {"exit_code": 0},
        [src], str(out),
    )
    paths = write_evidence(evidence, tmp_path / "evidence", make_zip=True)
    assert Path(paths["json"]).is_file()
    assert Path(paths["markdown"]).is_file()
    payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
    assert payload["task"] == "convert"
    with zipfile.ZipFile(paths["zip"]) as archive:
        assert sorted(archive.namelist()) == ["evidence.json", "evidence.md"]
