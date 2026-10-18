# -*- coding: utf-8 -*-
"""
i18n 迁移器：把「UI 调用里的中文字面量」批量包成 tr(key, 默认值)。

设计原则：
    · 只改 AST 能确认的 UI 调用点（复用 i18n_extract 的判定集合），
      不动注释、docstring、字体名、数据字面量。
    · 用 ast 的精确位置做切片替换，不做正则替换。
    · 相同文案共用一个 key（去重），key 由文本哈希生成，稳定可复现。
    · 默认只做**预演**（--dry-run 是默认行为），加 --write 才落盘。
    · 落盘前先做语法自检：新代码必须能 compile，否则放弃。

用法：
    python tools/i18n_migrate.py beeoffice/plugins/beewrite_toolbar_mixin.py
    python tools/i18n_migrate.py <file> --write
"""
import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from tools.i18n_extract import UI_FUNCS  # noqa: E402
except ImportError:  # 直接以脚本方式运行（sys.path 里没有仓库根）
    sys.path.insert(0, str(Path(__file__).parent))
    from i18n_extract import UI_FUNCS  # noqa: E402

CJK = re.compile(r"[\u4e00-\u9fff]")
TR_IMPORT = "from beeoffice.i18n import tr"


def _call_name(node):
    f = node.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return ""


def _is_tr(node):
    return (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("tr", "tf"))


def _line_offsets(src_bytes):
    """每行起始的绝对**字节**偏移。

    注意：CPython 的 ast 给出的 col_offset 是 UTF-8 字节偏移，
    不是字符偏移。含中文的行如果按字符算，切片会错位并破坏源码。
    """
    offsets = [0]
    for line in src_bytes.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def _abs(node, offsets):
    """ast 的 (lineno, col) → 绝对字节偏移。"""
    return offsets[node.lineno - 1] + node.col_offset


def make_key(module: str, text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return f"auto.{module}.{digest}"


def collect(src: str, module: str):
    """返回 [(start, end, key, literal_repr, text)]，按出现顺序（字节偏移）。"""
    tree = ast.parse(src)
    src_bytes = src.encode("utf-8")
    offsets = _line_offsets(src_bytes)
    entries = []
    seen = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _call_name(node) not in UI_FUNCS:
            continue
        for arg in list(node.args) + [k.value for k in node.keywords]:
            if _is_tr(arg):
                continue
            # 只处理单行、单引号/双引号的普通字符串常量
            if not (isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str)
                    and CJK.search(arg.value)):
                continue
            if arg.end_lineno != arg.lineno:
                continue  # 跨行字面量跳过，避免切片出错

            text = arg.value
            if text in seen:
                key = seen[text]
            else:
                key = make_key(module, text)
                seen[text] = key

            start = _abs(arg, offsets)
            end = start + (arg.end_col_offset - arg.col_offset)
            literal = src_bytes[start:end].decode("utf-8")
            entries.append((start, end, key, literal, text))
    return entries, seen


def rewrite(src: str, entries):
    """从后往前替换（字节级），保证前面的偏移不失效。"""
    out = src.encode("utf-8")
    for start, end, key, literal, _text in sorted(entries, reverse=True):
        replacement = f'tr("{key}", {literal})'.encode("utf-8")
        out = out[:start] + replacement + out[end:]
    return out.decode("utf-8")


def ensure_import(src: str) -> str:
    """在最后一条**顶层** import 之后插入 tr 的导入。

    不能用"第几行以 import 开头"来判断：本项目大量使用
    `from PySide6.QtWidgets import (` 这种跨行导入，
    按行号插入会把括号劈开，直接语法错误。
    """
    if TR_IMPORT in src:
        return src
    tree = ast.parse(src)
    insert_line = 0  # 0 表示没有任何 import，插到文件最前面
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            insert_line = max(insert_line, node.end_lineno)

    lines = src.splitlines(keepends=True)
    if insert_line == 0:
        # 跳过模块 docstring
        first = tree.body[0] if tree.body else None
        if (isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            insert_line = first.end_lineno
    lines.insert(insert_line, "\n" + TR_IMPORT + "\n"
                 if insert_line == 0 else TR_IMPORT + "\n")
    return "".join(lines)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--json", help="把 key→中文 写到这里")
    args = ap.parse_args(argv)

    path = Path(args.path)
    if not path.exists():
        path = ROOT / args.path
    src = path.read_text(encoding="utf-8")

    # i18n 模块自身不能引入 tr（会形成循环导入）
    if path.name in ("i18n.py", "__init__.py"):
        print(f"跳过 {path.name}：该模块不能引用 tr")
        return 0

    # i18n 模块自身不能引入 tr（会形成循环导入）
    if path.name in ("i18n.py", "__init__.py"):
        print(f"跳过 {path.name}：该模块不能引用 tr")
        return 0

    module = path.stem
    entries, mapping = collect(src, module)
    if not entries:
        print("没有可迁移的字符串。")
        return 0

    new_src = ensure_import(rewrite(src, entries))

    # 语法自检
    try:
        compile(new_src, str(path), "exec")
    except SyntaxError as e:
        print(f"✗ 重写后语法错误，已放弃：{e}")
        return 2

    uniq = len(set(mapping.values()))
    print(f"文件      : {path.relative_to(ROOT) if path.is_absolute() else path}")
    print(f"命中调用点: {len(entries)}")
    print(f"唯一条目  : {uniq}")

    if args.json:
        Path(args.json).write_text(
            json.dumps(
                {mapping[t]: t for t in mapping}, ensure_ascii=False, indent=2
            ),
            encoding="utf-8",
        )
        print(f"key→中文 已写入: {args.json}")

    if not args.write:
        print("\n（预演模式，未修改文件。加 --write 落盘）")
        for _s, _e, key, literal, text in entries[:5]:
            print(f"  {key}  ←  {literal}")
        return 0

    path.write_text(new_src, encoding="utf-8")
    print(f"\n✓ 已写入 {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
