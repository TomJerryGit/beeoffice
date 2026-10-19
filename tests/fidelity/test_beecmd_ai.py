# tests/fidelity/test_beecmd_ai.py
"""
`beecmd ai`（v0.3：本地/云端 AI 任务）的回归 —— **不联网**。

## 为什么需要
战略阶段③要求"本地 AI 任务化"：AI 不能只存在于 GUI 按钮里。
`beecmd ai summarize|polish|keywords|continue` 把 AI 变成**可脚本调用的任务**。

## 本文件锁住的行为
* 成功：写输出文件 + 来源标注 + 可选 JSON 元信息（model/api_base/source/耗时）；
* **诚实性**：AI 不可用 / 调用失败 → 退出码 1、说明原因、**不写输出文件**；
* `batch` 支持 `{"op":"ai", ...}` 并写审计；
* 零 Qt（子进程验证 AI 路径不 import PySide6）。
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _run(args):
    from beeoffice import beecmd

    return beecmd.main(args)


@pytest.fixture
def sample_md(tmp_path):
    path = tmp_path / "报告.md"
    path.write_text("# 季度报告\n\n收入增长 20%，成本下降 5%。\n", encoding="utf-8")
    return path


class _FakeClient:
    """假 AIClient：记录 prompt，返回固定文本（不联网）。"""

    #: 测试用它检查"到底把什么 prompt 发给了模型"
    instances = []

    def __init__(self, config=None):
        self.config = config or {}
        self.prompt = ""
        self.last_source = "ai"
        self.last_error = ""
        _FakeClient.instances.append(self)

    @property
    def available(self):
        return True

    def unavailable_reason(self):
        return ""

    def describe_source(self):
        return f"AI 生成（{self.config.get('model') or 'fake'}）"

    def chat(self, prompt, system=None, max_tokens=1200):
        self.prompt = prompt
        return True, "- 收入增长 20%\n- 成本下降 5%"

    def fail(self, prompt, system=None, max_tokens=1200):
        return False, "HTTP 500: boom"


class _UnavailableClient(_FakeClient):
    @property
    def available(self):
        return False

    def unavailable_reason(self):
        return "未配置模型名（测试）"


class _BrokenClient(_FakeClient):
    last_source = "error"

    def chat(self, prompt, system=None, max_tokens=1200):
        self.prompt = prompt
        self.last_source = "error"
        self.last_error = "HTTP 500: boom"
        return False, self.last_error


class _JsonClient(_FakeClient):
    """返回合法 JSON 数组（extract 任务用）。"""

    def chat(self, prompt, system=None, max_tokens=1200):
        self.prompt = prompt
        return True, ('[{"title": "收入", "value": "1200 万元",'
                      ' "quote": "营业收入 1200 万元"}]')


class _BadJsonClient(_FakeClient):
    """返回不合法的"结构化"输出（必须被拒绝，不能当结果写盘）。"""

    def chat(self, prompt, system=None, max_tokens=1200):
        self.prompt = prompt
        return True, "这不是 JSON，只是一段解释文字。"


class _OutlineClient(_FakeClient):
    """返回带标题与页分隔符的大纲（outline 任务用）。"""

    def chat(self, prompt, system=None, max_tokens=1200):
        self.prompt = prompt
        return True, "# 季度汇报\n\n- 收入增长 20%\n\n---\n\n# 风险\n\n- 回款周期 75 天"


class _BadOutlineClient(_FakeClient):
    """没有任何 `# 标题` 的输出（必须被拒绝）。"""

    def chat(self, prompt, system=None, max_tokens=1200):
        self.prompt = prompt
        return True, "收入增长 20%，成本下降 5%。"


class _RetryClient(_FakeClient):
    """第一次返回坏 JSON，第二次（格式修复）返回合法 JSON。"""

    calls = 0

    def chat(self, prompt, system=None, max_tokens=1200):
        self.prompt = prompt
        _RetryClient.calls += 1
        if _RetryClient.calls == 1:
            return True, '["title":"收入","value":1200]'
        return True, '[{"title": "收入", "value": "1200", "quote": "营业收入 1200 万元"}]'


class _AlwaysBadJsonClient(_FakeClient):
    def chat(self, prompt, system=None, max_tokens=1200):
        self.prompt = prompt
        return True, '["title":"收入"'


@pytest.fixture
def fake_ai(monkeypatch):
    from beeoffice.plugins import ai_client as ai_mod

    _FakeClient.instances = []
    monkeypatch.setattr(ai_mod, "AIClient", _FakeClient)
    return ai_mod


# ==================== 1. 成功路径 ====================

def test_ai_summarize_writes_result_and_meta(sample_md, tmp_path,
                                             fake_ai, capsys):
    out = tmp_path / "摘要.md"
    meta = tmp_path / "meta.json"
    code = _run([
        "ai", "summarize", str(sample_md),
        "--out", str(out), "--meta", str(meta),
        "--model", "fake-model", "--api-base", "http://127.0.0.1:11434/v1",
    ])
    assert code == 0
    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert "收入增长" in text

    payload = json.loads(meta.read_text(encoding="utf-8"))
    assert payload["task"] == "summarize"
    assert payload["source"] == "ai"
    assert payload["model"] == "fake-model"
    assert "elapsed_ms" in payload

    stdout = capsys.readouterr().out
    assert "AI summarize 完成" in stdout
    assert "AI 生成" in stdout


def test_ai_keywords_prompt_contains_source(sample_md, tmp_path,
                                            fake_ai, capsys):
    out = tmp_path / "kw.md"
    assert _run([
        "ai", "keywords", str(sample_md), "--out", str(out),
        "--model", "fake-model", "--api-base", "http://127.0.0.1:11434/v1",
    ]) == 0
    assert out.is_file()
    # 提示词必须带原文（防止"发了个空 prompt"这类假成功）
    assert _FakeClient.instances, "没有真正调用 AI 客户端"
    prompt = _FakeClient.instances[-1].prompt
    assert "季度报告" in prompt and "收入增长" in prompt, prompt[:200]
    assert "AI keywords 完成" in capsys.readouterr().out


# ==================== 2. 诚实性：失败不写文件 ====================

def test_ai_unavailable_exits_1_without_output(sample_md, tmp_path,
                                               monkeypatch, capsys):
    from beeoffice.plugins import ai_client as ai_mod

    monkeypatch.setattr(ai_mod, "AIClient", _UnavailableClient)
    out = tmp_path / "should_not_exist.md"
    code = _run(["ai", "summarize", str(sample_md), "--out", str(out)])
    assert code == 1
    assert not out.exists(), "AI 不可用时不能写输出（那是假成功）"
    err = capsys.readouterr().err
    assert "AI 不可用" in err and "未配置模型名" in err


def test_ai_call_failure_exits_1_without_output(sample_md, tmp_path,
                                                monkeypatch, capsys):
    from beeoffice.plugins import ai_client as ai_mod

    monkeypatch.setattr(ai_mod, "AIClient", _BrokenClient)
    out = tmp_path / "should_not_exist.md"
    code = _run([
        "ai", "summarize", str(sample_md), "--out", str(out),
        "--model", "m", "--api-base", "http://127.0.0.1:11434/v1",
    ])
    assert code == 1
    assert not out.exists()
    assert "HTTP 500" in capsys.readouterr().err


def test_ai_rejects_empty_source(tmp_path, fake_ai, capsys):
    src = tmp_path / "empty.md"
    src.write_text("   \n", encoding="utf-8")
    code = _run(["ai", "summarize", str(src)])
    assert code == 1
    assert "为空" in capsys.readouterr().err


# ==================== 2.5 extract / outline 的任务契约 ====================

def _patch_client(monkeypatch, cls):
    from beeoffice.plugins import ai_client as ai_mod

    monkeypatch.setattr(ai_mod, "AIClient", cls)


def test_ai_extract_valid_json(sample_md, tmp_path, monkeypatch, capsys):
    _patch_client(monkeypatch, _JsonClient)
    out = tmp_path / "条款.json"
    code = _run([
        "ai", "extract", str(sample_md), "--out", str(out),
        "--model", "fake-model", "--api-base", "http://127.0.0.1:11434/v1",
    ])
    assert code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data[0]["title"] == "收入"
    assert "quote" in data[0]
    assert "AI extract 完成" in capsys.readouterr().out


def test_ai_extract_invalid_json_is_rejected(sample_md, tmp_path,
                                             monkeypatch, capsys):
    """模型没按 JSON 输出 → 保存 raw、退出 1，**不能把解释文字当结果**。"""
    _patch_client(monkeypatch, _BadJsonClient)
    out = tmp_path / "条款.json"
    code = _run([
        "ai", "extract", str(sample_md), "--out", str(out),
        "--model", "fake-model", "--api-base", "http://127.0.0.1:11434/v1",
    ])
    assert code == 1
    assert not out.exists(), "不合法的 JSON 不能写进结果文件"
    raw = tmp_path / "条款.json.raw.txt"
    assert raw.is_file() and "不是 JSON" in raw.read_text(encoding="utf-8")
    assert "合法 JSON" in capsys.readouterr().err


def test_ai_extract_prompt_contains_quote_requirement(sample_md, tmp_path,
                                                      monkeypatch):
    _patch_client(monkeypatch, _JsonClient)
    out = tmp_path / "条款.json"
    assert _run([
        "ai", "extract", str(sample_md), "--out", str(out),
        "--model", "m", "--api-base", "http://127.0.0.1:11434/v1",
        "--limit", "3",
    ]) == 0
    prompt = _JsonClient.instances[-1].prompt
    assert "quote" in prompt and "季度报告" in prompt
    assert "最多 3 条" in prompt


def test_ai_outline_valid(sample_md, tmp_path, monkeypatch, capsys):
    _patch_client(monkeypatch, _OutlineClient)
    out = tmp_path / "大纲.md"
    code = _run([
        "ai", "outline", str(sample_md), "--out", str(out),
        "--model", "m", "--api-base", "http://127.0.0.1:11434/v1",
        "--slides", "6",
    ])
    assert code == 0
    text = out.read_text(encoding="utf-8")
    assert "# 季度汇报" in text and "---" in text
    assert "6 页" in _OutlineClient.instances[-1].prompt


def test_ai_outline_without_headings_is_rejected(sample_md, tmp_path,
                                                 monkeypatch, capsys):
    _patch_client(monkeypatch, _BadOutlineClient)
    out = tmp_path / "大纲.md"
    code = _run([
        "ai", "outline", str(sample_md), "--out", str(out),
        "--model", "m", "--api-base", "http://127.0.0.1:11434/v1",
    ])
    assert code == 1
    assert not out.exists()
    assert (tmp_path / "大纲.md.raw.txt").is_file()
    assert "大纲" in capsys.readouterr().err


def test_ai_extract_retries_once_on_bad_json(sample_md, tmp_path,
                                             monkeypatch, capsys):
    """小模型第一次 JSON 不合法 → 自动修复重试一次，成功则写结果并记 attempts=2。"""
    _patch_client(monkeypatch, _RetryClient)
    _RetryClient.calls = 0
    out = tmp_path / "条款.json"
    meta = tmp_path / "meta.json"
    code = _run([
        "ai", "extract", str(sample_md), "--out", str(out),
        "--meta", str(meta),
        "--model", "m", "--api-base", "http://127.0.0.1:11434/v1",
    ])
    assert code == 0, capsys.readouterr().err
    assert _RetryClient.calls == 2
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data[0]["quote"]
    payload = json.loads(meta.read_text(encoding="utf-8"))
    assert payload["attempts"] == 2
    assert "重试后通过" in capsys.readouterr().out


def test_ai_extract_retry_still_bad_saves_raw_and_fails(sample_md, tmp_path,
                                                        monkeypatch, capsys):
    _patch_client(monkeypatch, _AlwaysBadJsonClient)
    out = tmp_path / "条款.json"
    code = _run([
        "ai", "extract", str(sample_md), "--out", str(out),
        "--model", "m", "--api-base", "http://127.0.0.1:11434/v1",
    ])
    assert code == 1
    assert not out.exists()
    assert (tmp_path / "条款.json.raw.txt").is_file()
    err = capsys.readouterr().err
    assert "已重试 1 次" in err


def test_ai_extract_no_retry_flag(sample_md, tmp_path, monkeypatch, capsys):
    _patch_client(monkeypatch, _AlwaysBadJsonClient)
    out = tmp_path / "条款.json"
    code = _run([
        "ai", "extract", str(sample_md), "--out", str(out), "--no-retry",
        "--model", "m", "--api-base", "http://127.0.0.1:11434/v1",
    ])
    assert code == 1
    assert "已重试" not in capsys.readouterr().err


# ==================== 3. batch 支持 ai ====================
def test_batch_supports_ai(sample_md, tmp_path, fake_ai):
    out = tmp_path / "batch_out.md"
    audit = tmp_path / "audit.jsonl"
    jobs = tmp_path / "jobs.json"
    jobs.write_text(json.dumps({
        "jobs": [{
            "op": "ai", "task": "summarize", "src": str(sample_md),
            "out": str(out), "model": "fake-model",
            "api_base": "http://127.0.0.1:11434/v1",
        }]
    }), encoding="utf-8-sig")

    assert _run(["batch", str(jobs), "--audit", str(audit)]) == 0
    assert out.is_file()
    lines = [json.loads(x) for x in
             audit.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(lines) == 1
    assert lines[0]["op"] == "ai" and lines[0]["ok"] is True


# ==================== 4. 零 Qt ====================

def test_ai_path_does_not_import_qt(sample_md, tmp_path):
    """
    AI 任务路径必须能在无 Qt 的服务器上跑（配置错误也应"干净失败"）。

    ⚠️ 沙箱限制：子进程不能用管道捕获输出，结果写文件。
    """
    result_file = tmp_path / "qt_probe.txt"
    script = (
        "import sys\n"
        "from beeoffice import beecmd\n"
        "code = beecmd.main(['ai', 'summarize', "
        f"{str(sample_md)!r}, '--out', {str(tmp_path / 'x.md')!r},"
        " '--api-base', 'http://127.0.0.1:9/v1', '--model', 'x',"
        " '--api-key', 'k'])\n"
        "loaded = [m for m in sys.modules if m.startswith(('PySide6', 'shiboken'))]\n"
        f"open({str(result_file)!r}, 'w', encoding='utf-8').write("
        "f'code={code};qt={\",\".join(loaded)}')\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script], cwd=str(ROOT),
        env={**__import__("os").environ, "PYTHONPATH": str(ROOT)},
        timeout=180,
    )
    assert completed.returncode == 0
    payload = result_file.read_text(encoding="utf-8")
    assert payload.startswith("code=1;"), payload     # 连不上 → 干净失败
    assert payload.endswith("qt="), f"AI 路径不该加载 Qt：{payload}"
