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


def _probe_xlsx_shape(path: Path):
    """大表跳过时的轻量维度探测（不读值，只读 dimension/表名）。"""
    if path.suffix.lower() not in (".xlsx", ".xlsm"):
        return None
    try:
        from openpyxl import load_workbook

        wb = load_workbook(path, read_only=True, data_only=True)
        try:
            ws = wb.worksheets[0]
            return {
                "rows": max(0, (ws.max_row or 1) - 1),   # 不计表头
                "cols": ws.max_column or 0,
                "sheets": len(wb.sheetnames),
            }
        finally:
            wb.close()
    except Exception:  # noqa: BLE001 - 探测失败不影响报告
        return None


def _pptx_source_chars(path: Path) -> int:
    """PPTX 源文件里的文字量（标题/正文/表格/备注，去掉空白）。"""
    from pptx import Presentation

    total = 0
    presentation = Presentation(str(path))
    for slide in presentation.slides:
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False):
                total += len("".join(shape.text_frame.text.split()))
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    for cell in row.cells:
                        total += len("".join(cell.text.split()))
        try:
            notes = slide.notes_slide.notes_text_frame.text
            total += len("".join(notes.split()))
        except Exception:  # noqa: BLE001 - 没有备注页很正常
            pass
    return total


def _pptx_import_result(path: Path) -> dict:
    """
    PPTX 走**导入口径**（产品没有 pptx → Markdown → pptx 的往返路径）。

    这里不假装做了往返：调用产品的 `import_pptx()`，记录
    * 导入页数；
    * 文字保留率（标题/正文/备注口径，源端含表格文字）；
    * 产品**主动声明**的损失清单（图片/表格/图表等转占位）与警告。
    """
    result = {
        "path": str(path), "name": path.name, "format": "pptx",
        "size": path.stat().st_size, "profile": "pptx",
        "error": None, "skipped": None,
        "slides": 0, "text_before": 0, "text_after": 0,
        "losses": {}, "warnings": [],
    }
    try:
        from beeoffice.plugins.beeshow_pptx_import import import_pptx

        before = _pptx_source_chars(path)
        imported, _markdown = import_pptx(path)
        after = 0
        for slide in imported.slides:
            after += len("".join((slide.title or "").split()))
            for _level, text in slide.bullets:
                after += len("".join(text.split()))
            after += len("".join((slide.notes or "").split()))
        result.update({
            "slides": imported.slide_count,
            "text_before": before,
            "text_after": after,
            "losses": dict(imported.losses),
            "warnings": list(imported.warnings),
        })
    except Exception as e:  # noqa: BLE001 - 报告要跑完全部语料
        result["error"] = f"导入失败: {type(e).__name__}: {e}"
    return result


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
    pptx = [r for r in results if r["profile"] == "pptx"]

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
        if r.get("profile") == "pptx":
            # 导入口径：产品已明示的损失清单不算"未知"；只有导入异常才是未知
            continue
        if r["skipped"]:
            continue
        known = KNOWN_REAL if r["profile"] == "real" else KNOWN_STRESS
        if classify(r, known)["unknown"]:
            all_unknown.append((r["name"], classify(r, known)["unknown"]))

    real_rows = [r for r in real if not r["error"] and not r["skipped"]]
    stress_rows = [r for r in stress if not r["error"] and not r["skipped"]]
    pptx_rows = [r for r in pptx if not r["error"]]
    skipped_n = len([
        r for r in results
        if r.get("skipped") and r.get("profile") != "pptx"
    ])
    lines = [
        "# 保真度报告（自动生成）",
        "",
        f"> 生成时间：{meta['generated_at']} · 代码基线：`{meta['commit']}`",
        f"> 工具：`tools/fidelity_report.py` · 方法：OOXML 探测 → DOCX↔Markdown 往返 → 再探测；"
        "PPTX 走产品**导入口径**（无往返，记录已声明损失）",
        f"> JSON：`{meta.get('json', '—')}`",
        "",
        "## 0. 结论",
        "",
        f"- 样本：真实文档 **{len(real_rows)}** 份（往返）"
        + (f" + PPTX **{len(pptx_rows)}** 份（导入口径）" if pptx_rows else "")
        + (f" + 压力语料 **{len(stress_rows)}** 份" if stress_rows else "")
        + (f"（另有 {skipped_n} 份跳过：大表/无导入路径）" if skipped_n else "")
        + "。",
        f"- 未知类别/异常：**{len(all_unknown)}** 个"
        + ("（见下表，需要调查）" if all_unknown else "（全部差异都在已知类别内）"),
        "- 说明：**本报告不是\"零丢失\"证明**。真实文档的差异集中在"
        "“空段落无法用 Markdown 表达”“空白规范化”“HYPERLINK 域→真超链接”三类；"
        "PPTX 的图片/表格/图表等由产品在导入时**主动列出损失清单**（不伪装保留）。"
        "若要对外宣称保真能力，请使用“每次转换都有损失报告”的口径。",
        "",
        "## 1. 真实文档（DOCX/XLSX 往返）",
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
    if pptx:
        lines += [
            "## 2b. PPTX（导入口径，非往返）",
            "",
            "产品目前**没有** pptx→…→pptx 往返路径；这里调用产品导入接口，",
            "记录页数、文字保留率（标题/正文/备注；源端含表格文字）与**已声明损失**。",
            "",
            "| 文件 | 大小 | 页数 | 文字保留率 | 已声明损失 | 警告 | 异常 |",
            "|---|---:|---:|---:|---|---|---|",
        ]
        for r in pptx:
            if r["error"]:
                lines.append(
                    f"| {r['name']} | {r['size'] / 1024:.0f} KB | — | — | — | — "
                    f"| **{r['error']}** |"
                )
                continue
            before = r.get("text_before") or 0
            after = r.get("text_after") or 0
            ratio = f"{after / before * 100:.1f}%" if before else "—"
            losses = "、".join(
                f"{k}×{v}" for k, v in (r.get("losses") or {}).items()
            ) or "无声明"
            warns = "；".join(r.get("warnings") or []) or "—"
            lines.append(
                f"| {r['name']} | {r['size'] / 1024:.0f} KB | {r.get('slides', 0)} "
                f"| {ratio} | {losses} | {warns} | 无 |"
            )
        lines.append("")
    lines += [
        "## 3. 复跑",
        "",
        "```powershell",
        "cd D:\\beeofficeV",
        "$env:PYTHONPATH='D:\\beeofficeV'; $env:QT_QPA_PLATFORM='offscreen'",
        "python tools\\fidelity_report.py --include-pptx-import --max-size-mb 8 "
        "--report docs\\保真报告.md --json 结果.json",
        "```",
        "",
        "## 4. 局限",
        "",
        f"- 真实样本量取决于 `tests/fidelity/corpus/`，当前 {len(real) + len(pptx)} 个文件"
        f"（{len(real_rows)} 份可往返 + {len(pptx_rows)} 份 PPTX 只导入"
        + (f" + {skipped_n} 份大表跳过（>8 MB，见跳过原因）" if skipped_n else "")
        + "）；",
        "- DOCX 中间经过 Markdown，是结构性薄弱点；XLSX 走“保结构更新”另一条路；"
        "大表（>8 MB）不做 Markdown 往返，只用于打开/转换性能验证；",
        "- PPTX 目前只导入不往返，损失清单来自产品实现（不是第三方比对）；",
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
    ap.add_argument("--include-pptx-import", action="store_true",
                    help="对 PPTX 跑产品导入接口并记录已声明损失（非往返）")
    ap.add_argument("--report", help="输出 Markdown 报告路径")
    ap.add_argument("--json", help="输出 JSON 路径")
    ap.add_argument("--max-size-mb", type=float, default=0,
                    help="跳过超过该大小的文件（0=不限制；20 万行 xlsx 的 "
                         "Markdown 往返不可行，建议 8）")
    args = ap.parse_args(argv)

    real_dirs = args.dirs or [str(DEFAULT_REAL_DIR)]
    jobs = []          # (profile, path, workdir_root)
    tmp = tempfile.TemporaryDirectory(prefix="beeoffice_fidelity_")
    workdir = Path(tmp.name)

    real_files = iter_files(real_dirs)
    real_only = [p for p in real_files if p.suffix.lower() != ".pptx"]
    pptx_files = [
        p for p in real_files if p.suffix.lower() == ".pptx"
    ] if args.include_pptx_import else []
    print(f"真实语料 {len(real_files)} 个文件"
          f"（可往返 {len(real_only)} + PPTX 导入口径 {len(pptx_files)}）", flush=True)
    for path in real_only:
        jobs.append(("real", path, workdir / "real"))
    for path in pptx_files:
        jobs.append(("pptx", path, workdir / "pptx"))

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
    max_bytes = int(args.max_size_mb * 1024 * 1024) if args.max_size_mb else 0
    for profile, path, root in jobs:
        if profile == "pptx":
            print(f"  正在导入 {path.name} ...", flush=True)
            results.append(_pptx_import_result(path))
            continue
        size = path.stat().st_size
        if max_bytes and size > max_bytes:
            print(f"  ↷ 跳过（{size / 1024 / 1024:.1f} MB > "
                  f"{args.max_size_mb:g} MB）{path.name}", flush=True)
            shape = _probe_xlsx_shape(path)
            reason = (
                f"超过 --max-size-mb {args.max_size_mb:g} MB 上限"
                "（大表 Markdown 往返不可行）"
            )
            if shape:
                reason += (
                    f"；声明规模 {shape['rows']:,} 行 × {shape['cols']} 列"
                    f" / {shape['sheets']} 张表"
                )
            results.append({
                "name": path.name, "size": size, "error": "",
                "skipped": reason,
                "shape": shape,
                "rows": [], "profile": profile, "empty_paragraphs": None,
                "before": {"features": {}}, "after": {"features": {}},
            })
            continue
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
        if r.get("profile") == "pptx":
            continue
        if r["skipped"]:
            continue
        known = KNOWN_REAL if r["profile"] == "real" else KNOWN_STRESS
        if classify(r, known)["unknown"]:
            unknown.append((r["name"], classify(r, known)["unknown"]))

    real_n = len([r for r in results if r["profile"] == "real"])
    stress_n = len([r for r in results if r["profile"] == "stress"])
    pptx_n = len([r for r in results if r.get("profile") == "pptx"])
    print()
    print(f"完成：真实 {real_n} + PPTX {pptx_n} + 压力 {stress_n}；"
          f"未知类别/异常 {len(unknown)} 个")
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
