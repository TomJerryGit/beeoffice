"""结构化补测：云同步 providers（WebDAV / Google Drive / OneDrive）。"""
from pathlib import Path

import pytest

from beeoffice.cloud_sync.webdav import WebDAVStorage
from beeoffice.cloud_sync.googledrive import GoogleDriveStorage
from beeoffice.cloud_sync.onedrive import OneDriveStorage


class FakeWebDAVClient:
    def __init__(self):
        self.files = [".", "..", "a.txt", "b.txt"]
        self.checked = []
        self.uploaded = []
        self.downloaded = []
        self.deleted = []

    def check(self, path="/"):
        self.checked.append(path)
        return True

    def list(self, path):
        return self.files

    def download_sync(self, remote, local):
        self.downloaded.append((remote, local))

    def upload_sync(self, remote, local):
        self.uploaded.append((remote, local))

    def mkdir(self, path):
        self.checked.append(("mkdir", path))

    def clean(self, path):
        self.deleted.append(path)

    def info(self, path):
        return {"size": "12", "modified": "1.5"}


def make_webdav():
    s = WebDAVStorage({"url": "https://example.test/dav",
                       "username": "u", "password": "p"})
    s._client = FakeWebDAVClient()
    return s


def test_webdav_success_paths(tmp_path):
    s = make_webdav()
    assert s.authenticate() is True
    assert s.list_files("docs") == ["a.txt", "b.txt"]
    assert s.list_files("/docs") == ["a.txt", "b.txt"]
    local = tmp_path / "x" / "a.txt"
    assert s.download("/docs/a.txt", str(local)) is True
    assert local.parent.exists()
    assert s.upload(str(local), "/docs/a.txt") is True
    assert s.delete("/docs/a.txt") is True
    assert s.exists("/docs/a.txt") is True
    assert s.get_file_info("/docs/a.txt") == (12, 1.5)


def test_webdav_failure_paths(tmp_path):
    class BadClient(FakeWebDAVClient):
        def check(self, path="/"):
            raise RuntimeError("bad")
        def list(self, path):
            raise RuntimeError("bad")
        def download_sync(self, remote, local):
            raise RuntimeError("bad")
        def upload_sync(self, remote, local):
            raise RuntimeError("bad")
        def clean(self, path):
            raise RuntimeError("bad")
        def info(self, path):
            raise RuntimeError("bad")

    s = WebDAVStorage({})
    s._client = BadClient()
    assert s.authenticate() is False
    assert s.list_files("x") == []
    assert s.download("x", str(tmp_path / "x")) is False
    assert s.upload("x", "y") is False
    assert s.delete("x") is False
    assert s.exists("x") is False
    assert s.get_file_info("x") == (0, 0.0)


def test_webdav_info_invalid_values():
    s = make_webdav()
    s._client.info = lambda path: {"size": "bad", "modified": "bad"}
    assert s.get_file_info("x") == (0, 0.0)


def test_google_helpers(monkeypatch):
    g = GoogleDriveStorage({"access_token": "tok"})
    assert g._headers()["Authorization"] == "Bearer tok"
    assert GoogleDriveStorage._escape_query("a'b\\c") == "a\\'b\\\\c"
    assert g._resolve_path("/") == "root"
    # 路径不存在
    monkeypatch.setattr(g, "_find_file_by_query", lambda q: "")
    assert g._resolve_path("missing/file.txt") == ""
    # 两层都存在
    ids = {"folder": "fid", "file.txt": "xid"}
    def fake_find(q):
        for name, fid in ids.items():
            if f"name = '{name}'" in q:
                return fid
        return ""
    monkeypatch.setattr(g, "_find_file_by_query", fake_find)
    assert g._resolve_path("/folder/file.txt") == "xid"


def test_onedrive_helpers():
    o = OneDriveStorage({"access_token": "tok"})
    assert o._headers()["Authorization"] == "Bearer tok"
    o._check_requests()
    assert OneDriveStorage({}).authenticate() is False
