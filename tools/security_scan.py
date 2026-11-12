"""BeeOffice 安全扫描：只匹配真实的动态执行/反序列化模式。

规则（AST，不是正则）：
  - 裸 exec(...)          → 高危
  - 裸 eval(...)          → 高危；若所在函数有 AST 白名单 + 空 builtins，标为 guarded
  - pickle.load/loads    → 高危
  - subprocess shell=True → 高危

默认排除 tests/、dist/、build/、release-archive/、虚拟环境，避免把
Qt 的 dialog.exec()、测试假实现和第三方依赖算进去。

用法：
    python tools/security_scan.py
    python tools/security_scan.py --json
    python tools/security_scan.py --root beeoffice --include-tests
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

EXCLUDED_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".venv", "venv", "env", "node_modules",
    "tests", "test", "dist", "build", "release-archive",
}
SKIP_DIRS_ALWAYS = {".git", "__pycache__", ".venv", "venv", "node_modules"}
DYNAMIC_NAMES = {"exec", "eval"}
PICKLE_CALLS = {"load", "loads"}
SEVERITY_ORDER = {"high": 3, "medium": 2, "guarded": 1, "info": 0}


@dataclass
class Finding:
    kind: str
    path: str
    line: int
    severity: str
    guarded: bool = False
    detail: str = ""


def _aliases(tree: ast.AST):
    """收集 pickle / subprocess 的 import 别名。"""
    pickle_mods = {"pickle"}
    pickle_funcs = set()
    subprocess_mods = {"subprocess"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "pickle":
                    pickle_mods.add(a.asname or a.name)
                if a.name == "subprocess":
                    subprocess_mods.add(a.asname or a.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "pickle":
            for a in node.names:
                pickle_funcs.add(a.asname or a.name)
    return pickle_mods, pickle_funcs, subprocess_mods


def _parent_function(tree: ast.AST):
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return parents


def _enclosing_function(node, parents):
    cur = parents.get(node)
    while cur is not None:
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return cur
        cur = parents.get(cur)
    return None


def _is_guarded_eval(fn, source: str) -> bool:
    if fn is None:
        return False
    segment = ast.get_source_segment(source, fn) or ""
    # 只认“AST 白名单 + 空 builtins”的明确加固模式，不按注释/名字猜测
    return (
        "ast.parse" in segment
        and "__builtins__" in segment
        and ("allowed_nodes" in segment or "allowed_calls" in segment)
    )


def _is_attr_chain(node, mods: set[str], attrs: set[str]) -> bool:
    if not isinstance(node, ast.Attribute) or node.attr not in attrs:
        return False
    value = node.value
    while isinstance(value, ast.Attribute):
        value = value.value
    return isinstance(value, ast.Name) and value.id in mods


def scan_source(path: Path):
    source = path.read_text(encoding="utf-8", errors="ignore")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    pickle_mods, pickle_funcs, subprocess_mods = _aliases(tree)
    parents = _parent_function(tree)
    findings: list[Finding] = []
    rel = str(path)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        # 裸 exec / eval，不匹配 dialog.exec()
        if isinstance(fn, ast.Name) and fn.id in DYNAMIC_NAMES:
            guarded = False
            if fn.id == "eval":
                fn_node = _enclosing_function(node, parents)
                guarded = _is_guarded_eval(fn_node, source)
            findings.append(Finding(
                kind=fn.id,
                path=rel,
                line=node.lineno,
                severity="guarded" if guarded else "high",
                guarded=guarded,
                detail="已在 AST 白名单内" if guarded else "动态执行 Python 代码",
            ))
        # pickle.load / pickle.loads
        elif _is_attr_chain(fn, pickle_mods, PICKLE_CALLS):
            findings.append(Finding(
                kind="pickle.load",
                path=rel,
                line=node.lineno,
                severity="high",
                detail="反序列化不可信数据可执行任意代码",
            ))
        elif isinstance(fn, ast.Name) and fn.id in pickle_funcs:
            findings.append(Finding(
                kind="pickle.load",
                path=rel,
                line=node.lineno,
                severity="high",
                detail=f"from pickle import {fn.id}",
            ))
        # subprocess 的 shell=True
        for kw in node.keywords:
            if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                findings.append(Finding(
                    kind="shell=True",
                    path=rel,
                    line=node.lineno,
                    severity="high",
                    detail="shell 命令注入面",
                ))
    return findings


def iter_python_files(root: Path, include_tests: bool = False):
    root = root.resolve()
    for p in root.rglob("*.py"):
        rel_parts = p.relative_to(root).parts
        if any(part in SKIP_DIRS_ALWAYS for part in rel_parts):
            continue
        if not include_tests and any(part in EXCLUDED_DIRS for part in rel_parts):
            continue
        yield p


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="BeeOffice 安全扫描")
    parser.add_argument("--root", default=".", help="扫描根目录")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--include-tests", action="store_true", help="包含 tests/ 目录")
    args = parser.parse_args(argv)

    root = Path(args.root)
    findings: list[Finding] = []
    for p in iter_python_files(root, args.include_tests):
        try:
            findings.extend(scan_source(p))
        except OSError:
            continue

    findings.sort(key=lambda f: (-SEVERITY_ORDER.get(f.severity, 0), f.path, f.line))
    high = [f for f in findings if f.severity == "high"]

    if args.json:
        print(json.dumps([asdict(f) for f in findings], ensure_ascii=False, indent=2))
    else:
        print("高危模式扫描（AST）")
        if not findings:
            print("  未发现 bare exec/eval/pickle.load/shell=True")
        for f in findings:
            tag = f.severity.upper()
            print(f"  [{tag}] {f.path}:{f.line}  {f.kind}  {f.detail}")
        print(f"\n总计：{len(findings)} 条（高危 {len(high)} 条）")

    return 1 if high else 0


if __name__ == "__main__":
    sys.exit(main())
