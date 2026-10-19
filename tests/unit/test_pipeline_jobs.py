# tests/unit/test_pipeline_jobs.py
"""`tools/pipelines/build_jobs.py`（阶段③ 流水线模板生成器）的回归。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.pipelines.build_jobs import build_jobs, collect   # noqa: E402


def _touch(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_md_pdf_template_builds_convert_plus_verify(tmp_path):
    src = tmp_path / "合同"
    _touch(src / "a.md", "# A\n")
    _touch(src / "b.txt", "B\n")
    out = tmp_path / "out"

    payload = build_jobs("md-pdf", src, out)

    jobs = payload["jobs"]
    assert len(jobs) == 4, jobs          # 2 个 convert + 2 个 verify
    assert [j["op"] for j in jobs] == ["convert", "verify", "convert", "verify"]
    assert jobs[0]["to"] == "pdf"
    assert jobs[1]["artifact"].endswith("a.pdf")
    assert jobs[2]["src"].endswith("b.txt")


def test_beshow_template_has_no_verify(tmp_path):
    src = tmp_path / "讲稿"
    _touch(src / "a.md", "# A\n")
    _touch(src / "b.md", "# B\n")
    out = tmp_path / "out"

    payload = build_jobs("beshow", src, out)
    jobs = payload["jobs"]
    assert len(jobs) == 2, jobs          # 2 个 convert，无 verify
    assert {j["op"] for j in jobs} == {"convert"}
    assert jobs[0]["to"] == "beshow"
    assert jobs[0]["out"].endswith("a.beshow")


def test_sheet_merge_template_uses_merge_op(tmp_path):
    src = tmp_path / "月报"
    _touch(src / "1月.xlsx")
    _touch(src / "2月.xlsx")
    out = tmp_path / "out"

    payload = build_jobs("sheet-merge", src, out)
    jobs = payload["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["op"] == "merge"
    assert jobs[0]["mode"] == "append"
    assert len(jobs[0]["srcs"]) == 2


def test_collect_ignores_lock_files_and_unknown_ext(tmp_path):
    src = tmp_path / "data"
    _touch(src / "a.md")
    _touch(src / "~$a.md")               # Office 锁文件
    _touch(src / "a.png")                # 不认识的扩展名
    assert [p.name for p in collect(src, "md-pdf")] == ["a.md"]


def test_main_writes_jobs_json(tmp_path, capsys):
    from tools.pipelines.build_jobs import main

    src = tmp_path / "in"
    _touch(src / "a.md", "# hi\n")
    out = tmp_path / "out"
    assert main(["--kind", "md-pdf", "--input", str(src),
                 "--output-dir", str(out), "--no-verify"]) == 0
    jobs_path = out / "jobs.json"
    assert jobs_path.is_file()
    payload = json.loads(jobs_path.read_text(encoding="utf-8"))
    assert len(payload["jobs"]) == 1
    assert "batch" in capsys.readouterr().out


def test_main_rejects_missing_input(tmp_path, capsys):
    from tools.pipelines.build_jobs import main

    assert main(["--kind", "md-pdf", "--input", str(tmp_path / "nope")]) == 1
    assert "不存在" in capsys.readouterr().err
