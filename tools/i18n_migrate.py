# -*- coding: utf-8 -*-
"""
i18n 迁移器：把「UI 调用里的中文字面量」批量包成 tr(key, 默认值)。

支持两种形态：
    1. 普通字符串字面量
           QPushButton("保存")  →  QPushButton(tr("key", "保存"))
    2. 单行 f-string（v5.3 新增）
           f"已导出：{path}"    →  tr("key", "已导出：{path}").format(path=path)

f-string 的转换规则（保守，宁可跳过也不出错）：
    · 只处理单行
    · 跳过带格式说明符 `{x:.2f}`、带转换标志 `{x!r}`、嵌套 f-string 的
    · 简单变量名 → 关键字占位符 `{name}` + `.format(name=name)`
    · 出现复杂表达式或重名变量 → 整体改为位置参数 `{0}` + `.format(expr)`
    · 字面量里的 `{` `}` 会被转义成 `{{` `}}`，保证 .format 语义不变

安全：
    · 只改 AST 能确认的 UI 调用点，不动注释 / docstring / 字体名 / 数据字面量
    · 相同文案共用一个 key（哈希），稳定可复现
    · 写盘前编译新代码，语法不过直接放弃
    · i18n 模块自身禁止引入 tr（否则循环导入）
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
    """每行起始的绝对**字节**偏移（ast 的 col_offset 是 UTF-8 字节偏移）。"""
    offsets = [0]
    for line in src_bytes.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def _abs(node, offsets):
    return offsets[node.lineno - 1] + node.col_offset


def make_key(module: str, text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return f"auto.{module}.{digest}"


def _escape_literal(text: str) -> str:
    return text.replace("{", "{{").replace("}", "}}")


def _fstring_template(node):
    """
    把 JoinedStr 转成 (模板, format 参数表)；不支持时返回 None。
    """
    # 先尝试全关键字形式：所有插值都是简单变量且不重名
    keyword_parts, keyword_args, names = [], [], []
    keyword_ok = True
    for value in node.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            keyword_parts.append(_escape_literal(value.value))
        elif isinstance(value, ast.FormattedValue):
            if value.format_spec is not None or value.conversion not in (-1, None):
                keyword_ok = False
                break
            inner = value.value
            if not isinstance(inner, ast.Name) or inner.id in names:
                keyword_ok = False
                break
            names.append(inner.id)
            keyword_parts.append("{" + inner.id + "}")
            keyword_args.append(f"{inner.id}={inner.id}")
        else:
            keyword_ok = False
            break

    if keyword_ok and keyword_args:
        return "".join(keyword_parts), ", ".join(keyword_args)

    # 退回位置参数形式
    positional_parts, positional_args = [], []
    for value in node.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            positional_parts.append(_escape_literal(value.value))
        elif isinstance(value, ast.FormattedValue):
            if value.format_spec is not None or value.conversion not in (-1, None):
                return None
            if not hasattr(ast, "unparse"):
                return None
            try:
                expr = ast.unparse(value.value)
            except Exception:
                return None
            if not expr:
                return None
            positional_parts.append("{" + str(len(positional_args)) + "}")
            positional_args.append(expr)
        else:
            return None

    if not positional_args:
        return None
    return "".join(positional_parts), ", ".join(positional_args)


def collect(src: str, module: str):
    """返回 ([(start, end, key, replacement, text)], {key: text})，字节偏移。"""
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
            if not isinstance(arg, (ast.Constant, ast.JoinedStr)):
                continue
            if arg.end_lineno != arg.lineno:
                continue  # 跨行，切片容易出错

            text = None
            replacement = None

            # ---------- 普通字面量 ----------
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                if not CJK.search(arg.value):
                    continue
                text = arg.value
                start = _abs(arg, offsets)
                end = start + (arg.end_col_offset - arg.col_offset)
                literal = src_bytes[start:end].decode("utf-8")

            # ---------- f-string ----------
            else:
                raw = ast.get_source_segment(src, arg) or ""
                if not CJK.search(raw):
                    continue
                built = _fstring_template(arg)
                if built is None:
                    continue
                template, format_args = built
                text = template
                start = _abs(arg, offsets)
                end = start + (arg.end_col_offset - arg.col_offset)
                key = seen.get(text) or make_key(module, text)
                seen.setdefault(text, key)
                template_literal = json.dumps(template, ensure_ascii=False)
                replacement = (
                    f'tr("{key}", {template_literal}).format({format_args})'
                )

            if text is None:
                continue

            key = seen.get(text) or make_key(module, text)
            seen.setdefault(text, key)
            if replacement is None:
                replacement = f'tr("{key}", {literal})'

            entries.append((start, end, key, replacement, text))
    return entries, seen


def rewrite(src: str, entries):
    """从后往前替换（字节级），保证前面的偏移不失效。"""
    out = src.encode("utf-8")
    for start, end, _key, replacement, _text in sorted(entries, reverse=True):
        out = out[:start] + replacement.encode("utf-8") + out[end:]
    return out.decode("utf-8")


def ensure_import(src: str) -> str:
    """在最后一条**顶层** import 之后插入 tr 的导入（支持跨行导入）。"""
    if TR_IMPORT in src:
        return src
    tree = ast.parse(src)
    insert_line = 0
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            insert_line = max(insert_line, node.end_lineno)

    lines = src.splitlines(keepends=True)
    if insert_line == 0:
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
    ap.add_argument("--json", help="把 key→中文模板 写到这里")
    args = ap.parse_args(argv)

    path = Path(args.path)
    if not path.exists():
        path = ROOT / args.path
    src = path.read_text(encoding="utf-8")

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
        # 写成 {key: 中文模板}（i18n_apply_en 需要这个方向）
        Path(args.json).write_text(
            json.dumps(
                {key: text for text, key in mapping.items()},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
        print(f"key→中文 已写入: {args.json}")

    if not args.write:
        print("\n（预演模式，未修改文件。加 --write 落盘）")
        for _s, _e, key, replacement, _t in entries[:5]:
            print(f"  {key}  ←  {replacement[:70]}")
        return 0

    path.write_text(new_src, encoding="utf-8")
    print(f"\n✓ 已写入 {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
