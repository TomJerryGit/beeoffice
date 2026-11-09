"""build_release 纯函数测试，提升发布脚本覆盖率。"""
from pathlib import Path

import beeoffice.build_release as br


def test_get_version_matches_package():
    from beeoffice.__version__ import __version__
    assert br.get_version() == __version__


def test_check_pyinstaller_returns_bool():
    assert isinstance(br.check_pyinstaller(), bool)


def test_clean_build_dirs(tmp_path):
    (tmp_path / "build").mkdir()
    (tmp_path / "dist").mkdir()
    (tmp_path / "BeeOffice-v9.9.9.zip").write_bytes(b"x")
    br.clean_build_dirs(tmp_path)
    assert not (tmp_path / "build").exists()
    assert not (tmp_path / "dist").exists()
    assert not (tmp_path / "BeeOffice-v9.9.9.zip").exists()


def test_compute_sha256(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"abc")
    assert br.compute_sha256(p) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    assert br.compute_sha256(tmp_path / "missing.bin") == ""


def test_create_zip_missing_dist(tmp_path):
    assert br.create_zip(tmp_path, "1.0.0") is None


def test_print_summary_writes_sha(tmp_path, capsys):
    p = tmp_path / "BeeOffice-v1.0.0-windows.zip"
    p.write_bytes(b"x" * 64)
    br.print_summary(tmp_path, p, "1.0.0", 0.0)
    out = capsys.readouterr().out
    assert "发布包构建完成" in out
    assert (tmp_path / "BeeOffice-v1.0.0-windows.zip.sha256").exists()
