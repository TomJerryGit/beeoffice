# tests/unit/test_version_consistency.py
"""
优化规划 §4.3 回归：版本号与许可证声明必须与实际一致。

背景（引入本测试前的真实状态）
------------------------------
- README 的版本徽章写着 **5.0.2**，而 `beeoffice/__version__.py` 是 **5.0.7**
  —— 差 5 个补丁版本，此前**没有任何检查**会发现；
- README 的许可证徽章链接到 `LICENSE`，但**该文件根本不存在**；
- CHANGELOG 已有 `[5.0.8]` 条目，而 `__version__.py` 还停在 5.0.7。

现在：`__version__.py` 是唯一来源，`tools/sync_version.py` 负责核对，
本文件把它接进测试套件（CI 会跑）。
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VERSION_FILE = ROOT / "beeoffice" / "__version__.py"
README = ROOT / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"
LICENSE = ROOT / "LICENSE"


def _source_version() -> str:
    text = VERSION_FILE.read_text(encoding="utf-8")
    m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text,
                  re.MULTILINE)
    assert m, "__version__.py 里没有 __version__ 赋值"
    return m.group(1)


def test_source_version_is_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", _source_version()), (
        f"版本号不符合 SemVer: {_source_version()}"
    )


def test_readme_badge_matches_source_version():
    text = README.read_text(encoding="utf-8")
    m = re.search(r"badge/Version-(\d+\.\d+\.\d+)-", text)
    assert m, "README 缺少版本徽章"
    assert m.group(1) == _source_version(), (
        f"README 徽章版本 {m.group(1)} 与唯一来源 {_source_version()} 不一致 —— "
        f"运行 python tools/sync_version.py --write 修正"
    )


def test_changelog_latest_entry_matches_source_version():
    text = CHANGELOG.read_text(encoding="utf-8")
    m = re.search(r"^##\s*\[(\d+\.\d+\.\d+)\]", text, re.MULTILINE)
    assert m, "CHANGELOG 里找不到版本条目"
    assert m.group(1) == _source_version(), (
        f"CHANGELOG 最新条目 [{m.group(1)}] 与唯一来源 "
        f"{_source_version()} 不一致"
    )


def test_source_version_file_has_no_patch_history():
    """
    §4.3：不要在源码 docstring 里写补丁说明（历史归 CHANGELOG / git）。

    这里只对本文件做断言——全仓 45/118 个模块仍有余留，见规划 §4.3。
    """
    text = VERSION_FILE.read_text(encoding="utf-8")
    assert "版本历史" not in text, (
        "__version__.py 又内嵌了版本历史，请改为指向 CHANGELOG"
    )


# ==================== 许可证：徽章声明与实际文件必须一致 ====================

def test_license_file_exists():
    """README 的 License 徽章链接到 LICENSE，所以它必须存在。"""
    assert LICENSE.is_file(), (
        "README 声明 MIT 并链接 LICENSE，但该文件不存在（徽章是空头承诺）"
    )


def test_license_is_mit_and_matches_readme_badge():
    text = LICENSE.read_text(encoding="utf-8")
    assert text.lstrip().startswith("MIT License"), "LICENSE 不是 MIT 文本"

    readme = README.read_text(encoding="utf-8")
    assert "License-MIT" in readme, "README 徽章应声明 MIT，与 LICENSE 一致"


def test_license_has_copyright_holder():
    text = LICENSE.read_text(encoding="utf-8")
    assert re.search(r"Copyright \(c\) \d{4} \S+", text), (
        "LICENSE 缺少版权行"
    )


# ==================== 同步工具本身 ====================

def test_sync_version_tool_reports_consistent():
    """工具默认检查模式应在当前仓库上通过（退出码 0）。"""
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "sync_version.py")],
        cwd=str(ROOT), capture_output=True, text=True,
        timeout=120, encoding="utf-8", errors="replace",
    )
    assert proc.returncode == 0, (
        f"sync_version.py 报告版本号不一致：\n{proc.stdout}\n{proc.stderr}"
    )
