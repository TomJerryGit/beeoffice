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


def test_google_resumable_upload(monkeypatch, tmp_path):
    fake = install_fake(monkeypatch)
    g = GoogleDriveStorage({"access_token": "tok"})
    f = tmp_path / "big.bin"
    f.write_bytes(b"x" * 16)

    fake.post_resp = Resp(200, headers={"Location": "https://upload.test/session"})
    fake.put_resp = Resp(200)
    assert g._upload_resumable(str(f), "big.bin", "root") is True

    fake.post_resp = Resp(500)
    assert g._upload_resumable(str(f), "big.bin", "root") is False
    fake.post_resp = Resp(200, headers={})
    assert g._upload_resumable(str(f), "big.bin", "root") is False
    fake.post_resp = Resp(200, headers={"Location": "https://upload.test/session"})
    fake.put_resp = Resp(500)
    assert g._upload_resumable(str(f), "big.bin", "root") is False


def test_onedrive_large_upload(monkeypatch, tmp_path):
    fake = install_fake(monkeypatch)
    o = OneDriveStorage({"access_token": "tok"})
    f = tmp_path / "big.bin"
    f.write_bytes(b"x" * 16)

    fake.post_resp = Resp(200, {"uploadUrl": "https://upload.test/session"})
    fake.put_resp = Resp(202)
    assert o._upload_large(str(f), "big.bin") is True

    fake.post_resp = Resp(500)
    assert o._upload_large(str(f), "big.bin") is False
    fake.post_resp = Resp(200, {})
    assert o._upload_large(str(f), "big.bin") is False
    fake.post_resp = Resp(200, {"uploadUrl": "https://upload.test/session"})
    fake.put_resp = Resp(500)
    assert o._upload_large(str(f), "big.bin") is False


def test_google_folder_path_and_create(monkeypatch):
    fake = install_fake(monkeypatch)
    g = GoogleDriveStorage({"access_token": "tok"})
    # 已存在
    monkeypatch.setattr(g, "_find_file_by_query", lambda q: "fid")
    assert g._ensure_folder_path("/a/b") == "fid"
    # 不存在则创建
    created = []
    monkeypatch.setattr(g, "_find_file_by_query", lambda q: "")
    monkeypatch.setattr(g, "_create_folder", lambda name, parent: created.append((name, parent)) or f"id_{name}")
    assert g._ensure_folder_path("/a/b") == "id_b"
    assert created == [("a", "root"), ("b", "id_a")]
    # 创建失败
    monkeypatch.setattr(g, "_create_folder", lambda name, parent: "")
    assert g._ensure_folder_path("/x") == ""

    # create folder API（恢复真实实现）
    monkeypatch.undo()
    g = GoogleDriveStorage({"access_token": "tok"})
    fake = install_fake(monkeypatch)
    fake.post_resp = Resp(200, {"id": "newid"})
    assert g._create_folder("doc", "root") == "newid"
    fake.post_resp = Resp(500)
    assert g._create_folder("doc", "root") == ""


def test_google_upload_existing_and_small(monkeypatch, tmp_path):
    fake = install_fake(monkeypatch)
    g = GoogleDriveStorage({"access_token": "tok"})
    local = tmp_path / "a.txt"
    local.write_text("hello")
    monkeypatch.setattr(g, "_ensure_folder_path", lambda p: "parent")
    monkeypatch.setattr(g, "_find_file_by_query", lambda q: "existing")
    fake.patch_resp = Resp(200)
    assert g.upload(str(local), "/folder/a.txt") is True
    fake.patch_resp = Resp(500)
    assert g.upload(str(local), "/folder/a.txt") is False

    monkeypatch.setattr(g, "_find_file_by_query", lambda q: "")
    fake.post_resp = Resp(201)
    assert g.upload(str(local), "/a.txt") is True
    fake.post_resp = Resp(500)
    assert g.upload(str(local), "/a.txt") is False
    assert g.upload(str(tmp_path / "missing.txt"), "/a.txt") is False
    assert g.upload(str(local), "/") is False


def test_onedrive_upload_small(monkeypatch, tmp_path):
    fake = install_fake(monkeypatch)
    o = OneDriveStorage({"access_token": "tok"})
    local = tmp_path / "a.txt"
    local.write_text("hello")
    fake.put_resp = Resp(201)
    assert o.upload(str(local), "/a.txt") is True
    fake.put_resp = Resp(500)
    assert o.upload(str(local), "/a.txt") is False
    assert o.upload(str(tmp_path / "missing"), "/a.txt") is False
