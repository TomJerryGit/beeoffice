# tests/fidelity/test_beecmd_table_clean.py
"""
`beecmd clean`（v0.4：AI 表格清洗）的回归 —— **不联网**。

## 设计要点（本文件锁住）
* AI 只产出"清洗计划 JSON"，**实际修改由确定性代码执行**（可复核）；
* `--plan` 模式跳过 AI、按已有计划复跑（可回滚/审计）；
* 计划白名单 + 列存在性校验；不合规自动修复重试一次，仍不合规失败且不写清洗结果；
* 原始文件绝不修改；报告记录每项操作改了几处 + 样例行列号；
* 零 Qt（子进程验证）。
"""
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _run(args):
    from beeoffice import beecmd

    return beecmd.main(args)


def _write_dirty(path: Path) -> None:
    pd.DataFrame({
        "姓名": [" 张三 ", "李四", "张三", "", "王五"],
        "金额": ["100", None, "100", None, "50"],
        "备注": [" ", "x", " ", "   ", "y"],
    }).to_excel(path, index=False)


PLAN = {
    "operations": [
        {"op": "trim_whitespace"},
        {"op": "drop_empty_rows"},
        {"op": "fill_missing", "column": "金额", "value": "0"},
        {"op": "drop_duplicate_rows"},
    ]
}


def _write_plan(tmp_path: Path, plan=None) -> Path:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan or PLAN, ensure_ascii=False), encoding="utf-8")
    return path


def _read_xlsx(path: Path) -> pd.DataFrame:
    return pd.read_excel(path, dtype=str)


# ==================== 1. --plan 模式：确定性、可复跑 ====================

def test_clean_with_plan_file(tmp_path):
    src = tmp_path / "dirty.xlsx"
    _write_dirty(src)
    out = tmp_path / "clean.xlsx"
    report = tmp_path / "report.json"
    code = _run([
        "clean", str(src), "-o", str(out),
        "--plan", str(_write_plan(tmp_path)), "--report", str(report),
    ])
    assert code == 0

    cleaned = _read_xlsx(out)
    assert list(cleaned["姓名"]) == ["张三", "李四", "王五"]
    amount = cleaned.loc[cleaned["姓名"] == "李四", "金额"].iloc[0]
    assert str(amount) == "0"
    # 原文件不被修改
    assert len(_read_xlsx(src)) == 5

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["op"] == "clean"
    assert payload["plan_source"] == "plan-file"
    assert payload["rows_before"] == 5 and payload["rows_after"] == 3
    assert payload["original_untouched"] is True
    ops = {item["op"]: item for item in payload["operations"]}
    assert ops["fill_missing"]["changed"] == 1
    assert ops["drop_duplicate_rows"]["changed"] == 1
    # 报告给出可核对的行列号样例
    assert ops["fill_missing"]["samples"][0]["column"] == "金额"

    # 计划被规范化保存（供复跑/回滚）
    saved = json.loads((tmp_path / "clean.xlsx.plan.json").read_text(encoding="utf-8"))
    assert saved["operations"][0]["op"] == "trim_whitespace"


def test_clean_rejects_unknown_op_and_column(tmp_path):
    src = tmp_path / "dirty.xlsx"
    _write_dirty(src)
    out = tmp_path / "clean.xlsx"
    bad_op = _write_plan(tmp_path, {"operations": [{"op": "rm_rf"}]})
    assert _run(["clean", str(src), "-o", str(out), "--plan", str(bad_op)]) == 1
    assert not out.exists()

    bad_col = _write_plan(tmp_path, {"operations": [
        {"op": "fill_missing", "column": "不存在的列", "value": "x"},
    ]})
    assert _run(["clean", str(src), "-o", str(out), "--plan", str(bad_col)]) == 1
    assert not out.exists()


# ==================== 2. AI 模式：计划由模型出、执行确定性 ====================

