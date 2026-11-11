"""核心 100% 批次 2：自然语言公式、WebDAV、i18n。"""
import sys
import types
from pathlib import Path

import pytest

import beeoffice.i18n as i18n_mod
from beeoffice.i18n import I18nManager
from beeoffice.plugins.nl_formula import NLFormulaParser
from beeoffice.cloud_sync.webdav import WebDAVStorage


# ---------- nl_formula ----------
def test_nl_formula_remaining_branches():
    assert NLFormulaParser._parse_if("如果A1没有条件") is None
    assert NLFormulaParser._extract_value("", ["显示"]) == ""
    assert NLFormulaParser._extract_value("显示高，否则低", ["显示"]) == '"高"'
    assert NLFormulaParser._extract_value("显示显示高", ["显示"]) == '"高"'
    assert NLFormulaParser.parse("") is None


# ---------- webdav ----------
class FakeClient:
    def __init__(self, options=None):
        self.options = options
        self.checked = []
        self.mkdirs = []
        self.uploaded = []
    def check(self, path=None):
        self.checked.append(path)
        return False
    def mkdir(self, path):
        self.mkdirs.append(path)
    def upload_sync(self, remote, local):
        self.uploaded.append((remote, local))


def test_webdav_client_import_error(monkeypatch):
    s = WebDAVStorage({})
    monkeypatch.setitem(sys.modules, "webdav3.client", None)
    with pytest.raises(RuntimeError, match="未安装 webdavclient3"):
        s._get_client()


def test_webdav_client_creation_and_upload_mkdir(monkeypatch, tmp_path):
    mod = types.ModuleType("webdav3.client")
    mod.Client = FakeClient
    monkeypatch.setitem(sys.modules, "webdav3.client", mod)
    s = WebDAVStorage({"url": "https://dav", "username": "u", "password": "p"})
    client = s._get_client()
    assert isinstance(client, FakeClient)
    assert client.options["webdav_hostname"] == "https://dav"
    local = tmp_path / "a.txt"
    local.write_text("x", encoding="utf-8")
    assert s.upload(str(local), "/dir/a.txt") is True
    assert client.mkdirs == ["/dir"]


# ---------- i18n ----------
@pytest.fixture
def reset_i18n(monkeypatch):
    I18nManager._instance = None
    I18nManager._translations = {}
    I18nManager._default_translations = {}
    yield
    I18nManager._instance = None
    I18nManager._translations = {}
    I18nManager._default_translations = {}


def test_i18n_missing_locales_dir(reset_i18n, monkeypatch):
    monkeypatch.setattr(Path, "exists", lambda self: False)
    I18nManager()
    assert I18nManager._translations == {}


