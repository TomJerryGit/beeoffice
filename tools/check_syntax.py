# -*- coding: utf-8 -*-
"""
BeeOffice 语法编译检查工具

用途（路线图 WP-04 / WP-08）：
    在没有 PySide6 的机器上，也能在 30 秒内发现"整包 import 不了"的问题。
    历史教训：beesheet_engine.py 第 1310 行一个孤立反斜杠，让整个蜜算模块
    无法编译；而 plugin_manager 用 except 吞掉了这个错误，表现为"功能凭空消失"。
    这类问题本该由 CI 的 import smoke 拦住。

用法：
    python tools/check_syntax.py            # 检查 beeoffice/ tests/ tools/
    python tools/check_syntax.py --all      # 连仓库根目录的脚本一起检查

退出码：
    0  全部通过
    1  存在语法错误（输出文件名 + 行号 + 原因）
"""
import sys
from pathlib import Path

try:
    from _console import enable_utf8_output
    enable_utf8_output()
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent

# 默认检查范围（tests/ 覆盖测试代码本身）
DEFAULT_DIRS = ("beeoffice", "tests", "tools")

# 明确跳过的目录
SKIP_PARTS = {"__pycache__", ".pytest_cache", "backup", "build", "dist", ".git", "docs"}


def iter_py_files(base: Path, include_root: bool = False):
    """遍历待检查的 .py 文件。"""
    roots = []
    if include_root:
        roots.extend(p for p in base.glob("*.py"))
    for name in DEFAULT_DIRS:
        d = base / name
        if d.is_dir():
            roots.extend(d.rglob("*.py"))
    for p in roots:
        if any(part in SKIP_PARTS for part in p.parts):
            continue
        yield p


def check_file(path: Path):
    """编译单个文件，返回错误描述或 None。"""
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # 源码里有非 UTF-8 字节也算问题，单独报出来
        return "非 UTF-8 编码"
    try:
        compile(source, str(path), "exec")
    except SyntaxError as e:
        return f"第 {e.lineno} 行: {e.msg}"
    except ValueError as e:  # 例如源码里出现 NUL 字节
        return f"ValueError: {e}"
    return None


def main(argv):
    include_root = "--all" in argv
    failures = []
    total = 0
    for p in iter_py_files(ROOT, include_root):
        total += 1
        err = check_file(p)
        if err:
            failures.append((p, err))

    for p, err in failures:
        try:
            rel = p.relative_to(ROOT)
        except ValueError:
            rel = p
        print(f"[FAIL] {rel} -> {err}")

    print(f"\n检查 {total} 个文件，失败 {len(failures)} 个")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
