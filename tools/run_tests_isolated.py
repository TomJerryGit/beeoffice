#!/usr/bin/env python3
# tools/run_tests_isolated.py
"""
按测试文件隔离运行 pytest，规避已知的"进程退出期原生崩溃"。

背景
----
本项目的全量 pytest 运行会出现 `Windows fatal exception: code 0x80000003`
（STATUS_BREAKPOINT），发生在**解释器退出阶段**（faulthandler 的回溯末端是
`runpy._run_module_as_main`），因此：

  * 单独运行某个测试文件时它往往仍会打印结果，但进程以非 0 退出；
  * 与其它文件一起运行时，崩溃点会漂移到别的文件里，表现为"顺序污染"，
    整轮运行拿不到 summary。

本脚本对每个测试文件起一个独立的 pytest 进程，把输出落到文件（不用管道，
避免在受限沙箱里 EPERM），再解析 summary 行做汇总。这样：

  * 真正的断言失败不会被"退出期崩溃"掩盖；
  * 崩溃的文件被单独标记出来（`CRASH`），成为待修清单而不是噪声。

用法
----
    python tools/run_tests_isolated.py              # 全部
    python tools/run_tests_isolated.py tests/unit   # 只要某个目录
    python tools/run_tests_isolated.py --quiet
"""
import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
LOG_DIR = ROOT / "_ptmp" / "isolated"
COUNTS = ("passed", "failed", "error", "skipped", "xfailed", "xpassed")
SUMMARY_RE = re.compile(r"(\d+)\s+(passed|failed|error|errors|skipped|xfailed|xpassed)")


def discover(targets):
    files = []
    for t in targets:
        p = (ROOT / t).resolve()
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            files.extend(sorted(p.rglob("test_*.py")))
    return sorted(set(files))


def parse_summary(text):
    """从输出里取最后一条 summary 行。"""
    for line in reversed(text.strip().splitlines()):
        stripped = line.strip().strip("= ")
        if " in " not in stripped:
            continue
        hits = SUMMARY_RE.findall(stripped)
        if not hits:
            continue
        counts = {k: 0 for k in COUNTS}
        for num, kind in hits:
            if kind == "errors":
                kind = "error"
            counts[kind] = int(num)
        return counts, stripped
    return None, None


def run_one(path):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / (path.relative_to(ROOT).as_posix().replace("/", "__") + ".log")
    cmd = [
        sys.executable, "-m", "pytest", str(path),
        "-q", "--no-header",
        "-p", "no:cacheprovider",
        "-o", "log_file=",
        "--timeout=180",
        "--basetemp", str(ROOT / "_ptmp" / "basetemp"),
    ]
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONIOENCODING"] = "utf-8"

    started = time.perf_counter()
    with open(log_file, "w", encoding="utf-8", errors="replace") as fh:
        try:
            # 输出重定向到文件而不是管道：受限沙箱下管道可能 EPERM
            subprocess.run(
                cmd, cwd=str(ROOT), env=env,
                stdout=fh, stderr=subprocess.STDOUT, timeout=600,
            )
        except subprocess.TimeoutExpired:
            fh.write("\n*** TIMEOUT ***\n")
    elapsed = time.perf_counter() - started

    text = log_file.read_text(encoding="utf-8", errors="replace")
    counts, summary = parse_summary(text)
    crashed = ("Windows fatal exception" in text) or ("Fatal Python error" in text)
    if "*** TIMEOUT ***" in text:
        counts = counts or {k: 0 for k in COUNTS}
        return counts, "TIMEOUT", crashed, elapsed, log_file
    if counts is None:
        return {k: 0 for k in COUNTS}, "CRASH(no summary)", crashed, elapsed, log_file
    return counts, summary, crashed, elapsed, log_file


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("targets", nargs="*", default=["tests"])
    ap.add_argument("--quiet", action="store_true", help="只打印有问题的文件")
    args = ap.parse_args()

    files = discover(args.targets or ["tests"])
    if not files:
        print("no test files found")
        return 2

    totals = {k: 0 for k in COUNTS}
    bad, crashed_files, elapsed_total = [], [], 0.0

    print(f"isolated run: {len(files)} test files\n")
    for i, path in enumerate(files, 1):
        rel = path.relative_to(ROOT).as_posix()
        counts, summary, crashed, elapsed, log_file = run_one(path)
        elapsed_total += elapsed
        for k in COUNTS:
            totals[k] += counts.get(k, 0)

        failed = counts.get("failed", 0) + counts.get("error", 0)
        flag = ""
        if summary == "TIMEOUT":
            flag = "TIMEOUT"
        elif summary and summary.startswith("CRASH"):
            flag = "NO-SUMMARY"
        elif crashed:
            flag = "exit-crash"
        if failed or flag:
            bad.append((rel, summary, log_file))
        if crashed or flag:
            crashed_files.append(rel)

        if failed or flag or not args.quiet:
            tag = f"[{flag}]" if flag else ("[FAIL]" if failed else "[ok]")
            print(f"  {i:>3}/{len(files)} {tag:<12} {rel:<58} "
                  f"{summary or '':<34} {elapsed:5.1f}s")

    print("\n" + "=" * 78)
    print(f"files                : {len(files)}")
    if totals["xfailed"] or totals["xpassed"]:
        print(f"xfail/xpass          : {totals['xfailed']} / {totals['xpassed']}")
    print(f"passed               : {totals['passed']}")
    print(f"failed               : {totals['failed']}")
    print(f"error                : {totals['error']}")
    print(f"skipped              : {totals['skipped']}")
    print(f"wall time (sum)      : {elapsed_total:.1f}s")
    print(f"files with exit-crash: {len(crashed_files)}")
    for rel in crashed_files:
        print(f"    CRASH  {rel}")
    print("=" * 78)

    if bad:
        print("\n需要处理的文件：")
        for rel, summary, log_file in bad:
            print(f"  - {rel}\n      {summary}\n      日志: {log_file}")

    return 1 if totals["failed"] or totals["error"] else 0


if __name__ == "__main__":
    sys.exit(main())
