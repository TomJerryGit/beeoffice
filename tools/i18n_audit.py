# tools/i18n_audit.py
"""
**i18n 棘轮（ratchet）**：统计硬编码中文 UI 文案，防止继续恶化。

## 为什么需要
分析报告 §2.3 实测：中文 UI 文案的 `tr()` 包装率只有约 11%，且 `tr` 只出现在
`app.py` / `menus.py`。在决定"全面 tr 化"还是"中文优先"之前，至少要先做到
**不再增加新的硬编码** —— 否则无论选哪条路，债都在变大。

本工具做三件事：
1. 扫描 `beeoffice/`，统计**引号外的中文文案**（排除 docstring、`tr()` 参数、
   `logging.*` 与 `print` 的输出）；
2. 与 `tools/i18n_baseline.json` 比较，**只许减少、不许增加**；
3. 生成报告（Markdown），列出硬编码最多的文件，供后续按模块 tr 化时排序。

## 口径（故意保守，不追求语言学精确）
* 计入：所有含 CJK 字符的字符串常量（模块/类/函数 docstring 除外，
  `tr(...)` 调用里的参数除外，`logging.*` / `print(...)` 的参数除外）；
* 不计入：注释（AST 里本来就没有）、日志、控制台输出；
* 这个口径会**高估**实际 UI 文案（有些中文串是数据/测试/正则），
  但它稳定、可解释、适合做"趋势棘轮"。

## 用法
    python tools/i18n_audit.py                 # 检查（增加则 exit 1）
    python tools/i18n_audit.py --write-baseline # 更新基线（有意减少后）
    python tools/i18n_audit.py --json out.json --report docs/i18n现状.md
"""
import argparse
import ast
import datetime as _dt
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "beeoffice"
BASELINE = ROOT / "tools" / "i18n_baseline.json"

#: 含 CJK 统一表意文字（够用；扩展区/兼容区不常见于界面）
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

#: 这些"调用名"的参数不计入（日志/控制台/翻译包装）
_EXCLUDED_CALL_NAMES = {
    "tr", "translate", "print",
    "debug", "info", "warning", "error", "exception", "critical", "log",
    "basicConfig",
}


def _call_name(node) -> str:
    """取出 Call 的函数名（Name / Attribute 的最后一段）。"""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _excluded_constant_ids(tree):
    """返回"不该计入"的字符串常量节点 id 集合。"""
    excluded = set()
    # 1) docstring（模块/类/函数的第一条 Expr 字符串）
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef,
                             ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) \
                    and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                excluded.add(id(body[0].value))
    # 2) tr(...) / logging.* / print(...) 的参数
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _call_name(node) in _EXCLUDED_CALL_NAMES:
            for value in node.args:
                for sub in ast.walk(value):
                    if isinstance(sub, ast.Constant) and isinstance(
                            sub.value, str):
                        excluded.add(id(sub))
            for kw in node.keywords or []:
                for sub in ast.walk(kw.value):
                    if isinstance(sub, ast.Constant) and isinstance(
                            sub.value, str):
                        excluded.add(id(sub))
    return excluded


def scan(root: Path = PACKAGE) -> dict:
    """
    扫描目录下所有 `.py`，返回 `{"total": int, "by_file": {相对路径: 数量}}`。
    """
    total = 0
    by_file = {}
    for path in sorted(Path(root).rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source)
        except Exception:  # noqa: BLE001 - 语法坏的文件跳过并提示
            continue
        excluded = _excluded_constant_ids(tree)
        count = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(
                    node.value, str):
                continue
            if id(node) in excluded:
                continue
            if _CJK_RE.search(node.value):
                count += 1
        if count:
            try:
                rel = str(path.relative_to(ROOT if ROOT in path.parents
                                           else Path(root).parent))
            except ValueError:
                rel = str(path)
            # 统一成 POSIX 分隔符：基线在 Windows/Linux 上必须可比
            rel = rel.replace("\\", "/")
            by_file[rel] = count
            total += count
    return {"total": total, "by_file": by_file}


def load_baseline(path: Path = BASELINE) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 基线缺失时给空基线（不崩）
        return {"total": 0, "by_file": {}}


def write_baseline(scan_result: dict, path: Path = BASELINE) -> None:
    payload = {
        "total": scan_result["total"],
        "by_file": scan_result["by_file"],
        "generated_at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "commit": _git_commit(),
        "note": "硬编码中文文案棘轮基线；只许减少。更新方式："
                "python tools/i18n_audit.py --write-baseline",
    }
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT),
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() if out.returncode == 0 else "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def check(scan_result: dict, baseline: dict) -> dict:
    """
    比较当前扫描与基线。规则：**总数不得增加**；文件名增减只做报告。

    :return: {"ok": bool, "current_total": int, "baseline_total": int,
              "delta": int, "top_files": [(file, count), ...],
              "new_files": [(file, count), ...],
              "delta_files": [(file, before, after), ...]}
    """
    current_total = int(scan_result.get("total", 0))
    baseline_total = int(baseline.get("total", 0))
    cur_by = scan_result.get("by_file", {}) or {}
    base_by = baseline.get("by_file", {}) or {}

    top_files = sorted(cur_by.items(), key=lambda kv: -kv[1])[:15]
    new_files = sorted(
        ((f, c) for f, c in cur_by.items() if f not in base_by),
        key=lambda kv: -kv[1],
    )[:10]
    delta_files = sorted(
        ((f, base_by[f], cur_by[f]) for f in cur_by
         if f in base_by and cur_by[f] != base_by[f]),
        key=lambda item: -(item[2] - item[1]),
    )[:10]
    return {
        "ok": current_total <= baseline_total,
        "current_total": current_total,
        "baseline_total": baseline_total,
        "delta": current_total - baseline_total,
        "top_files": top_files,
        "new_files": new_files,
        "delta_files": delta_files,
    }


