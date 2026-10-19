# tools/pipelines/build_jobs.py
"""
**自动化流水线模板生成器**（阶段③ P1-2）：把"一个目录"变成 `beecmd batch` 的任务清单。

## 三个模板
1. `md-pdf`：目录下所有 Markdown → PDF（+ 可选词元级 verify）
   —— 对应路线图"合同/报告批量转 PDF 并校验"；
2. `beshow`：目录下所有 Markdown → `.beshow` 演示文稿
   —— 对应"演示批量导出"的 CLI 部分（PPTX 导出仍需 GUI/WebEngine，未接）；
3. `sheet-merge`：把目录下所有表格文件合并成一个 xlsx
   —— 对应"Excel 多表汇总"（beecmd v0.2 `merge`）。

## 用法
    python tools/pipelines/build_jobs.py --kind md-pdf --input 合同/
    python tools/pipelines/build_jobs.py --kind beshow --input 讲稿/
    python tools/pipelines/build_jobs.py --kind sheet-merge --input 月报/ --mode append
    # 生成 jobs.json 后：
    python -m beeoffice.beecmd batch jobs.json --audit audit.jsonl

默认输出到 `<input>/../pipeline_out/`；`--out` 可覆盖 jobs.json 路径。
退出码：0 成功生成；1 输入不合法（目录不存在/没有匹配文件）。
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: 各模板认识的输入扩展名
KINDS = {
    "md-pdf": (".md", ".markdown", ".txt"),
    "beshow": (".md", ".markdown", ".txt"),
    "sheet-merge": (".xlsx", ".xls", ".csv", ".json", ".md", ".html", ".htm"),
}


def collect(input_dir: Path, kind: str):
    """按模板收集输入文件（排序，保证输出稳定）。"""
    exts = KINDS[kind]
    files = [
        p for p in sorted(input_dir.rglob("*"))
        if p.is_file() and p.suffix.lower() in exts
        and not p.name.startswith("~$")
    ]
    return files


def build_jobs(kind: str, input_dir: Path, output_dir: Path,
               verify: bool = True, mode: str = "append") -> dict:
    """生成 `{"jobs": [...]}`（路径为绝对路径，避免 cwd 影响）。"""
    files = collect(input_dir, kind)
    jobs = []
    if kind in ("md-pdf", "beshow"):
        target = "pdf" if kind == "md-pdf" else "beshow"
        for src in files:
            out = output_dir / f"{src.stem}.{target}"
            jobs.append({"op": "convert", "src": str(src),
                         "to": target, "out": str(out)})
            # ⚠️ 只有 md→pdf 能做词元级 verify；`.beshow` 是蜜演自有格式，
            # `verify` 不支持与 Markdown 比对（会误报不一致），因此不生成 verify。
            if verify and kind == "md-pdf":
                jobs.append({
                    "op": "verify", "src": str(src), "artifact": str(out),
                    "report": str(output_dir / f"{src.stem}.verify.json"),
                })
    elif kind == "sheet-merge":
        out = output_dir / f"汇总_{input_dir.name}.xlsx"
        jobs.append({
            "op": "merge", "srcs": [str(p) for p in files],
            "out": str(out), "mode": mode,
        })
    else:  # pragma: no cover - argparse 已限制
        raise ValueError(f"未知模板: {kind}")
    return {"jobs": jobs}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成 beecmd 批量任务清单（流水线模板）")
    ap.add_argument("--kind", required=True, choices=sorted(KINDS),
                    help="模板：md-pdf / beshow / sheet-merge")
    ap.add_argument("--input", required=True, help="输入目录")
    ap.add_argument("--output-dir", help="产物目录（默认 <input>/../pipeline_out）")
    ap.add_argument("--out", help="jobs.json 路径（默认 <output-dir>/jobs.json）")
    ap.add_argument("--no-verify", action="store_true",
                    help="md-pdf 模板不生成 verify 任务")
    ap.add_argument("--mode", choices=["append", "sheets"], default="append",
                    help="sheet-merge 模板的合并模式")
    args = ap.parse_args(argv)

    input_dir = Path(args.input).resolve()
    if not input_dir.is_dir():
        print(f"❌ 输入目录不存在: {input_dir}", file=sys.stderr)
        return 1
    files = collect(input_dir, args.kind)
    if not files:
        print(f"❌ {input_dir} 下没有 {args.kind} 模板认识的输入文件", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir).resolve() if args.output_dir \
        else input_dir.parent / f"{input_dir.name}_pipeline_out"
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_jobs(args.kind, input_dir, output_dir,
                         verify=not args.no_verify, mode=args.mode)
    jobs_path = Path(args.out).resolve() if args.out else output_dir / "jobs.json"
    jobs_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"✅ 模板 {args.kind}：{len(files)} 个输入 → {len(payload['jobs'])} 条任务")
    print(f"   任务清单: {jobs_path}")
    print("   执行: python -m beeoffice.beecmd batch "
          f"\"{jobs_path}\" --audit \"{output_dir / 'audit.jsonl'}\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
