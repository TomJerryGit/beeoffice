# tests/unit/test_plugin_discovery_is_lazy.py
"""
优化规划 §2.1 回归：插件发现不得为了"找插件"而 import 整个 plugins 目录。

原缺陷
------
`PluginManager.discover_plugins()` 对 beeoffice/plugins/ 下**全部** 84 个模块
逐个 `importlib.import_module()`，把 pandas / matplotlib / PyMuPDF /
QtWebEngine 统统拉起来。实测 `discover_plugins()` 需 **2487 ms**
（冷启动 **9110 ms**），而这段代码由 app.py 在窗口 show() 之后于主线程同步
执行 —— 界面冻结约 7~9 秒。

关键实测事实（决定了修复方式）：
  - `pkgutil.iter_modules` 只扫描文件名，84 个模块名耗时 10.6 ms；
  - 4 个插件壳（`*_plugin.py`）各自只要 1~3 ms，且**不拉任何重依赖**
    （重依赖都在它们的 `create_widget()` 里延迟导入）。

所以只要不 import 其余 80 个实现模块即可，无需改动插件架构。

本文件的第 3 条用**全新解释器子进程**断言"发现过程没有引入重依赖"——
这一点必须在干净环境里测，否则会被本进程已有的 import 污染。
"""
import json
import subprocess
import sys
import textwrap
from pathlib import Path


from beeoffice.plugin_manager import PluginManager

ROOT = Path(__file__).parent.parent.parent.resolve()

#: 一旦这些模块出现在 sys.modules，就说明启动被拖慢了
HEAVY_MODULES = (
    "matplotlib",
    "fitz",
    "pandas",
    "docx",
    "pptx",
    "PySide6.QtWebEngineWidgets",
)

#: 在干净解释器里跑：只做插件发现，报告耗时与 sys.modules 里的重依赖
_PROBE = textwrap.dedent(
    """
    import json, os, sys, time
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication([])

    from beeoffice.plugin_manager import PluginManager

    HEAVY = %r
    before = {m for m in sys.modules if m in HEAVY}
    mgr = PluginManager(None)
    t0 = time.perf_counter()
    mgr.discover_plugins()
    elapsed_ms = (time.perf_counter() - t0) * 1000
    after = {m for m in sys.modules if m in HEAVY}

    print("RESULT" + json.dumps({
        "ms": elapsed_ms,
        "heavy_before": sorted(before),
        "heavy_after": sorted(after),
        "plugin_count": mgr.count(),
        "plugin_names": [p.name for p in mgr.plugins],
        "stats": mgr.last_discovery_stats,
    }))
    """
) % (HEAVY_MODULES,)


def _run_probe(tmp_path) -> dict:
    """
    在独立解释器里运行探针。

    输出写到文件而不是管道：受限沙箱环境下管道可能不可用。
    """
    out_file = tmp_path / "probe_stdout.txt"
    with open(out_file, "w", encoding="utf-8") as fh:
        subprocess.run(
            [sys.executable, "-c", _PROBE],
            cwd=str(ROOT),
            stdout=fh,
            stderr=subprocess.STDOUT,
            timeout=300,
        )
    text = out_file.read_text(encoding="utf-8", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.startswith("RESULT")]
    assert lines, f"探针未产出结果：\n{text[-3000:]}"
    return json.loads(lines[-1][len("RESULT"):])


# ==================== 1. 只把插件壳当作候选 ====================

def test_candidate_names_are_only_plugin_shells(qapp):
    """候选模块应恰好是 4 个内置插件壳，而不是 84 个模块。"""
    mgr = PluginManager(None)
    names = set(mgr.iter_plugin_module_names())

    assert names == {
        "beewrite_plugin",
        "beesheet_plugin",
        "beeshow_plugin",
        "pdf_annotator_plugin",
    }, f"候选集不符合预期: {sorted(names)}"

    stats = mgr.last_discovery_stats
    assert stats["scanned"] >= 80, "应扫描到全部模块名"
    assert stats["candidates"] <= 10, "候选不应多"
    assert stats["skipped"] >= 70, f"应跳过绝大多数实现模块，实际 {stats}"


# ==================== 2. 兜底：换名字的插件仍能被发现 ====================

def test_source_scan_finds_differently_named_plugin(tmp_path):
    """
    插件市场的安装逻辑不保证文件名以 _plugin 结尾，因此必须有源码兜底信号。
    """
    weird = tmp_path / "my_cool_extension.py"
    weird.write_text(
        "from beeoffice.plugin_base import Plugin\n"
        "class MyExtension(Plugin):\n"
        "    name = 'x'\n",
        encoding="utf-8",
    )
    assert PluginManager._source_declares_plugin(weird) is True

    plain = tmp_path / "not_a_plugin.py"
    plain.write_text("VALUE = 1\n", encoding="utf-8")
    assert PluginManager._source_declares_plugin(plain) is False

    assert PluginManager._source_declares_plugin(tmp_path / "missing.py") is False


# ==================== 3. 关键：发现过程不得引入重依赖 ====================

def test_discovery_does_not_import_heavy_dependencies(tmp_path):
    """
    在全新解释器里断言：discover_plugins() 之后，重依赖仍然没有出现。

    这正是"启动冻结 9 秒"的根因，必须在干净进程里验证。
    """
    result = _run_probe(tmp_path)

    assert result["plugin_count"] == 4, (
        f"应发现 4 个内置插件，实际 {result['plugin_count']}: "
        f"{result['plugin_names']}"
    )

    still_clean = set(result["heavy_after"]) - set(result["heavy_before"])
    assert not still_clean, (
        f"插件发现引入了重依赖，启动会被拖慢: {sorted(still_clean)}"
    )


def test_discovery_is_fast(tmp_path):
    """
    耗时断言（宽松阈值，避免 CI 抖动误报）。

    基线：本机 2487 ms（冷启动 9110 ms）；修复后约 190 ms。
    这里设 1500 ms，只拦"退化回全量 import"这种数量级问题。
    """
    result = _run_probe(tmp_path)
    assert result["ms"] < 1500, (
        f"discover_plugins() 耗时 {result['ms']:.0f} ms，疑似退化回全量 import"
    )
