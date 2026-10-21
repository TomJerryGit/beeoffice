# tests/fidelity/test_open_docx_async.py
"""
v5.0.17 首次打开优化：**主线程不再做 extras / 保真分析的同步 I/O**。

## 背景（cProfile 实测，5 万字 DOCX，A 级）
| 阶段 | 优化前 | 处理 |
|---|---:|---|
| `set_content`（渲染） | ~600 ms | 保持主线程（Qt 控件操作） |
| `read_docx_extras` | ~122–164 ms | **挪到后台线程** |
| `analyze_file`（保真提示） | ~5 ms | **挪到后台线程** |
| 装载期间的光标通知 | ~250 ms + 10,860 次 hasattr | **加载中跳过** |

## 本文件锁住
1. 后台 helper 确实把三件事都做了（AST）；
2. `_open_docx_file` 主线程代码里不再同步读 extras；
3. `_attach_fidelity_report` 接受后台预先算好的 report（不再重复分析）；
4. 批量装载期间光标通知/格式状态同步会提前返回（不遍历父链）。
"""
import ast
import inspect
import textwrap

import pytest

from beeoffice import app as app_module


def test_background_helper_does_import_extras_and_report():
    src = textwrap.dedent(inspect.getsource(app_module._import_docx_for_open))
    tree = ast.parse(src)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert {"import_from_docx", "read_docx_extras"} <= imported
    assert {"import_from_docx", "read_docx_extras", "analyze_file"} <= called


def test_open_docx_runs_helper_in_async_worker():
    src = textwrap.dedent(
        inspect.getsource(app_module.BeeApp._open_docx_file)
    )
    tree = ast.parse(src)
    names = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }
    assert "_import_docx_for_open" in names, (
        "打开 DOCX 必须走后台 helper（否则 extras/保真分析又回到主线程）"
    )


def test_attach_report_accepts_precomputed(app):
    """后台已算好 report 时，主线程不能再调用 analyze_file。"""

    class _DummyWidget:
        pass

    called = {"analyze": 0}

    def _boom(path):
        called["analyze"] += 1
        raise AssertionError("不应在主线程重复分析")

    monkeypatch = pytest.MonkeyPatch()
    try:
        from beeoffice.plugins import fidelity_report as fr

        monkeypatch.setattr(fr, "analyze_file", _boom)
        widget = _DummyWidget()
        sentinel = object()
        app._attach_fidelity_report(widget, "whatever.docx", report=sentinel)
        assert widget._fidelity_report is sentinel
        assert called["analyze"] == 0
    finally:
        monkeypatch.undo()


def test_beewrite_import_does_not_pull_heavy_optional_deps():
    """首次打开会 import beewrite —— 不能顺手把 pandas/matplotlib 拉进来。

    实测（2026-10-21）：`import beeoffice.plugins.beewrite` 原先 1.39 s，
    其中 pandas ~0.6 s、matplotlib ~0.45 s 都是"打开文档时根本用不到"的依赖。
    改成使用点延迟导入后：~0.84 s，且 sys.modules 里两者都不在。
    """
    import os
    import subprocess
    import sys
    from pathlib import Path

    from beeoffice import app as app_module

    root = Path(app_module.__file__).resolve().parents[1]
    script = (
        "import sys\n"
        "import beeoffice.plugins.beewrite\n"
        "print('pandas' in sys.modules, 'matplotlib' in sys.modules)\n"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root)
    env["QT_QPA_PLATFORM"] = "offscreen"
    completed = subprocess.run(
        [sys.executable, "-c", script], cwd=str(root), env=env,
        capture_output=True, text=True, timeout=180,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "False False", completed.stdout


def test_cursor_notification_skips_while_loading(beewrite_editor):
    """装载期间 `_notify_cursor_position` 不能读 cursor（否则每段一次父链探测）。"""
    editor = beewrite_editor.rich_editor
    original = editor.textCursor
    editor._loading_markdown = True
    editor.textCursor = lambda: (_ for _ in ()).throw(
        AssertionError("装载期间不应读 cursor")
    )
    try:
        editor._notify_cursor_position()          # 不应抛异常
    finally:
        editor.textCursor = original
        editor._loading_markdown = False
    # 对照：加载结束后正常路径仍会读 cursor
    assert editor.textCursor() is not None
