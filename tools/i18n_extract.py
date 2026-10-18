# -*- coding: utf-8 -*-
"""
i18n 债务盘点：找出**未走 tr() 的中文 UI 字符串**。

判定方式（基于 AST，不做正则猜测）：
    只看"面向用户的调用点"，例如
        QLabel("文本") / setText / setWindowTitle / setPlaceholderText
        QMessageBox.information(...) / addAction(...) / addTab(...)
    参数里含 CJK 的字符串常量，且外层不是 tr()/tf()。

用法：
    python tools/i18n_extract.py                # 打印统计与高频文件
    python tools/i18n_extract.py --json out.json  # 输出候选明细

退出码：0
"""
import argparse
import ast
import json
import re
import sys
from collections import Counter
from pathlib import Path

try:
    from _console import enable_utf8_output
    enable_utf8_output()
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
CJK = re.compile(r"[\u4e00-\u9fff]")

# 视为"用户可见"的被调用函数名（取调用表达式最后一个属性名）
UI_FUNCS = {
    # Qt 控件/窗口
    "setText", "setWindowTitle", "setPlaceholderText", "setToolTip",
    "setStatusTip", "setTabText", "addTab", "addAction", "addMenu",
    "setTitle", "setLabelText", "setInformativeText", "setDetailedText",
    # 构造/弹窗
    "QLabel", "QPushButton", "QCheckBox", "QGroupBox", "QRadioButton",
    "QAction", "QMenu", "QListWidgetItem", "QTableWidgetItem",
    "information", "warning", "critical", "question", "about",
    "getText", "getItem", "getOpenFileName", "getSaveFileName",
    "getExistingDirectory",
    # 项目内部封装
    "register_command", "_set_status", "set_global_status", "tr_",
}

# 明确不算 UI 的参数位置（QMessageBox.parent 等）——本项目里父对象都是 self，无需处理


def _call_name(node: ast.Call) -> str:
    f = node.func
    if isinstance(f, ast.Attribute):
        # logging.warning / logger.critical 与 QMessageBox.warning 同名，
        # 但日志不是界面文案，不能算 UI（否则会去翻译日志）。
        base = f.value
        if isinstance(base, ast.Name) and base.id in ("logging", "logger", "log"):
            return ""
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return ""


def _is_tr_wrapped(node: ast.AST) -> bool:
    """
    判断字符串是否已被 tr()/tf() 包裹。

    需要识别**链式调用**：迁移后的代码是
        tr("key", "模板").format(x=x)
    参数本身是一个 `.format(...)` 调用，若不穿透到内层，
    已翻译的字符串会被继续当成"未国际化"，统计永远降不到 0。
    """
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name) and func.id in ("tr", "tf"):
        return True
    if isinstance(func, ast.Attribute):
        # a.b(...) → 递归看 a 是不是 tr(...)/封装器
        return _is_tr_wrapped(func.value)
    return False


def scan_file(path: Path):
    """返回 [(行号, 函数名, 字符串)]。"""
    try:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
    except (SyntaxError, UnicodeDecodeError):
        return []

    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name not in UI_FUNCS:
            continue
        for arg in list(node.args) + [k.value for k in node.keywords]:
            if _is_tr_wrapped(arg):
                continue
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                if CJK.search(arg.value):
                    hits.append((arg.lineno, name, arg.value))
            # f-string / 拼接
            elif isinstance(arg, ast.JoinedStr):
                text = "".join(
                    v.value for v in arg.values
                    if isinstance(v, ast.Constant) and isinstance(v.value, str)
                )
                if CJK.search(text):
                    hits.append((arg.lineno, name, text))
    return hits


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="把明细写到这个路径")
    args = ap.parse_args(argv)

    files = [
        p for p in (ROOT / "beeoffice").rglob("*.py")
        if "__pycache__" not in p.parts
    ]

    per_file = {}
    total = 0
    funcs = Counter()
    for p in files:
        hits = scan_file(p)
        if hits:
            per_file[str(p.relative_to(ROOT))] = hits
            total += len(hits)
            for _, name, _ in hits:
                funcs[name] += 1

    # 已使用 tr() 的数量（用词边界，避免把 str( 也数进去）
    tr_pattern = re.compile(r"(?<![\w.])tr\(")
    tr_calls = 0
    for p in files:
        try:
            tr_calls += len(tr_pattern.findall(p.read_text(encoding="utf-8")))
        except UnicodeDecodeError:
            pass

    print(f"扫描 {len(files)} 个文件")
    print(f"已使用 tr( 调用次数（粗略）: {tr_calls}")
    print(f"未走 tr() 的中文 UI 字符串: {total} 条，分布 {len(per_file)} 个文件\n")

    print("Top 15 文件:")
    for rel, hits in sorted(per_file.items(), key=lambda kv: -len(kv[1]))[:15]:
        print(f"  {len(hits):5d}  {rel}")

    print("\nTop 10 调用点:")
    for name, n in funcs.most_common(10):
        print(f"  {n:5d}  {name}()")

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(per_file, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n明细已写入: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
