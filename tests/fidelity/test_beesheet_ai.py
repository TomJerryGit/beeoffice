# tests/fidelity/test_beesheet_ai.py
"""
R5：蜜算 AI 助手（公式建议 / 解释表格问题 / 表格摘要）。

## 定位（与 WPS 的"AI 一键生成"不同）
走**本地优先 + 可解释**：不自动改用户数据；事实（错误值/重复/空值）由
**本地规则**查出，AI 只负责解释；未配置 AI 或调用失败时，
**先说明原因并征求同意**，同意后才给本地结果且写明"不是 AI 生成"
（与蜜写同一套规则）。

## 本文件守的
1. 上下文与提示词：**只发表头 + 少量样本**（绝不整表），且提示词带上约束；
2. 本地兜底：关键词 → 公式模板；统计摘要措辞必须诚实；
3. 三条 AI 流程：成功标注来源 / 不可用先问 / 失败先问 / 同意后本地结果带"不是 AI"标签；
4. 本地事实收集（错误值、重复行、空单元格）不依赖 AI。
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from beeoffice.plugins.beesheet_ai_mixin import (                  # noqa: E402
    SheetAIMixin, build_audit_prompt, build_formula_prompt,
    build_sheet_context, build_summary_prompt, local_formula_hint,
    local_sheet_summary,
)


@pytest.fixture
def df():
    return pd.DataFrame({
        "名称": ["甲", "乙", "丙", "#DIV/0!"],
        "数量": [1, 2, 3, 4],
        "单价": [10.5, 20.0, None, 30.25],
    })


# ==================== 1. 上下文与提示词 ====================

def test_context_has_shape_headers_and_sample(df):
    context = build_sheet_context(df)

    assert "4 行 × 3 列" in context
    assert "名称" in context and "数量" in context
    assert "甲" in context, "要带样本行"
    assert "制表符分隔" in context


def test_context_gives_column_letters_and_real_row_numbers(df):
    """
    **实测教训**：第一版只给"制表符分隔的样本"，真模型就把"数量×单价"
    写成 `=A2*B2`（实际应是 `=C2*D2`）—— 它不知道哪列是 A/B/C。
    所以上下文**必须**给出列字母对应与真实行号。
    """
    context = build_sheet_context(df)

    assert "A: 名称" in context, context
    assert "B: 数量" in context, context
    assert "C: 单价" in context, context
    assert "数据从第 2 行开始" in context
    assert "\n2\t" in context, "样本行要带真实行号（第 2 行起）"


def test_context_never_sends_whole_table():
    """几十万行的表**绝不能整表发过去**（超上下文、也没必要）。"""
    big = pd.DataFrame({f"列{i}": range(50000) for i in range(10)})

    context = build_sheet_context(big, max_rows=5, max_cols=3)

    assert "50000 行 × 10 列" in context
    assert "另有" in context, "要说明还有多少没列出来"
    # 只应有 5 个样本行 + 少量说明行
    assert len(context.splitlines()) <= 12, len(context.splitlines())


def test_context_handles_empty_table():
    assert "没有数据" in build_sheet_context(pd.DataFrame())
    assert "没有数据" in build_sheet_context(None)


def test_formula_prompt_carries_context_and_bans_markdown():
    prompt = build_formula_prompt("数量列求和", "工作表共 4 行")

    assert "工作表共 4 行" in prompt
    assert "数量列求和" in prompt
    assert "不要带 markdown 代码块" in prompt, "否则用户没法直接粘贴"
    assert "不要编造列名" in prompt


def test_audit_prompt_says_facts_come_from_local_rules():
    prompt = build_audit_prompt("· 错误值：#DIV/0!（1 处）")

    assert "本地规则" in prompt
    assert "不要编造" in prompt
    assert "#DIV/0!" in prompt


def test_summary_prompt_demands_compression():
    prompt = build_summary_prompt("工作表共 4 行")
    assert "必须压缩" in prompt and "不要逐行复述" in prompt


# ==================== 2. 本地兜底 ====================

@pytest.mark.parametrize("text,expect", [
    ("把数量列求和", "SUM"),
    ("求平均值", "AVERAGE"),
    ("找出最大值", "MAX"),
    ("统计有多少条", "COUNT"),
    ("查找匹配", "VLOOKUP"),
    ("满足条件求和", "SUMIF"),
])
def test_local_formula_hint_matches_keywords(text, expect):
    formula, keyword = local_formula_hint(text)

    assert formula and expect in formula
    assert keyword, "要告诉用户是命中了哪个关键词"


def test_local_formula_hint_reports_miss():
    formula, keyword = local_formula_hint("随便写点跟公式无关的话")

    assert formula is None and keyword == ""


def test_local_summary_is_statistics_with_honest_wording(df):
    text = local_sheet_summary(df)

    assert "4 行 × 3 列" in text
    assert "数量" in text or "单价" in text
    assert "最大" in text and "缺失" in text


def test_local_summary_handles_empty():
    assert "没有数据" in local_sheet_summary(pd.DataFrame())


# ==================== 3. Mixin：三条流程 ====================

class StubClient:
    def __init__(self, available=True, result=(True, "AI 输出")):
        self.available = available
        self._result = result
        self.prompts = []
        self.last_source = "ai"

    def unavailable_reason(self):
        return "未配置接口地址。请在「帮助 → 🤖 AI 设置」里选择服务商。"

    def describe_source(self):
        return "AI 生成（llama3.2）" if self.last_source == "ai" else "本地规则"

    def chat(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return self._result


class FakeSheet(SheetAIMixin):
    """只测 AI 逻辑所需的最小宿主。"""

    def __init__(self, client, df=None):
        self._ai_client = client
        self.model = type("M", (), {"df": df if df is not None else pd.DataFrame()})()
        self.statuses = []
        self.shown = []

    def _set_status(self, message, timeout=3000):
        self.statuses.append(message)

    def _sheet_ai_show_text(self, title, text, note=""):
        self.shown.append((title, text, note))


@pytest.fixture
def sync_runner(monkeypatch):
    from beeoffice.plugins import beesheet_ai_mixin as module

    def run(fn, *args, on_result=None, on_error=None, **kwargs):
        try:
            result = fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            if on_error:
                on_error(str(e))
            return
        if on_result:
            on_result(result)

    monkeypatch.setattr(module.AsyncTaskManager, "run", staticmethod(run))


@pytest.fixture(autouse=True)
def _no_modal(monkeypatch):
    """拦截模态框（否则"征求同意"那步会把用例挂死）。"""
    from PySide6.QtWidgets import QMessageBox

    seen = {"question": [], "information": [], "warning": []}

    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda parent, title, text, *a, **k: (
            seen["question"].append((title, text)),
            QMessageBox.StandardButton.No)[-1]),
    )
    for name in ("information", "warning"):
        monkeypatch.setattr(
            QMessageBox, name,
            staticmethod(lambda *a, _n=name, **k: seen[_n].append(a)),
        )
    return seen


def test_ai_success_labels_source(sync_runner):
    client = StubClient(result=(True, "=SUM(B2:B5)\n说明：对数量列求和。"))
    sheet = FakeSheet(client, pd.DataFrame({"数量": [1, 2, 3]}))

    sheet._run_sheet_ai(
        "公式建议", "prompt",
        on_ai_text=lambda t: sheet.shown.append(("公式建议", t, "")),
        build_local=lambda: ("本地", "本地规则"),
    )

    assert sheet.shown, "AI 结果没有展示"
    assert any("AI 生成" in s for s in sheet.statuses), sheet.statuses


def test_ai_unavailable_asks_first_and_respects_no(sync_runner, _no_modal):
    """**不静默糊弄**：没有 AI 必须先问；用户说"否"就什么都不给。"""
    sheet = FakeSheet(StubClient(available=False))

    sheet._run_sheet_ai(
        "公式建议", "prompt",
        on_ai_text=lambda t: sheet.shown.append(("x", t, "")),
        build_local=lambda: ("本地公式", "本地规则"),
    )

    assert _no_modal["question"], "没有征求同意"
    assert not sheet.shown, f"用户没同意却展示了内容：{sheet.shown}"
    assert any("已取消" in s for s in sheet.statuses)


def test_ai_unavailable_local_result_is_labelled(sync_runner, _no_modal,
                                                 monkeypatch):
    """同意后才给本地结果，且必须写明"不是 AI 生成"。"""
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )
    sheet = FakeSheet(StubClient(available=False))

    sheet._run_sheet_ai(
        "公式建议", "prompt",
        on_ai_text=lambda t: sheet.shown.append(("x", t, "")),
        build_local=lambda: ("=SUM(范围)", "本地关键词匹配结果（不是 AI 理解）"),
    )

    assert sheet.shown, "同意后应给出本地结果"
    _, text, note = sheet.shown[-1]
    assert "不是 AI" in note, note
    assert any("不是 AI 生成" in s for s in sheet.statuses), sheet.statuses


def test_ai_failure_also_asks_first(sync_runner, _no_modal):
    sheet = FakeSheet(StubClient(result=(False, "API Key 无效（HTTP 401）")))

    sheet._run_sheet_ai(
        "表格摘要", "prompt",
        on_ai_text=lambda t: sheet.shown.append(("x", t, "")),
        build_local=lambda: ("本地统计", "本地规则"),
    )

    assert _no_modal["question"], "失败后也要先问"
    assert not sheet.shown


def test_local_builder_returning_nothing_reports_reason(sync_runner,
                                                        monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )
    sheet = FakeSheet(StubClient(available=False))

    sheet._run_sheet_ai(
        "公式建议", "prompt",
        on_ai_text=lambda t: sheet.shown.append(("x", t, "")),
        build_local=lambda: (None, "本地关键词匹配没找到对应函数"),
    )

    assert not sheet.shown
    assert any("没找到对应函数" in s for s in sheet.statuses), sheet.statuses


def test_ai_call_goes_through_async_runner(monkeypatch):
    from beeoffice.plugins import beesheet_ai_mixin as module

    used = {}

    def run(fn, *args, on_result=None, on_error=None, **kwargs):
        used["called"] = True

    monkeypatch.setattr(module.AsyncTaskManager, "run", staticmethod(run))
    sheet = FakeSheet(StubClient())

    sheet._run_sheet_ai("表格摘要", "prompt",
                        on_ai_text=lambda t: None,
                        build_local=lambda: ("x", "y"))

    assert used.get("called") is True


# ==================== 4. 本地事实收集（不依赖 AI）====================

def test_collect_findings_reports_facts(df):
    sheet = FakeSheet(StubClient(), df)

    findings = sheet._collect_local_findings()

    assert "#DIV/0!" in findings, findings
    assert "空单元格" in findings or "空" in findings, findings


def test_collect_findings_reports_duplicates():
    dup = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"]})
    sheet = FakeSheet(StubClient(), dup)

    assert "重复" in sheet._collect_local_findings()


def test_collect_findings_handles_clean_table():
    clean = pd.DataFrame({"a": [1, 2, 3]})
    sheet = FakeSheet(StubClient(), clean)

    assert "没有发现明显问题" in sheet._collect_local_findings()


def test_collect_findings_handles_empty_table():
    sheet = FakeSheet(StubClient(), pd.DataFrame())
    assert "没有数据" in sheet._collect_local_findings()


# ==================== 5. 入口存在 ====================

def test_view_has_ai_button_and_entries(qtbot):
    from beeoffice.plugins.beesheet import BeeSheetView

    view = BeeSheetView()
    qtbot.addWidget(view)
    try:
        assert getattr(view, "_ai_btn", None) is not None, "工具栏没有 AI 按钮"
        for name in ("_ai_suggest_formula", "_ai_explain_issues",
                     "_ai_summarize_sheet", "_show_sheet_ai_menu",
                     "_open_ai_settings"):
            assert callable(getattr(view, name, None)), name
    finally:
        view.close()


def test_open_ai_settings_clears_cached_client(monkeypatch, qtbot):
    """改了配置要让缓存失效，否则用户以为没生效。"""
    import beeoffice.ai_settings as ai_module

    monkeypatch.setattr(ai_module, "show_ai_settings",
                        lambda parent=None, settings=None: True)

    from beeoffice.plugins.beesheet import BeeSheetView

    view = BeeSheetView()
    qtbot.addWidget(view)
    try:
        view._ai_client = StubClient()
        view._open_ai_settings()
        assert view._ai_client is None
    finally:
        view.close()
