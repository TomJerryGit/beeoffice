# tests/unit/test_verify_release.py
"""`tools/verify_release.py`（发布包一致性校验器）的纯逻辑回归。"""
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.verify_release import sha256, verify_zip   # noqa: E402


def _make_zip(path: Path, *, locale_keys: int = 226, with_sha: bool = True,
              future: bool = True) -> Path:
    stamp = (2035 if future else 2000, 1, 1, 0, 0, 0)

    def _info(name: str) -> zipfile.ZipInfo:
        return zipfile.ZipInfo(name, date_time=stamp)

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(_info("BeeOffice/BeeOffice.exe"), b"exe")
        archive.writestr(
            _info("BeeOffice/_internal/beeoffice/data/tech_words.txt"), "词\n"
        )
        archive.writestr(
            _info("BeeOffice/_internal/beeoffice/locales/zh_CN.json"),
            json.dumps({f"k{i}": "值" for i in range(locale_keys)},
                       ensure_ascii=False),
        )
        archive.writestr(
            _info("BeeOffice/_internal/beeoffice/locales/en_US.json"),
            json.dumps({f"k{i}": "v" for i in range(locale_keys)}),
        )
        # 再加空条目凑到 ≥3000
        for i in range(3000):
            archive.writestr(_info(f"BeeOffice/filler/{i}.bin"), b"")
    if with_sha:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        path.with_name(path.name + ".sha256").write_text(
            f"{digest}  {path.name}\n", encoding="utf-8"
        )
    return path


def test_sha256_helper(tmp_path):
    path = tmp_path / "x.bin"
    path.write_bytes(b"hello")
    assert sha256(path) == hashlib.sha256(b"hello").hexdigest()


def test_verify_zip_all_checks_pass(tmp_path):
    zip_path = _make_zip(tmp_path / "pkg.zip")
    result = verify_zip(zip_path, commit_time=1)   # 提交时间很旧 → 时间线通过
    assert result["ok"] is True, result
    names = {item["name"] for item in result["checks"]}
    assert "SHA-256 与 .sha256 一致" in names
    assert "必需文件存在" in names
    assert f"locale key 数 = 226" in names
    assert "包内最新条目晚于提交" in names


def test_verify_zip_detects_sha_mismatch(tmp_path):
    zip_path = _make_zip(tmp_path / "pkg.zip", with_sha=False)
    result = verify_zip(zip_path, commit_time=1)
    assert result["ok"] is False
    failed = [i["name"] for i in result["checks"] if not i["ok"]]
    assert "SHA-256 与 .sha256 一致" in failed


def test_verify_zip_detects_old_zip(tmp_path):
    """包比提交还旧 → 时间线检查失败（防止拿旧包冒充分支）。"""
    zip_path = _make_zip(tmp_path / "pkg.zip", future=False)
    result = verify_zip(zip_path, commit_time=2_000_000_000)
    assert result["ok"] is False
    assert any(
        i["name"] == "包内最新条目晚于提交" and not i["ok"]
        for i in result["checks"]
    )


def test_verify_zip_detects_wrong_locale_count(tmp_path):
    zip_path = _make_zip(tmp_path / "pkg.zip", locale_keys=100)
    result = verify_zip(zip_path, commit_time=1)
    assert result["ok"] is False
    assert any(
        i["name"].startswith("locale key 数") and not i["ok"]
        for i in result["checks"]
    )
