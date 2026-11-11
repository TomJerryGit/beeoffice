"""BeeShow AI 服务补测。"""
import json

import pytest

from beeoffice.plugins.beeshow_ai_service import BeeshowAIService, SlideOutline


def test_outline_markdown_variants():
    s = SlideOutline("标题", "title_only", ["副标题"])
    assert s.to_markdown().startswith("# 标题")
    assert "> 副标题" in s.to_markdown()
    s2 = SlideOutline("标题", "two_column", ["a", "b", "c"])
    assert '<div class="columns">' in s2.to_markdown()
    s3 = SlideOutline("标题", "title_content", ["a", "b"])
    md = s3.to_markdown()
    assert "- a" in md and "- b" in md
    assert SlideOutline.from_dict(s3.to_dict()).title == "标题"
    assert SlideOutline.from_dict({}).layout == "title_content"


def test_generate_outline_no_key_fallback():
    svc = BeeshowAIService()
    out = svc.generate_outline("主题")
    assert len(out) >= 3
    assert out[0].layout == "title_only"
    assert svc.generate_outline("") == []


def test_generate_outline_with_ai(monkeypatch):
    svc = BeeshowAIService({"api_key": "k", "retry": 0})
    payload = [{"title": "封面", "layout": "title_only", "bullets": ["x"]}]
    monkeypatch.setattr(svc, "_call_llm", lambda p: "```json\n" + json.dumps(payload) + "\n```")
    out = svc.generate_outline("主题")
    assert out[0].title == "封面"


def test_generate_outline_ai_failure_fallback(monkeypatch):
    svc = BeeshowAIService({"api_key": "k", "retry": 0})
    monkeypatch.setattr(svc, "_call_llm", lambda p: "not json")
    out = svc.generate_outline("主题")
    assert out and out[0].layout == "title_only"


def test_refine_and_notes(monkeypatch):
    svc = BeeshowAIService()
    current = [SlideOutline("旧")]
    assert svc.refine_outline(current, "改") == current
    assert svc.generate_notes("标题", "内容") == ""
    svc.api_key = "k"
    monkeypatch.setattr(svc, "_call_llm", lambda p: " 讲稿 ")
    assert svc.generate_notes("标题", "内容") == "讲稿"
    monkeypatch.setattr(svc, "_call_llm", lambda p: json.dumps([{"title": "新", "layout": "ending"}]))
    assert svc.refine_outline(current, "改")[0].title == "新"


def test_parse_outline_json():
    svc = BeeshowAIService()
    assert svc._parse_outline_json("") == []
    out = svc._parse_outline_json(
        '说明文字 [{"title": "A", "layout": "bad", "bullets": ["x"]},'
        '{"title": "", "bullets": []}, {"bad": 1}] 结束'
    )
    assert len(out) == 1 and out[0].layout == "title_content"
    with pytest.raises(ValueError):
        svc._parse_outline_json("{}")
    with pytest.raises(ValueError):
        svc._parse_outline_json("not json")


def test_call_llm_requests_and_urllib(monkeypatch):
    svc = BeeshowAIService({"api_key": "k"})
    class Resp:
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": "hi"}}]}
    import sys, types
    fake_requests = types.ModuleType("requests")
    fake_requests.post = lambda *a, **k: Resp()
    monkeypatch.setitem(sys.modules, "requests", fake_requests)
    assert svc._call_llm("p") == "hi"
    # 无 choices
    fake_requests.post = lambda *a, **k: type("R", (), {"raise_for_status": lambda s: None, "json": lambda s: {}})()
    with pytest.raises(RuntimeError):
        svc._call_llm("p")
    # urllib 回退分支直接测
    class UResp:
        def read(self): return b'{"choices":[{"message":{"content":"u"}}]}'
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: UResp())
    assert svc._call_llm_urllib("http://x", {}, {})["choices"][0]["message"]["content"] == "u"


def test_suggest_images():
    assert BeeshowAIService().suggest_images("x") == []
