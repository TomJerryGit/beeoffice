# tools/fidelity_report.py
"""
保真度 **报告生成器**（阶段③：把"真实文档到底丢什么"变成可对外发布的报告）。

## 为什么不直接用 `fidelity_corpus.py`
后者是**检查器**：发现任何差异就 exit 1，输出是给人看的文本。
本工具是**报告器**：
* 把差异按"已知类别 / 未知类别"分类（与 `tests/fidelity/test_corpus.py` 同口径）；
* 逐文件给出文字丢失率、段落减少与源文件空段落数的关系、增加项（如样式定义）；
* 生成 Markdown 报告（可提交/对外），JSON 供机器复核；
* 只有出现**未知类别**或异常时 exit 1 —— 与"有已知差异"区分开。

## 两个语料档位
* **real**：真实文档（默认 `tests/fidelity/corpus/`）。已知类别：
  `paragraphs`（Markdown 无法表达空段落）、`text_chars`（空白规范化）、
  `fields`（HYPERLINK 域 → 真超链接，属表示法改善）。
* **stress**：`tools/fidelity_corpus_gen.py` 生成的压力语料（每个文件专攻一维），
  已知类别按 `test_corpus.py::KNOWN_LOSSES`。

## 用法
    python tools/fidelity_report.py --report docs/xxx.md --json out.json
    python tools/fidelity_report.py --include-stress --report docs/xxx.md
    python tools/fidelity_report.py --dir 某目录 --profile real
退出码：0 = 无未知类别/异常；1 = 有未知类别或异常（需要调查）。
"""
import argparse
import datetime as _dt
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.fidelity_corpus import iter_files, run_one          # noqa: E402
from tools.fidelity_corpus_gen import generate_all             # noqa: E402

DEFAULT_REAL_DIR = ROOT / "tests" / "fidelity" / "corpus"

#: 真实语料的已知差异类别（与 test_corpus.py 的 USER_KNOWN_LOSS_KEYS 同步）
KNOWN_REAL = {"paragraphs", "text_chars", "fields"}
#: 压力语料的已知差异类别（与 test_corpus.py 的 KNOWN_LOSSES 同步）
KNOWN_STRESS = {"paragraphs", "tables", "text_chars"}


def _features(result):
    return (result.get("before") or {}).get("features") or {}


def _after_features(result):
    return (result.get("after") or {}).get("features") or {}


def _empty_paragraphs(path: Path):
    """源 docx 里的空段落数（解释段落减少用）；非 docx 返回 None。"""
    if path.suffix.lower() != ".docx":
        return None
    try:
        from docx import Document

        doc = Document(str(path))
        return sum(
            1 for p in doc.paragraphs if not (p.text or "").strip()
        )
    except Exception:  # noqa: BLE001
        return None


def classify(result, known):
    """把一行结果分类成：丢失/未知丢失/增加/错误。"""
    lost = [r for r in result.get("rows", []) if r.get("status") == "lost"]
    gained = [r for r in result.get("rows", []) if r.get("status") == "gained"]
    changed = [r for r in result.get("rows", []) if r.get("status") == "changed"]
    unknown = sorted({r["feature"] for r in lost} - set(known))
    return {
        "lost": lost,
        "gained": gained,
        "changed": changed,
        "unknown": unknown,
    }


def _text_loss(result):
    before = _features(result).get("text_chars")
    after = _after_features(result).get("text_chars")
    if not before:
        return None
    return max(0.0, (before - (after or 0)) / before * 100)


def _fmt_lost(items):
    return "、".join(f"`{r['feature']}` {r['before']}→{r['after']}" for r in items) or "—"


def _fmt_gained(items):
    return "、".join(f"`{r['feature']}` {r['before']}→{r['after']}" for r in items) or "—"


