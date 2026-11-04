"""自动更新检查：版本比较、Release 解析、sha256 下载校验。"""
import hashlib
import io

import pytest

from beeoffice.update_checker import (
    UpdateError,
    check_for_update,
    download_update,
    is_newer,
    parse_version,
)


def test_parse_and_compare():
    assert parse_version("v5.3.2") == (5, 3, 2)
    assert is_newer("5.3.1", "5.3.2")
    assert not is_newer("5.3.2", "5.3.2")
    assert is_newer("5.3.2", "5.4.0")


def test_check_for_update_picks_stable(monkeypatch):
    releases = [
        {"tag_name": "v5.4.0", "draft": False, "prerelease": True,
         "html_url": "https://github.com/x/releases/tag/v5.4.0", "assets": []},
        {"tag_name": "v5.3.5", "draft": False, "prerelease": False,
         "html_url": "https://github.com/x/releases/tag/v5.3.5",
         "assets": [{"name": "app.zip", "browser_download_url": "https://x"}]},
        {"tag_name": "v5.3.2", "draft": False, "prerelease": False,
         "html_url": "https://github.com/x/releases/tag/v5.3.2", "assets": []},
    ]

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        "beeoffice.update_checker.urllib.request.urlopen",
        lambda req, timeout=8: Resp(__import__("json").dumps(releases).encode()),
    )
    info = check_for_update("5.3.2")
    assert info is not None
    assert info.version == "5.3.5"
    assert "v5.3.5" in info.html_url


def test_download_hash_validation(tmp_path, monkeypatch):
    data = b"hello update"
    sha = hashlib.sha256(data).hexdigest()

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        "beeoffice.update_checker.urllib.request.urlopen",
        lambda req, timeout=60: Resp(data),
    )
    target = tmp_path / "update.zip"
    assert download_update("https://example.com/update.zip", target, sha) == target
    assert target.read_bytes() == data

    bad = tmp_path / "bad.zip"
    with pytest.raises(UpdateError):
        download_update("https://example.com/update.zip", bad, "deadbeef")
    assert not bad.exists()


def test_download_requires_https(tmp_path):
    with pytest.raises(UpdateError):
        download_update("http://example.com/x.zip", tmp_path / "x.zip", "00")
