# tests/unit/test_i18n_audit.py
"""`tools/i18n_audit.py`（硬编码中文棘轮）的回归 —— 纯逻辑，不依赖 Qt。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.i18n_audit import build_report, check, load_baseline, scan   # noqa: E402


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_scan_counts_only_hardcoded_ui_text(tmp_path):
    """
    计入：普通中文串（UI 文案）；
    不计入：docstring、`tr()` 参数、`logging.*` / `print` 参数。
    """
    pkg = tmp_path / "pkg"
    _write(pkg / "a.py", '''
"""模块 docstring 中文不计入。"""
import logging


class A:
    """类 docstring 中文不计入。"""

    def f(self):
        label = "中文标签"                    # 计入 1
        tr("key", "中文默认值")               # tr 参数不计入
        logging.info("中文日志")              # 日志不计入
        print("中文控制台")                   # 控制台不计入
        return label
''')
    _write(pkg / "b.py", '''
from PySide6.QtWidgets import QLabel

def build():
    w = QLabel("第二处中文")
    w.setWindowTitle("窗口标题")
    return w
''')
    result = scan(pkg)
    assert result["total"] == 3, result
    counts = result["by_file"]
    assert any(name.endswith("a.py") and c == 1 for name, c in counts.items())
    assert any(name.endswith("b.py") and c == 2 for name, c in counts.items())


def test_scan_ignores_non_python_and_pycache(tmp_path):
    pkg = tmp_path / "pkg"
    _write(pkg / "a.py", 'X = "中文"\n')
    _write(pkg / "notes.txt", "中文")
    _write(pkg / "__pycache__" / "junk.py", 'X = "中文缓存"\n')
    assert scan(pkg)["total"] == 1


def test_check_passes_when_not_increased_and_fails_when_increased(tmp_path):
    scan_result = {"total": 10, "by_file": {"a.py": 10}}
    assert check(scan_result, {"total": 10})["ok"] is True
    assert check(scan_result, {"total": 11})["ok"] is True   # 减少了也通过
    worse = check(scan_result, {"total": 9})
    assert worse["ok"] is False
    assert worse["delta"] == 1


def test_check_reports_delta_files_and_top(tmp_path):
    current = {"total": 12, "by_file": {"a.py": 5, "b.py": 7}}
    baseline = {"total": 12, "by_file": {"a.py": 2, "b.py": 10}}
    result = check(current, baseline)
    assert result["ok"] is True
    assert result["top_files"][0][0] == "b.py"
    deltas = {name: (before, after) for name, before, after in result["delta_files"]}
    assert deltas["a.py"] == (2, 5)
    assert deltas["b.py"] == (10, 7)


def test_report_contains_verdict_and_top_files():
    result = {
        "ok": False, "current_total": 5, "baseline_total": 3, "delta": 2,
        "top_files": [("a.py", 5)], "new_files": [], "delta_files": [],
    }
    report = build_report(result, {"total": 3})
    assert "未通过" in report or "❌" in report or "增加" in report
    assert "`a.py`" in report
    assert "两条路线" in report


def test_baseline_file_is_valid_snapshot():
    baseline = load_baseline()
    assert baseline["total"] > 0
    assert isinstance(baseline.get("by_file"), dict) and baseline["by_file"]
    assert all("/" in key or key.endswith(".py") for key in baseline["by_file"])
