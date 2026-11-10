"""结构化补测：Google Drive / OneDrive API 成功与失败分支（mock requests）。"""
import sys

from beeoffice.cloud_sync.googledrive import GoogleDriveStorage
from beeoffice.cloud_sync.onedrive import OneDriveStorage


class Resp:
    def __init__(self, status=200, data=None, content=b"", headers=None):
        self.status_code = status
        self._data = data or {}
        self._content = content
        self.headers = headers or {}
        self.text = ""

    def json(self):
        return self._data

    def iter_content(self, chunk_size=8192):
        yield self._content


class FakeRequests:
    def __init__(self):
        self.calls = []
        self.get_resp = Resp()
        self.post_resp = Resp()
        self.put_resp = Resp()
        self.patch_resp = Resp()
        self.delete_resp = Resp(204)

    def get(self, *a, **k):
        self.calls.append(("get", a, k))
        return self.get_resp

    def post(self, *a, **k):
        self.calls.append(("post", a, k))
        return self.post_resp

    def put(self, *a, **k):
        self.calls.append(("put", a, k))
        return self.put_resp

    def patch(self, *a, **k):
        self.calls.append(("patch", a, k))
        return self.patch_resp

    def delete(self, *a, **k):
        self.calls.append(("delete", a, k))
        return self.delete_resp


def install_fake(monkeypatch):
    fake = FakeRequests()
    monkeypatch.setitem(sys.modules, "requests", fake)
    return fake


def test_google_api_paths(monkeypatch, tmp_path):
    fake = install_fake(monkeypatch)
    g = GoogleDriveStorage({"access_token": "tok"})
    monkeypatch.setattr(g, "_resolve_path", lambda p: "fid")

    fake.get_resp = Resp(200, {"files": [{"name": "a.txt"}]})
    assert g.list_files("/") == ["a.txt"]

    fake.get_resp = Resp(200, content=b"hello")
    local = tmp_path / "sub" / "a.txt"
    assert g.download("/a.txt", str(local)) is True
    assert local.read_bytes() == b"hello"

    fake.delete_resp = Resp(204)
    assert g.delete("/a.txt") is True
    fake.delete_resp = Resp(500)
    assert g.delete("/a.txt") is False
    assert g.exists("/a.txt") is True

    fake.get_resp = Resp(200, {"size": "12",
                                "modifiedTime": "2024-01-01T12:00:00.000Z"})
    size, mtime = g.get_file_info("/a.txt")
    assert size == 12 and mtime > 0

    fake.get_resp = Resp(200)
    assert g.authenticate() is True
    fake.get_resp = Resp(401)
    assert g.authenticate() is False


def test_google_failures(monkeypatch, tmp_path):
    fake = install_fake(monkeypatch)
    g = GoogleDriveStorage({"access_token": "tok"})
    monkeypatch.setattr(g, "_resolve_path", lambda p: "")
    assert g.list_files("/x") == []
    assert g.download("/x", str(tmp_path / "x")) is False
    assert g.delete("/x") is False
    assert g.get_file_info("/x") == (0, 0.0)

    fake.get_resp = Resp(500)
    assert g.list_files("/x") == []
    assert g.download("/x", str(tmp_path / "y")) is False


def test_onedrive_api_paths(monkeypatch, tmp_path):
    fake = install_fake(monkeypatch)
    o = OneDriveStorage({"access_token": "tok"})

    fake.get_resp = Resp(200, {"value": [{"name": "a.txt"}]})
    assert o.list_files("/docs") == ["a.txt"]

    fake.get_resp = Resp(200, content=b"onedrive")
    local = tmp_path / "a.txt"
    assert o.download("/docs/a.txt", str(local)) is True
    assert local.read_bytes() == b"onedrive"

    local2 = tmp_path / "up.txt"
    local2.write_text("x")
    fake.put_resp = Resp(201)
    assert o.upload(str(local2), "/docs/up.txt") is True

    fake.delete_resp = Resp(204)
    assert o.delete("/docs/a.txt") is True
    assert o.exists("/docs/a.txt") is True

    fake.get_resp = Resp(200, {"size": 12,
                                "lastModifiedDateTime": "2024-01-01T12:00:00Z"})
    size, mtime = o.get_file_info("/docs/a.txt")
    assert size == 12 and mtime > 0

    fake.get_resp = Resp(200)
    assert o.authenticate() is True
    fake.get_resp = Resp(401)
    assert o.authenticate() is False


def test_onedrive_failures(monkeypatch, tmp_path):
    fake = install_fake(monkeypatch)
    o = OneDriveStorage({"access_token": "tok"})
    assert o.upload(str(tmp_path / "missing"), "/x") is False
    fake.get_resp = Resp(500)
    assert o.list_files("/x") == []
    assert o.download("/x", str(tmp_path / "y")) is False
    assert o.exists("/x") is False
    assert o.get_file_info("/x") == (0, 0.0)
