# tests/unit/test_bench_wps_vs_bee.py
"""S0 基准脚本的纯逻辑测试（不启动 WPS/Qt）。"""

from tools.bench_wps_vs_bee import (
    BenchFile,
    BenchResult,
    _pct,
    render_markdown,
    select_files,
)


def test_percentile():
    assert _pct([], 50) == 0.0
    assert _pct([10.0], 50) == 10.0
    assert _pct([10.0, 20.0], 50) == 15.0
    assert _pct([1.0, 2.0, 3.0, 4.0], 95) > 3.5


def test_select_files_filters_and_sorts(tmp_path):
    (tmp_path / "a.docx").write_bytes(b"x" * 120)
    (tmp_path / "b.xlsx").write_bytes(b"x" * 20)
    (tmp_path / "c.txt").write_bytes(b"x")
    (tmp_path / "~$locked.docx").write_bytes(b"x")
    files = select_files([str(tmp_path)], limit=10, max_size_mb=1)
    assert [f.name for f in files] == ["a.docx", "b.xlsx"]
    assert files[0].kind == "docx"


def test_render_markdown_includes_ratio():
    f = BenchFile("a.docx", "a.docx", "docx", 1024)
    results = [
        BenchResult("beeoffice", "docx_import", "a.docx", "a.docx", "docx",
                    1024, samples=[200.0, 220.0]),
        BenchResult("wps", "docx_import", "a.docx", "a.docx", "docx",
                    1024, samples=[100.0, 120.0]),
    ]
    md = render_markdown(results, [f])
    assert "docx_import" in md
    assert "x |" in md
    assert "BeeOffice" in md
