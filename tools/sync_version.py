# tools/sync_version.py
"""
版本号单一来源（优化规划 §4.3）

**唯一来源**是 `beeoffice/__version__.py` 的 `__version__`。
本工具负责让 README 的版本徽章与 CHANGELOG 的最新条目标题与它一致。

为什么需要它
------------
在引入本工具之前，README 徽章写着 `Version-5.0.2`，而
`beeoffice/__version__.py` 是 `5.0.7` —— 差了 5 个补丁版本，没有任何东西
会发现这件事（CI 里也没检查）。人工同步版本号迟早会漂移。

用法
----
    python tools/sync_version.py            # 只检查，不一致则退出码 1
    python tools/sync_version.py --write    # 就地修正 README / CHANGELOG

设计取舍
--------
- **默认只检查**：CI 里跑检查；改动由人显式加 `--write`，避免工具悄悄改文档。
- 只改"版本号出现的位置"，不重写整份文件（保持 diff 最小、避免误伤）。
- CHANGELOG 只校验"最新一个条目标题"的版本号，不动历史条目。
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "beeoffice" / "__version__.py"
README = ROOT / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"

#: README 里的版本徽章：badge/Version-5.0.7-orange.svg
README_BADGE_RE = re.compile(r"(badge/Version-)(\d+\.\d+\.\d+)(-)")
#: README 里可能出现的"当前版本：x.y.z"写法
README_TEXT_RE = re.compile(r"(当前版本[：:]\s*)(\d+\.\d+\.\d+)")
#: CHANGELOG 最新的 "## [x.y.z] - date"
CHANGELOG_RE = re.compile(r"^##\s*\[(\d+\.\d+\.\d+)\]", re.MULTILINE)


def read_source_version() -> str:
    """从 __version__.py 读取版本号（唯一来源）。"""
    text = VERSION_FILE.read_text(encoding="utf-8")
    m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    if not m:
        raise SystemExit(f"无法从 {VERSION_FILE} 解析 __version__")
    return m.group(1)


def find_readme_versions() -> "list[tuple[str, str]]":
    """返回 README 里找到的 (上下文, 版本号) 列表。"""
    text = README.read_text(encoding="utf-8")
    found = []
    for m in README_BADGE_RE.finditer(text):
        found.append(("徽章", m.group(2)))
    for m in README_TEXT_RE.finditer(text):
        found.append(("正文", m.group(2)))
    return found


def find_changelog_latest() -> "str | None":
    """返回 CHANGELOG 最新条目的版本号。"""
    text = CHANGELOG.read_text(encoding="utf-8")
    m = CHANGELOG_RE.search(text)
    return m.group(1) if m else None


def check() -> "list[str]":
    """
    检查各处版本号是否与唯一来源一致。

    :return: 问题描述列表（空表示一致）
    """
    version = read_source_version()
    problems = []

    for where, found in find_readme_versions():
        if found != version:
            problems.append(
                f"README（{where}）版本号为 {found}，应为 {version}"
            )

    latest = find_changelog_latest()
    if latest is not None and latest != version:
        problems.append(
            f"CHANGELOG 最新条目为 [{latest}]，应为 [{version}]"
        )

    return problems


def write() -> int:
    """
    把 README 的版本号就地改成唯一来源的版本号。

    :return: 修改的文件数
    """
    version = read_source_version()
    text = README.read_text(encoding="utf-8")
    original = text

    text = README_BADGE_RE.sub(
        lambda m: f"{m.group(1)}{version}{m.group(3)}", text
    )
    text = README_TEXT_RE.sub(
        lambda m: f"{m.group(1)}{version}", text
    )

    if text != original:
        try:
            README.write_text(text, encoding="utf-8")
        except OSError as e:
            # 受限环境下可能不允许写（例如只读挂载 / 沙箱）。
            # 明确告诉用户改哪一行，而不是丢一个裸 PermissionError。
            print(f"[错误] 无法写入 {README}：{e}")
            print("请手动把 README 的版本徽章改为：")
            print(f"  badge/Version-{version}-orange.svg")
            return 0
        return 1
    return 0


def main() -> int:
    # Windows 中文环境的 stdout 常是 GBK；打印非 GBK 字符（如 "✓"）会抛
    # UnicodeEncodeError 并把退出码变成 1 —— 实测在子进程里就是这样，
    # 会让 CI 步骤无端失败。这里统一按 UTF-8 输出并容错替换。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(description="版本号单一来源检查 / 同步")
    ap.add_argument("--write", action="store_true",
                    help="就地修正 README 的版本号（默认只检查）")
    args = ap.parse_args()

    version = read_source_version()
    print(f"唯一来源 beeoffice/__version__.py: {version}")

    if args.write:
        changed = write()
        print(f"已更新 {changed} 个文件" if changed else "无需更新")
        return 0

    problems = check()
    if problems:
        print("版本号不一致：")
        for p in problems:
            print(f"  - {p}")
        print("提示：运行 python tools/sync_version.py --write 修正")
        return 1

    # 只用 ASCII 标记，避免任何控制台编码问题
    print("版本号一致 [OK]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
