# tests/unit/test_build_cli.py
"""`tools/build_cli.py`（独立 beecmd.exe 打包器）的纯逻辑回归 —— 不跑 PyInstaller。"""
import hashlib
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import build_cli   # noqa: E402


def test_must_exclude_qt():
    """独立 CLI 必须排除 Qt：体积/依赖都是次要的，重要的是“服务器可跑”。"""
    assert "PySide6" in build_cli.EXCLUDES
    assert "shiboken6" in build_cli.EXCLUDES


def test_entry_and_readme_exist():
    assert build_cli.ENTRY.is_file()
    assert "beecmd_entry" in build_cli.ENTRY.name
    readme = build_cli.README_TEXT
    assert "beecmd.exe" in readme
    assert "md → docx / pdf" in readme        # 明确写不支持项
    assert "SHA256SUMS" in readme


def test_sha256_helper(tmp_path):
    path = tmp_path / "x.bin"
    path.write_bytes(b"hello")
    assert build_cli._sha256(path) == hashlib.sha256(b"hello").hexdigest()


def test_make_zip_contains_exe_and_checksum(tmp_path, monkeypatch):
    monkeypatch.setattr(build_cli, "DIST", tmp_path)
    exe = tmp_path / "beecmd.exe"
    exe.write_bytes(b"fake-exe-bytes")

    result = build_cli._make_zip(exe, "0.4.0", "5.0.15")

    zip_path = Path(result["zip"])
    assert zip_path.is_file()
    with zipfile.ZipFile(zip_path) as archive:
        assert sorted(archive.namelist()) == ["README-beecmd.txt", "beecmd.exe"]
    sha_file = zip_path.with_name(zip_path.name + ".sha256")
    assert sha_file.read_text(encoding="utf-8").split()[0] == result["zip_sha256"]
    assert result["zip_sha256"] == build_cli._sha256(zip_path)