def build_markdown(results, meta) -> str:
    """生成 Markdown 报告（人读）。"""
    real = [r for r in results if r["profile"] == "real"]
    stress = [r for r in results if r["profile"] == "stress"]

    def _section(title, rows, known):
        lines = [f"### {title}", ""]
        if not rows:
            lines += ["（无样本）", ""]
            return lines
        lines += [
            "| 文件 | 大小 | 丢失 | 增加 | 文字丢失率 | 空段落/段落减少 | 未知类别 |",
            "|---|---:|---|---|---:|---|---|",
        ]
        for r in rows:
            if r["error"]:
                lines.append(
                    f"| {r['name']} | {r['size'] / 1024:.0f} KB | **异常**：{r['error']} | — | — | — | — |"
                )
                continue
            if r["skipped"]:
                lines.append(
                    f"| {r['name']} | {r['size'] / 1024:.0f} KB | 跳过（{r['skipped']}） | — | — | — | — |"
                )
                continue
            cls = classify(r, known)
            ratio = _text_loss(r)
            ratio_text = f"{ratio:.2f}%" if ratio is not None else "—"
            empty = r.get("empty_paragraphs")
            before_p = _features(r).get("paragraphs")
            after_p = _after_features(r).get("paragraphs")
            para = (
                f"{empty} / {before_p - after_p}"
                if empty is not None and before_p is not None and after_p is not None
                else "—"
            )
            unknown = "、".join(cls["unknown"]) or "无"
            lines.append(
                f"| {r['name']} | {r['size'] / 1024:.0f} KB "
                f"| {_fmt_lost(cls['lost'])} | {_fmt_gained(cls['gained'])} "
                f"| {ratio_text} | {para} | {unknown} |"
            )
        lines.append("")
        return lines

    all_unknown = []
    for r in results:
        if r["error"]:
            all_unknown.append((r["name"], "异常"))
            continue
        if r["skipped"]:
            continue
        known = KNOWN_REAL if r["profile"] == "real" else KNOWN_STRESS
        if classify(r, known)["unknown"]:
            all_unknown.append((r["name"], classify(r, known)["unknown"]))

    real_rows = [r for r in real if not r["error"] and not r["skipped"]]
    stress_rows = [r for r in stress if not r["error"] and not r["skipped"]]
    skipped_n = len([r for r in results if r["skipped"]])
    lines = [
        "# 保真度报告（自动生成）",
        "",
        f"> 生成时间：{meta['generated_at']} · 代码基线：`{meta['commit']}`",
        f"> 工具：`tools/fidelity_report.py` · 方法：OOXML 探测 → DOCX↔Markdown 往返 → 再探测",
        f"> JSON：`{meta.get('json', '—')}`",
        "",
        "## 0. 结论",
        "",
        f"- 样本：真实文档 **{len(real_rows)}** 份 + 压力语料 **{len(stress_rows)}** 份"
        + (f"（另有 {skipped_n} 份跳过：无导入路径）" if skipped_n else "")
        + "。",
        f"- 未知类别/异常：**{len(all_unknown)}** 个"
        + ("（见下表，需要调查）" if all_unknown else "（全部差异都在已知类别内）"),
        "- 说明：**本报告不是\"零丢失\"证明**。真实文档的差异集中在"
        "“空段落无法用 Markdown 表达”“空白规范化”“HYPERLINK 域→真超链接”三类；"
        "若要对外宣称保真能力，请使用“每次转换都有损失报告”的口径。",
        "",
        "## 1. 真实文档",
        "",
    ]
    lines += _section("1.1 逐文件结果", real, KNOWN_REAL)
    lines += [
        "## 2. 压力语料（生成器）",
        "",
        "这些文件由 `tools/fidelity_corpus_gen.py` 生成，每个专攻一个维度，",
        "用于暴露合成夹具覆盖不到的构造；已知丢失见 `tests/fidelity/test_corpus.py`。",
        "",
    ]
    lines += _section("2.1 逐文件结果", stress, KNOWN_STRESS)
    lines += [
        "## 3. 复跑",
        "",
        "```powershell",
        "cd D:\\beeofficeV",
        "$env:PYTHONPATH='D:\\beeofficeV'; $env:QT_QPA_PLATFORM='offscreen'",
        "python tools\\fidelity_report.py --include-stress --report docs\\保真报告.md --json 结果.json",
        "```",
        "",
        "## 4. 局限",
        "",
        "- 真实样本量有限（当前 7 份，目标 50 份），且以中文技术文档为主；",
        "- 只覆盖 DOCX 往返；XLSX 走“保结构更新”另一条路，PPTX 目前只导入不往返；",
        "- 差异按“特征计数”而非逐字 diff；能抓住大段丢失，不能证明逐字一致。",
        "",
    ]
    return "\n".join(lines)


def _git_commit():
    try:
        import subprocess

        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT),
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() if out.returncode == 0 else "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="保真度报告生成器")
    ap.add_argument("--dir", action="append", dest="dirs",
                    help="真实语料目录（可多次；默认 tests/fidelity/corpus）")
    ap.add_argument("--include-stress", action="store_true",
                    help="同时跑 tools/fidelity_corpus_gen.py 生成的压力语料")
    ap.add_argument("--report", help="输出 Markdown 报告路径")
    ap.add_argument("--json", help="输出 JSON 路径")
    args = ap.parse_args(argv)

    real_dirs = args.dirs or [str(DEFAULT_REAL_DIR)]
    jobs = []          # (profile, path, workdir_root)
    tmp = tempfile.TemporaryDirectory(prefix="beeoffice_fidelity_")
    workdir = Path(tmp.name)

    real_files = iter_files(real_dirs)
    print(f"真实语料 {len(real_files)} 个文件", flush=True)
    for path in real_files:
        jobs.append(("real", path, workdir / "real"))

    stress_files = []
    if args.include_stress:
        stress_root = workdir / "stress_src"
        stress_root.mkdir(parents=True, exist_ok=True)
        generate_all(stress_root)
        stress_files = iter_files([str(stress_root)])
        print(f"压力语料 {len(stress_files)} 个文件", flush=True)
        for path in stress_files:
            jobs.append(("stress", path, workdir / "stress"))

    results = []
    for profile, path, root in jobs:
        root.mkdir(parents=True, exist_ok=True)
        print(f"  正在测 {path.name} ...", flush=True)
        r = run_one(path, root)
        r["profile"] = profile
        r["empty_paragraphs"] = _empty_paragraphs(path)
        results.append(r)

    unknown = []
    for r in results:
        if r["error"]:
            unknown.append((r["name"], "异常"))
            continue
        if r["skipped"]:
            continue
        known = KNOWN_REAL if r["profile"] == "real" else KNOWN_STRESS
        if classify(r, known)["unknown"]:
            unknown.append((r["name"], classify(r, known)["unknown"]))

    real_n = len([r for r in results if r["profile"] == "real"])
    stress_n = len([r for r in results if r["profile"] == "stress"])
    print()
    print(f"完成：真实 {real_n} + 压力 {stress_n}；未知类别/异常 {len(unknown)} 个")
    for name, detail in unknown:
        print(f"  ✗ {name}: {detail}")

    if args.json:
        Path(args.json).write_text(
            json.dumps(results, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"JSON 已写入 {args.json}")

    if args.report:
        meta = {
            "generated_at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "commit": _git_commit(),
            "json": args.json or "",
        }
        text = build_markdown(results, meta)
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(text, encoding="utf-8")
        print(f"Markdown 报告已写入 {report_path}")

    tmp.cleanup()
    return 1 if unknown else 0


if __name__ == "__main__":
    sys.exit(main())
