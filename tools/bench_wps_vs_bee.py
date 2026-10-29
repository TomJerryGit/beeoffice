# tools/bench_wps_vs_bee.py
"""同机 WPS / BeeOffice 基准脚本（S0）。

设计原则：
- **可重复**：warmup + repeat，输出 P50/P95，不拿单次测量下结论；
- **不依赖 WPS 登录**：WPS 只走本机 COM（KWps/Ket/Kwpp），没有则明确标 unavailable；
- **不破坏文件**：WPS 以只读/无窗口方式打开，BeeOffice 只读导入；
- **可选**：默认 --no-wps 也能测 BeeOffice，CI/无 WPS 机器可用。

用法：
    python tools/bench_wps_vs_bee.py --no-wps --limit 5
    python tools/bench_wps_vs_bee.py --repeat 3 --json _ptmp/analysis/bench.json \
        --markdown _ptmp/analysis/bench.md
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_DIRS = ("test+files", "tests/fidelity/corpus")
SUPPORTED = {".docx": "docx", ".xlsx": "xlsx", ".pptx": "pptx", ".pdf": "pdf"}


@dataclass
class BenchFile:
    path: str
    name: str
    kind: str
    size: int


@dataclass
class BenchResult:
    engine: str
    operation: str
    name: str
    path: str
    kind: str
    size: int = 0
    samples: list[float] = field(default_factory=list)
    error: str = ""
    note: str = ""

    @property
    def p50(self) -> float:
        return _pct(self.samples, 50)

    @property
    def p95(self) -> float:
        return _pct(self.samples, 95)


def _pct(samples: list[float], pct: float) -> float:
    if not samples:
        return 0.0
    if len(samples) == 1:
        return samples[0]
    ordered = sorted(samples)
    k = (len(ordered) - 1) * pct / 100.0
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    frac = k - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


def select_files(dirs, limit: int = 0, max_size_mb: int = 25):
    """收集支持的文件；按大小降序取前 limit 个（更有代表性）。"""
    found = []
    seen = set()
    for raw in dirs:
        base = Path(raw)
        if not base.is_absolute():
            base = ROOT / base
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file():
                continue
            kind = SUPPORTED.get(p.suffix.lower())
            if not kind or p.name.startswith("~$") or p.name.startswith("rt_"):
                continue
            try:
                size = p.stat().st_size
            except OSError:
                continue
            if size <= 0 or size > max_size_mb * 1024 * 1024:
                continue
            key = str(p.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            found.append(BenchFile(str(p), p.name, kind, size))
    found.sort(key=lambda f: f.size, reverse=True)
    if limit:
        found = found[:limit]
    return found


def _time_call(fn, repeat: int, warmup: int) -> list[float]:
    for _ in range(max(0, warmup)):
        fn()
    samples = []
    for _ in range(max(1, repeat)):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000.0)
    return samples


# ---------------- BeeOffice ----------------

def _bee_docx_open(path: Path):
    from beeoffice.plugins.bee_export import import_from_docx, read_docx_extras

    md = import_from_docx(str(path))
    read_docx_extras(path)
    return md


def _bee_xlsx_open(path: Path):
    from beeoffice.plugins.beesheet_workbook import read_workbook

    return read_workbook(path)


def _bee_pptx_open(path: Path):
    from beeoffice.plugins.beeshow_pptx_import import read_pptx

    return read_pptx(path)


def _bee_pdf_text(path: Path):
    import fitz

    doc = fitz.open(str(path))
    try:
        for page in doc:
            page.get_text()
    finally:
        doc.close()


def bench_bee(files: list[BenchFile], repeat: int, warmup: int) -> list[BenchResult]:
    results = []
    for f in files:
        path = Path(f.path)
        if f.kind == "docx":
            fn = lambda p=path: _bee_docx_open(p)
            op = "docx_import"
        elif f.kind == "xlsx":
            fn = lambda p=path: _bee_xlsx_open(p)
            op = "xlsx_read"
        elif f.kind == "pptx":
            fn = lambda p=path: _bee_pptx_open(p)
            op = "pptx_import"
        elif f.kind == "pdf":
            fn = lambda p=path: _bee_pdf_text(p)
            op = "pdf_text"
        else:
            continue
        r = BenchResult("beeoffice", op, f.name, f.path, f.kind, f.size)
        try:
            r.samples = _time_call(fn, repeat, warmup)
        except Exception as e:  # noqa: BLE001
            r.error = f"{type(e).__name__}: {e}"
        results.append(r)
    return results


def bench_startup(repeat: int) -> list[BenchResult]:
    """测量 import beeoffice.app 的冷/热进程启动（不含 Qt 窗口）。"""
    r = BenchResult("beeoffice", "import_app", "startup", "", "", 0)
    samples = []
    try:
        for _ in range(max(1, repeat)):
            t0 = time.perf_counter()
            subprocess.run(
                [sys.executable, "-c", "import beeoffice.app"],
                cwd=str(ROOT),
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=120,
            )
            samples.append((time.perf_counter() - t0) * 1000.0)
        r.samples = samples
    except Exception as e:  # noqa: BLE001
        r.error = f"{type(e).__name__}: {e}"
    return [r]


# ---------------- WPS COM（可选） ----------------

WPS_PROGIDS = {
    "docx": ("KWps.Application", "Documents", "Document"),
    "xlsx": ("Ket.Application", "Workbooks", "Workbook"),
    "pptx": ("Kwpp.Application", "Presentations", "Presentation"),
}


def _wps_open(com, path: Path, kind: str):
    app, collection, _ = com
    if kind == "docx":
        return getattr(app, collection).Open(str(path), ReadOnly=True)
    if kind == "xlsx":
        return getattr(app, collection).Open(str(path), ReadOnly=True, UpdateLinks=0)
    if kind == "pptx":
        return getattr(app, collection).Open(
            str(path), ReadOnly=True, WithWindow=False
        )
    raise ValueError(kind)


def _wps_close(com, opened, kind: str):
    try:
        if kind == "pptx":
            opened.Close()
        else:
            opened.Close(False)
    except Exception:  # noqa: BLE001,S110 - COM 清理失败不影响测量结果
        pass


def bench_wps(files: list[BenchFile], repeat: int, warmup: int) -> list[BenchResult]:
    try:
        import win32com.client  # type: ignore
    except Exception as e:  # noqa: BLE001
        return [
            BenchResult(
                "wps", "all", "WPS", "", "", 0,
                error=f"win32com unavailable: {type(e).__name__}: {e}",
                note="安装 pywin32 且本机装有 WPS 后可测",
            )
        ]

    results = []
    apps: dict[str, object] = {}
    try:
        for kind, (progid, _coll, _cls) in WPS_PROGIDS.items():
            kind_files = [f for f in files if f.kind == kind]
            if not kind_files:
                continue
            try:
                app = win32com.client.DispatchEx(progid)
                try:
                    app.Visible = False
                    app.DisplayAlerts = False
                except Exception:  # noqa: BLE001,S110 - 设置可选属性失败可忽略
                    pass
                apps[kind] = app
            except Exception as e:  # noqa: BLE001
                for f in kind_files:
                    results.append(
                        BenchResult(
                            "wps", f"{kind}_open", f.name, f.path,
                            f.kind, f.size,
                            error=f"WPS {progid} unavailable: {e}",
                        )
                    )
                continue
            com = (apps[kind], WPS_PROGIDS[kind][1], WPS_PROGIDS[kind][2])
            for f in kind_files:
                r = BenchResult("wps", f"{kind}_open", f.name, f.path,
                                f.kind, f.size)
                path = Path(f.path)
                for _ in range(max(0, warmup)):
                    try:
                        opened = _wps_open(com, path, kind)
                        _wps_close(com, opened, kind)
                    except Exception:  # noqa: BLE001
                        break
                samples = []
                try:
                    for _ in range(max(1, repeat)):
                        t0 = time.perf_counter()
                        opened = _wps_open(com, path, kind)
                        elapsed = (time.perf_counter() - t0) * 1000.0
                        _wps_close(com, opened, kind)
                        samples.append(elapsed)
                    r.samples = samples
                except Exception as e:  # noqa: BLE001
                    r.error = f"{type(e).__name__}: {e}"
                results.append(r)
    finally:
        for app in apps.values():
            try:
                app.Quit()
            except Exception:  # noqa: BLE001,S110 - 退出 WPS 失败不阻断
                pass
    return results


# ---------------- 报告 ----------------

def _p50(result: BenchResult) -> float:
    return result.p50


def render_markdown(results: list[BenchResult], files: list[BenchFile]) -> str:
    lines = [
        "# BeeOffice vs WPS 基准",
        "",
        f"- 时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Python：{sys.version.split()[0]}",
        f"- 文件数：{len(files)}",
        "",
        "| 引擎 | 操作 | 文件 | 大小(MB) | P50(ms) | P95(ms) | 错误 |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.engine} | {r.operation} | {r.name} | "
            f"{r.size / 1024 / 1024:.2f} | {_p50(r):.1f} | "
            f"{r.p95:.1f} | {r.error[:80]} |"
        )
    lines += ["", "## 对比（同文件、均有的引擎）", ""]
    by_key = {}
    for r in results:
        if r.samples and not r.error:
            by_key.setdefault((r.kind, r.name), {})[r.engine] = r
    lines.append("| 操作 | 文件 | BeeOffice P50 | WPS P50 | WPS/Bee |")
    lines.append("|---|---|---:|---:|---:|")
    for (kind, name), engines in by_key.items():
        bee = engines.get("beeoffice")
        wps = engines.get("wps")
        if bee and wps and wps.p50:
            ratio = bee.p50 / wps.p50
            lines.append(
                f"| {kind} | {name} | {bee.p50:.1f} ms | "
                f"{wps.p50:.1f} ms | {ratio:.2f}x |"
            )
    lines += [
        "",
        (
            "> 说明：本脚本不做主观判断；ratio > 1 表示 BeeOffice 更慢，"
            "< 1 表示更快。单机、单次文件集，结论需扩大样本。"
        ),
    ]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="WPS / BeeOffice 同机基准")
    parser.add_argument("--dir", action="append", default=[],
                        help="语料目录，可重复；默认 test+files 与 tests/fidelity/corpus")
    parser.add_argument("--limit", type=int, default=0,
                        help="最多测多少个文件（按大小降序）")
    parser.add_argument("--max-size-mb", type=int, default=25)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--no-wps", action="store_true",
                        help="只测 BeeOffice（无 WPS 机器/CI 用）")
    parser.add_argument("--startup", action="store_true",
                        help="额外测 import beeoffice.app 启动时间")
    parser.add_argument("--json", default="")
    parser.add_argument("--markdown", default="")
    args = parser.parse_args(argv)

    dirs = args.dir or list(DEFAULT_DIRS)
    files = select_files(dirs, args.limit, args.max_size_mb)
    if not files:
        print("没有找到可测文件（.docx/.xlsx/.pdf）")
        return 2
    print(f"files={len(files)} dirs={dirs} repeat={args.repeat}")

    results = bench_bee(files, args.repeat, args.warmup)
    if args.startup:
        results += bench_startup(args.repeat)
    if not args.no_wps:
        results += bench_wps(files, args.repeat, args.warmup)

    md = render_markdown(results, files)
    print(md)
    payload = {
        "timestamp": time.time(),
        "python": sys.version,
        "dirs": dirs,
        "files": [asdict(f) for f in files],
        "results": [
            {**asdict(r), "p50": r.p50, "p95": r.p95}
            for r in results
        ],
    }
    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        print(f"json -> {out}")
    if args.markdown:
        out = Path(args.markdown)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
        print(f"markdown -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
