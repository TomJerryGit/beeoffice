# tests/fidelity/test_i18n_ratchet.py
"""
i18n 棘轮门禁：**硬编码中文文案只许减少、不许增加**。

背景（分析报告 §2.3）：`tr()` 包装率约 11%，`tr` 只出现在 app.py/menus.py。
在"全面 tr 化 vs 中文优先"决策之前，先阻止新增硬编码，避免债继续变大。
口径与工具见 `tools/i18n_audit.py`。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.i18n_audit import (   # noqa: E402
    BASELINE, PACKAGE, check, load_baseline, scan,
)


def test_hardcoded_chinese_does_not_increase():
    assert BASELINE.is_file(), "基线缺失：请运行 python tools/i18n_audit.py --write-baseline"
    current = scan(PACKAGE)
    baseline = load_baseline()
    result = check(current, baseline)
    assert result["ok"], (
        f"硬编码中文串增加了 {result['delta']} 处"
        f"（当前 {result['current_total']} / 基线 {result['baseline_total']}）。\n"
        f"新增文件: {result['new_files']}\n"
        f"变化文件: {result['delta_files']}\n"
        "请用 tr() 包装新增文案；若确属有意（如数据/日志口径调整），"
        "在 PR 说明理由后更新基线。"
    )


def test_baseline_snapshot_is_readable():
    baseline = load_baseline()
    assert baseline.get("total", 0) > 0
    assert isinstance(baseline.get("by_file"), dict) and baseline["by_file"]
