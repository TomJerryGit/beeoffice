"""GUI 覆盖率批次：template_manager。"""
import json
import urllib.error
from pathlib import Path

import pytest

from beeoffice.resources import template_manager as tm_mod
from beeoffice.resources.template_manager import (
    OnlineTemplateFetcher,
    TemplateManager,
    _safe_filename,
    get_template_manager,
)


class FakeResp:
    def __init__(self, data):
        self.data = data.encode("utf-8") if isinstance(data, str) else data
    def read(self):
        return self.data
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def test_safe_filename():
    assert _safe_filename("") == "untitled"
    assert _safe_filename("a<b>c:d") == "a_b_c_d"
    assert _safe_filename("...") == "untitled"
    assert len(_safe_filename("x" * 300)) == 100


def test_index_recovery(tmp_path):
    (tmp_path / "index.json").write_text("{bad", encoding="utf-8")
    assert TemplateManager(tmp_path)._index == {"user_templates": []}
    (tmp_path / "index.json").write_text("[]", encoding="utf-8")
    assert TemplateManager(tmp_path)._index == {"user_templates": []}
    (tmp_path / "index.json").write_text(
        json.dumps({"user_templates": "bad"}), encoding="utf-8"
    )
    assert TemplateManager(tmp_path)._index == {"user_templates": []}
    (tmp_path / "index.json").write_text(
        json.dumps({"user_templates": [{"name": "x"}, {"filename": "f", "name": "ok"}]}),
        encoding="utf-8",
    )
    assert len(TemplateManager(tmp_path)._index["user_templates"]) == 1


def test_save_query_delete_rename(tmp_path):
    m = TemplateManager(tmp_path)
    assert m.save_as_template("", "x") is False
    assert m.save_as_template("我的模板", "内容", "工作") is True
    assert m.save_user_template("另一个", None) is True
    users = m.get_user_templates()
    assert len(users) == 2
    assert any(t["source"] == "builtin" for t in m.get_builtin_templates())
    assert m.delete_template("我的模板") is True
    assert m.delete_template("") is False
    assert m.rename_template("另一个", "新名字") is True
    assert m.rename_template("", "x") is False
    assert m.rename_template("不存在", "x") is False


def test_stale_index_cleanup(tmp_path):
    m = TemplateManager(tmp_path)
    m.save_as_template("临时", "x")
    # 删除文件但保留索引
    entry = m._index["user_templates"][0]
    (tmp_path / entry["filename"]).unlink()
    m.get_all_templates()
    assert entry not in m._index["user_templates"]


def test_save_index_failure(tmp_path, monkeypatch):
    m = TemplateManager(tmp_path)
    monkeypatch.setattr("builtins.open", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
    assert m._save_index() is False


def test_online_download_and_fetcher(tmp_path, monkeypatch):
    m = TemplateManager(tmp_path)
    assert m.download_online_template("", "x") is False
    monkeypatch.setattr(tm_mod.urllib.request, "urlopen", lambda *a, **k: FakeResp("hello"))
    assert m.download_online_template("https://x/a.md", "在线") is True
    monkeypatch.setattr(tm_mod.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
    assert m.download_online_template("https://x/a.md", "在线") is False

    f = m.fetch_online_templates()
    assert isinstance(f, OnlineTemplateFetcher)
    ready = []
    f.templates_ready.connect(lambda data: ready.append(data))
    monkeypatch.setattr(tm_mod.urllib.request, "urlopen", lambda *a, **k: FakeResp(json.dumps([
        {"type": "file", "name": "a.md", "download_url": "u", "size": 1},
        {"type": "dir", "name": "b"},
    ])))
    f.run()
    assert ready[0][0]["name"] == "a"


def test_fetcher_error(monkeypatch):
    f = OnlineTemplateFetcher("x")
    errors = []
    f.error.connect(errors.append)
    monkeypatch.setattr(tm_mod.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("net")))
    f.run()
    assert errors


def test_categorize_and_singleton():
    m = TemplateManager(Path.home() / ".beeoffice_templates_test")
    assert m._categorize("") == "其他"
    assert m._categorize("周报") == "工作"
    assert m._categorize("会议纪要") == "会议"
    assert get_template_manager() is not None
