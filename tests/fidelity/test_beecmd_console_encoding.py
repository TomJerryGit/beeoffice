# tests/fidelity/test_beecmd_console_encoding.py
"""
打包 exe 的 Windows 控制台编码回归：**GBK 代码页下 print(emoji) 不能崩**。

实测（2026-10-20，PyInstaller onefile exe，默认 cp936 控制台）：
`beecmd.exe convert ...` 在最后一行 `print("✅ …")` 抛
`UnicodeEncodeError: 'gbk' codec can't encode character '\\u2705'`，
命令本身成功却以 exit 1 结束 —— 外部用户会以为工具坏了。
"""
import io
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _StrictGBKStream(io.TextIOWrapper):
    """模拟 Windows 控制台：GBK 编码 + errors='strict'。"""


def test_console_safe_makes_gbk_print_not_crash(monkeypatch, capsys):
    from beeoffice import beecmd

    raw = io.BytesIO()
    gbk_stream = io.TextIOWrapper(raw, encoding="gbk", errors="strict",
                                  write_through=True)
    monkeypatch.setattr(sys, "stdout", gbk_stream)
    monkeypatch.setattr(sys, "stderr", gbk_stream)

    beecmd._make_console_safe()
    # 这两行在修复前会抛 UnicodeEncodeError
    print("✅ 已清洗完成")
    print("❌ 失败示例")

    text = raw.getvalue()
    assert text  # 确实写出了内容，且没有抛异常
    # 恢复 capsys 捕获（monkeypatch 会自动恢复，但这里主动断言无残留异常）


def test_main_reconfigures_console(monkeypatch):
    """main() 必须先做控制台兜底再跑命令（--version 是最短路径）。"""
    from beeoffice import beecmd

    called = {"safe": 0}
    original = beecmd._make_console_safe

    def spy():
        called["safe"] += 1
        original()

    monkeypatch.setattr(beecmd, "_make_console_safe", spy)
    # argparse 的 --version 会 SystemExit(0)，这是正常退出路径
    with pytest.raises(SystemExit) as exc:
        beecmd.main(["--version"])
    assert exc.value.code == 0
    assert called["safe"] == 1
