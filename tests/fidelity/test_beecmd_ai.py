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
