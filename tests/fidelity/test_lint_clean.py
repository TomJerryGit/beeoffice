# tests/fidelity/test_lint_clean.py
"""
把"未用导入"钉成门禁：F401 / TC005 必须**保持为零**。

## 为什么值得单独一条门禁
第十一批清理了全仓 **187 处** F401（另有 10 处 try/except 内的残留手工处理），
过程中暴露了两件必须记住的事：

1. **`ruff --fix` 会删掉"刻意导入"**：它把 `tests/test_smoke_beeshow.py` 里
   `ICON_LIBRARY / TEMPLATE_LIBRARY / LAYOUT_CSS / _PlayWindow` 删了 ——
   而那几个名字正是那条冒烟测试要验证的**兼容契约**
   （拆分模块后旧名字仍可 import）。现在改成**补断言**而不是 noqa：
   既消掉 F401，又真正验证契约。
2. **会留下空块**：`beesheet_commands.py` 的 `if TYPE_CHECKING: pass`
   （里面唯一导入被删）→ 由 TC005 抓出并修掉。

所以这条门禁守两件事：不再新增未用导入、也不留下空块。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run_ruff(select: str):
    return subprocess.run(
        [sys.executable, "-m", "ruff", "check", "beeoffice", "tests", "tools",
         "--select", select, "--output-format", "concise"],
        cwd=str(ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=300,
    )


def test_no_unused_imports():
    """F401 必须为零（新增未用导入会在这里被拦下）。"""
    result = _run_ruff("F401")
    if result.returncode == 0:
        return
    lines = [ln for ln in (result.stdout or "").splitlines() if "F401" in ln]
    assert not lines, "存在未使用的导入：\n" + "\n".join(lines[:20])


def test_no_empty_type_checking_block():
    """TC005：`--fix` 删空 `if TYPE_CHECKING:` 块会留下空块，这里守。"""
    result = _run_ruff("TC005")
    if result.returncode == 0:
        return
    lines = [ln for ln in (result.stdout or "").splitlines() if "TC005" in ln]
    assert not lines, "存在空的类型检查块：\n" + "\n".join(lines[:20])