def test_i18n_bad_json_and_missing_en(reset_i18n, monkeypatch, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{bad", encoding="utf-8")
    monkeypatch.setattr(Path, "exists", lambda self: True)
    monkeypatch.setattr(Path, "glob", lambda self, pattern: [bad])
    import builtins
    monkeypatch.setattr(builtins, "open", lambda *a, **k: (_ for _ in ()).throw(ValueError("bad")))
    I18nManager()
    assert I18nManager._translations["bad"] == {}
    assert I18nManager._translations.get("en_US", {}) == {}


def test_i18n_language_and_fallback(reset_i18n):
    m = I18nManager()
    I18nManager._translations = {"en_US": {"hello": "Hello"}, "zh_CN": {"hello": "你好"}}
    I18nManager._default_translations = {"hello": "Hello"}
    assert m.current_language == "zh_CN"
    assert m.get("hello") == "你好"
    assert m.get("missing", "中文默认") == "中文默认"
    assert m.get("hello2") == "hello2"
    assert m.set_language("zh_CN") is True
    assert m.set_language("xx") is False


# ---------- secret_store ----------
def test_secret_store_fallbacks(monkeypatch):
    import base64
    import beeoffice.secret_store as ss

    monkeypatch.setattr(ss, "_IS_WINDOWS", False)
    assert ss.is_encrypted() is False
    token = ss.protect("abc")
    assert token.startswith("b64:") and ss.unprotect(token) == "abc"
    assert ss.unprotect("dpapi:AAAA") == ""
    assert ss.unprotect("b64:a") == ""
    assert ss.unprotect("中文") == "中文"

    monkeypatch.setattr(ss, "_IS_WINDOWS", True)
    monkeypatch.setattr(ss, "_dpapi", lambda *a: (_ for _ in ()).throw(RuntimeError("x")))
    assert ss.protect("abc").startswith("b64:")
    monkeypatch.setattr(ss, "_dpapi", lambda *a, **k: b"abc")
    token = ss.protect("abc")
    assert token.startswith("dpapi:")
    assert ss.unprotect(token) == "abc"
    # DPAPI 解密异常
    monkeypatch.setattr(ss, "_dpapi", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bad")))
    assert ss.unprotect("dpapi:!!!") == ""


def test_secret_store_dpapi_failure_and_local_free(monkeypatch):
    import ctypes
    import beeoffice.secret_store as ss

    class FakeFn:
        argtypes = []
        restype = None
        def __call__(self, *a):
            return False
    class Crypt32:
        CryptProtectData = FakeFn()
        CryptUnprotectData = FakeFn()
    class Kernel32:
        def LocalFree(self, p):
            raise OSError("free")
    class Windll:
        crypt32 = Crypt32()
        kernel32 = Kernel32()
    monkeypatch.setattr(ss.ctypes, "windll", Windll())
    with pytest.raises(OSError):
        ss._dpapi(b"x", True)
    blob, _buf = ss._make_blob(b"abc")
    assert ss._take_blob(blob) == b"abc"


# ---------- update_checker ----------
def test_update_info_and_version(monkeypatch):
    import beeoffice.update_checker as uc
    info = uc.UpdateInfo("5.5.0", "v5.5.0", "https://x", assets=[{"name": "a.sha256"}])
    assert info.sha256_asset["name"] == "a.sha256"
    assert uc.UpdateInfo("5.5.0", "v5.5.0", "x").sha256_asset is None
    with pytest.raises(uc.UpdateError):
        uc.parse_version("")
    assert uc.parse_version("v5.3.2-beta") == (5, 3, 2)
    assert uc.is_newer("5.3.2", "5.3.3") is True
    assert uc.is_newer("5.3.3", "5.3.2") is False


def test_get_json_error(monkeypatch):
    import beeoffice.update_checker as uc
    monkeypatch.setattr(uc.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("net")))
    with pytest.raises(uc.UpdateError):
        uc._get_json("https://x")


def test_check_for_update_branches(monkeypatch):
    import beeoffice.update_checker as uc
    monkeypatch.setattr(uc, "_get_json", lambda *a, **k: {})
    with pytest.raises(uc.UpdateError):
        uc.check_for_update("5.0.0")
    monkeypatch.setattr(uc, "_get_json", lambda *a, **k: [{"draft": True, "tag_name": "v9.0.0"}])
    assert uc.check_for_update("5.0.0") is None
    monkeypatch.setattr(uc, "_get_json", lambda *a, **k: [
        {"draft": True, "tag_name": "v9.0.0"},
        {"prerelease": True, "tag_name": "v8.0.0"},
        {"tag_name": "bad"},
        {"tag_name": "v5.0.0"},
    ])
    assert uc.check_for_update("5.0.0") is None
    monkeypatch.setattr(uc, "_get_json", lambda *a, **k: [
        {"tag_name": "v5.5.0", "html_url": "https://x", "body": "b", "assets": [{"name": "a"}]},
    ])
    info = uc.check_for_update("5.0.0")
    assert info.version == "5.5.0" and info.assets


def test_download_update(monkeypatch, tmp_path):
    import hashlib
    import beeoffice.update_checker as uc

    with pytest.raises(uc.UpdateError):
        uc.download_update("http://x", tmp_path / "x", "0" * 64)

    class Resp:
        def __init__(self, data): self.data = data; self.done = False
        def read(self, n):
            if self.done: return b""
            self.done = True
            return self.data
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(uc.urllib.request, "urlopen", lambda *a, **k: Resp(b"abc"))
    data = b"abc"
    sha = hashlib.sha256(data).hexdigest()
    out = uc.download_update("https://x", tmp_path / "a.bin", sha)
    assert out.read_bytes() == data
    with pytest.raises(uc.UpdateError):
        uc.download_update("https://x", tmp_path / "b.bin", "0" * 64)
    monkeypatch.setattr(uc.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("net")))
    with pytest.raises(uc.UpdateError):
        uc.download_update("https://x", tmp_path / "c.bin", "0" * 64)


# ---------- settings ----------
def test_settings_encode_decode_fallback(monkeypatch):
    import beeoffice.secret_store as ss
    import beeoffice.settings as st
    monkeypatch.setattr(st.Path, "home", staticmethod(lambda: Path(r"D:eeofficeV\_ptmpnalysis")))
    s = st.AppSettings()
    monkeypatch.setattr(ss, "protect", lambda x: (_ for _ in ()).throw(RuntimeError("x")))
    assert s._encode("abc") == "abc"
    monkeypatch.setattr(ss, "unprotect", lambda x: (_ for _ in ()).throw(RuntimeError("x")))
    assert s._decode("abc") == "abc"


def test_settings_load_bad_json_and_save_failure(monkeypatch, tmp_path):
    import beeoffice.settings as st
    monkeypatch.setattr(st.Path, "home", staticmethod(lambda: tmp_path))
    s = st.AppSettings()
    bad = tmp_path / "bad.json"
    bad.write_text("{bad", encoding="utf-8")
    s.path = bad
    s.load()  # 只记录错误，不抛出
    good = tmp_path / "good.json"
    good.write_text('{"version": 1, "cloud_config": {"__decoded__": "bad"}}', encoding="utf-8")
    s.path = good
    s.load()
    s.path = tmp_path / "save.json"
    monkeypatch.setattr(st.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("x")))
    monkeypatch.setattr(st.Path, "unlink", lambda self, **k: (_ for _ in ()).throw(OSError("unlink")))
    assert s.save() is False


def test_settings_recent_files(monkeypatch, tmp_path):
    import beeoffice.settings as st
    monkeypatch.setattr(st.Path, "home", staticmethod(lambda: tmp_path))
    s = st.AppSettings()
    s.save = lambda: True
    s.add_recent_file("a")
    s.add_recent_file("a")
    assert s.recent_files[0] == "a" and s.recent_files.count("a") == 1
    s.clear_recent_files()
    assert s.recent_files == []
