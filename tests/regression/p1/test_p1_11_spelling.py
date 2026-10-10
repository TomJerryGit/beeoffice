# tests/regression/p1/test_p1_11_spelling.py
"""
P1-11 回归：beewrite_* 文件头注释拼写正确

背景：
  10 个 beewrite_* 文件的头注释把 "beewrite_" 拼成了 "bewrite_"，
  少一个 e。虽然不影响运行，但容易误导搜索。

修复：
  文件头注释统一为正确的 "beewrite_"。

测试策略：
  1. 静态扫描 beewrite_*.py，检查 docstring 里没有 "bewrite_"
  2. 磁盘上不存在 bewrite_*.py 文件
"""
import re
from pathlib import Path


PLUGINS_DIR = (
    Path(__file__).parent.parent.parent.parent
    / "beeoffice" / "plugins"
)


def test_no_bewrite_typo_in_docstrings():
    """P1-11：beewrite_*.py 的 docstring 不应出现 bewrite_（少一个 e）。"""
    files = sorted(PLUGINS_DIR.glob("beewrite_*.py"))
    assert files, f"未找到 beewrite_*.py，目录: {PLUGINS_DIR}"

    problems = []
    for f in files:
        text = f.read_text(encoding="utf-8")
        for m in re.finditer(r"(?<!b)bewrite_", text):
            line_no = text[:m.start()].count("\n") + 1
            problems.append(f"{f.name}:{line_no}")

    assert not problems, (
        "P1-11：以下位置有 bewrite_ 拼写错误：\n"
        + "\n".join(f"  {p}" for p in problems)
    )


def test_no_bewrite_files_on_disk():
    """P1-11：磁盘上不应存在 bewrite_*.py（拼错的文件名）。"""
    wrong = list(PLUGINS_DIR.glob("bewrite_*.py"))
    assert not wrong, (
        "P1-11：发现拼写错误的文件：\n"
        + "\n".join(f"  {f.name}" for f in wrong)
    )