class _PlanClient:
    instances = []

    def __init__(self, config=None):
        self.config = config or {}
        self.prompt = ""
        self.last_source = "ai"
        self.last_error = ""
        _PlanClient.instances.append(self)

    @property
    def available(self):
        return True

    def unavailable_reason(self):
        return ""

    def describe_source(self):
        return "AI 生成（fake）"

    def chat(self, prompt, system=None, max_tokens=900):
        self.prompt = prompt
        return True, json.dumps(PLAN, ensure_ascii=False)


class _RetryPlanClient(_PlanClient):
    calls = 0

    def chat(self, prompt, system=None, max_tokens=900):
        self.prompt = prompt
        _RetryPlanClient.calls += 1
        if _RetryPlanClient.calls == 1:
            return True, "这不是 JSON，只是一段建议"
        return True, json.dumps(PLAN, ensure_ascii=False)


class _BadPlanClient(_PlanClient):
    def chat(self, prompt, system=None, max_tokens=900):
        self.prompt = prompt
        return True, '{"operations": [{"op": "rm_rf"}]}'


def _patch(monkeypatch, cls):
    from beeoffice.plugins import ai_client as ai_mod

    monkeypatch.setattr(ai_mod, "AIClient", cls)


def _ai_args(src, out, report):
    return [
        "clean", str(src), "-o", str(out), "--report", str(report),
        "--model", "fake-model", "--api-base", "http://127.0.0.1:11434/v1",
    ]


def test_clean_ai_mode(tmp_path, monkeypatch):
    _patch(monkeypatch, _PlanClient)
    src = tmp_path / "dirty.xlsx"
    _write_dirty(src)
    out = tmp_path / "clean.xlsx"
    report = tmp_path / "report.json"
    assert _run(_ai_args(src, out, report)) == 0
    assert len(_read_xlsx(out)) == 3
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["plan_source"] == "ai" and payload["attempts"] == 1
    # 发给模型的 prompt 必须包含概况（行数/列名/样本），而不是全表
    prompt = _PlanClient.instances[-1].prompt
    assert '"rows": 5' in prompt and "姓名" in prompt and "sample_rows" in prompt


def test_clean_ai_retries_once_on_bad_plan(tmp_path, monkeypatch, capsys):
    _patch(monkeypatch, _RetryPlanClient)
    _RetryPlanClient.calls = 0
    src = tmp_path / "dirty.xlsx"
    _write_dirty(src)
    out = tmp_path / "clean.xlsx"
    report = tmp_path / "report.json"
    assert _run(_ai_args(src, out, report)) == 0, capsys.readouterr().err
    assert _RetryPlanClient.calls == 2
    assert json.loads(report.read_text(encoding="utf-8"))["attempts"] == 2
    assert "重试" not in capsys.readouterr().out  # 输出只标完成，不吹


def test_clean_ai_bad_plan_twice_saves_raw_and_fails(tmp_path, monkeypatch, capsys):
    _patch(monkeypatch, _BadPlanClient)
    src = tmp_path / "dirty.xlsx"
    _write_dirty(src)
    out = tmp_path / "clean.xlsx"
    assert _run(_ai_args(src, out, tmp_path / "r.json")) == 1
    assert not out.exists(), "计划不合法时不能写清洗结果"
    raw = tmp_path / "clean.xlsx.plan.raw.txt"
    assert raw.is_file() and "rm_rf" in raw.read_text(encoding="utf-8")
    assert "不合法" in capsys.readouterr().err


# ==================== 3. 零 Qt ====================

def test_clean_path_does_not_import_qt(tmp_path):
    src = tmp_path / "dirty.xlsx"
    _write_dirty(src)
    out = tmp_path / "clean.xlsx"
    plan = _write_plan(tmp_path)
    result_file = tmp_path / "qt_probe.txt"
    script = (
        "import sys\n"
        "from beeoffice import beecmd\n"
        f"code = beecmd.main(['clean', {str(src)!r}, '-o', {str(out)!r},"
        f" '--plan', {str(plan)!r}])\n"
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
    assert payload.startswith("code=0;"), payload
    assert payload.endswith("qt="), f"清洗路径不该加载 Qt：{payload}"