def build_report(result: dict, baseline: dict) -> str:
    lines = [
        "# i18n 现状与硬编码棘轮",
        "",
        f"> 生成时间：{_dt.datetime.now().strftime('%Y-%m-%d %H:%M')} · "
        f"代码基线：`{_git_commit()}`",
        "> 工具：`tools/i18n_audit.py`（统计**引号外中文串**，排除 docstring/"
        "`tr()` 参数/日志；口径偏保守，见工具文档）",
        "",
        "## 0. 一页结论",
        "",
        f"- 当前硬编码中文串：**{result['current_total']}** 处；"
        f"棘轮基线：**{result['baseline_total']}** 处；"
        f"变化：**{result['delta']:+d}**",
        f"- 判定：{'✅ 未增加（棘轮通过）' if result['ok'] else '❌ 增加，需要处理'}",
        "- 这不是“完整 i18n 化”：只是**防止债变大**。是否全面 tr 化是产品决策，",
        "  两条路各有人日成本（见文末）。",
        "",
        "## 1. 硬编码最多的文件（Top 15）",
        "",
        "| 文件 | 处数 |",
        "|---|---:|",
    ]
    for name, count in result["top_files"]:
        lines.append(f"| `{name}` | {count} |")
    lines += [
        "",
        "## 2. 与基线相比新增的文件（Top 10）",
        "",
    ]
    if result["new_files"]:
        lines.append("| 文件 | 处数 |")
        lines.append("|---|---:|")
        for name, count in result["new_files"]:
            lines.append(f"| `{name}` | {count} |")
    else:
        lines.append("（无新增文件）")
    lines += [
        "",
        "## 3. 与基线相比变化的文件（Top 10）",
        "",
    ]
    if result["delta_files"]:
        lines.append("| 文件 | 基线 | 当前 | 变化 |")
        lines.append("|---|---:|---:|---:|")
        for name, before, after in result["delta_files"]:
            lines.append(f"| `{name}` | {before} | {after} | {after - before:+d} |")
    else:
        lines.append("（无变化）")
    lines += [
        "",
        "## 4. 两条路线（待决策）",
        "",
        "| 路线 | 内容 | 粗估 | 风险 |",
        "|---|---|---|---|",
        "| A. 按模块 tr 化 | 逐模块把 UI 文案抽成 key，补 en_US；运行时切换需重翻译 | 2–3 周 | 改动面大、回归多 |",
        "| B. 中文优先 | 移除语言切换入口，在 README 写明暂不支持英文界面 | 0.5 人日 | 失去英文用户（本来也几乎不可用） |",
        "",
        "无论选哪条，**棘轮门禁都会阻止新增硬编码**（`python tools/i18n_audit.py`）。",
        "",
        "## 5. 复跑",
        "",
        "```powershell",
        "python tools\\i18n_audit.py                 # 检查（增加则 exit 1）",
        "python tools\\i18n_audit.py --write-baseline # 有意减少后再更新基线",
        "python tools\\i18n_audit.py --report docs\\i18n现状.md",
        "```",
        "",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="i18n 硬编码棘轮")
    ap.add_argument("--write-baseline", action="store_true",
                    help="用当前扫描结果更新基线")
    ap.add_argument("--json", help="输出 JSON 路径")
    ap.add_argument("--report", help="输出 Markdown 报告路径")
    args = ap.parse_args(argv)

    scanned = scan(PACKAGE)
    if args.write_baseline:
        write_baseline(scanned)
        print(f"✅ 已更新基线：{scanned['total']} 处 → {BASELINE}")
        return 0

    baseline = load_baseline()
    result = check(scanned, baseline)
    print(f"硬编码中文串：当前 {result['current_total']} / 基线 "
          f"{result['baseline_total']}（{result['delta']:+d}）")
    for name, before, after in result["delta_files"]:
        print(f"  {name}: {before} → {after} ({after - before:+d})")
    if result["ok"]:
        print("✅ 棘轮通过（未增加）")
    else:
        print("❌ 新增了硬编码中文文案；请用 tr() 包装或更新基线（需理由）")

    if args.json:
        Path(args.json).write_text(
            json.dumps({"scan": scanned, "check": result,
                        "baseline": baseline},
                       ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"JSON 已写入 {args.json}")
    if args.report:
        report = build_report(result, baseline)
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(report, encoding="utf-8")
        print(f"报告已写入 {args.report}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
