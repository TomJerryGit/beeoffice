# -*- coding: utf-8 -*-
"""
打包产物冒烟：验证 exe 真正跑起来了，而不是"进程没退就算过"。

为什么需要它（2026-10-18 真实事故）：
    5.2.0 打出来的包，四个模块（蜜写/蜜算/蜜演/PDF 批注）**全部缺失**，
    因为 PyInstaller 把模块放进 PYZ 归档，磁盘上没有
    `beeoffice/plugins/` 目录，插件扫描直接空转。
    界面还在、日志看起来正常、进程也不崩——
    我此前"打包验收"只看"进程能起来 + 启动耗时"，于是一路绿灯。

本脚本断言四件事：
    1. 进程在观察窗口内没有退出（没崩）
    2. 日志出现「启动完成（含插件加载）」
    3. 插件数量符合预期（完整版 4，精简版 3）
    4. 没有生成 crash_*.log

用法：
    python tools/smoke_packaged.py                    # 默认 dist/BeeOffice/BeeOffice.exe
    python tools/smoke_packaged.py --exe <path> --lite
    python tools/smoke_packaged.py --keep             # 不杀进程（调试用）
"""
import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXE = ROOT / "dist" / "BeeOffice" / "BeeOffice.exe"
LOG_DIR = Path.home() / ".beeoffice_logs"
APP_LOG = LOG_DIR / "app.log"

PLUGIN_RE = re.compile(r"共加载\s*(\d+)\s*个插件")
STARTED_RE = re.compile(r"启动完成（含插件加载）")


def read_log() -> str:
    try:
        return APP_LOG.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""


def crash_logs():
    if not LOG_DIR.exists():
        return []
    return sorted(LOG_DIR.glob("crash_*.log"))


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=str(DEFAULT_EXE))
    ap.add_argument("--lite", action="store_true", help="精简版（无蜜演，3 个插件）")
    ap.add_argument("--wait", type=float, default=20.0, help="观察窗口秒数")
    ap.add_argument("--keep", action="store_true", help="结束后不杀进程")
    args = ap.parse_args(argv)

    exe = Path(args.exe)
    results = []

    def record(name, ok, detail=""):
        results.append((name, ok, detail))

    if not exe.exists():
        print(f"✗ 找不到可执行文件: {exe}")
        print("  先构建：python build.py（或 PyInstaller beeoffice.spec）")
        return 2

    # 清掉旧日志，避免读到上一次运行的内容
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    for p in [APP_LOG, *crash_logs()]:
        try:
            p.unlink()
        except OSError:
            pass

    proc = subprocess.Popen([str(exe)], cwd=str(exe.parent))
    try:
        time.sleep(args.wait)
        alive = proc.poll() is None
        log = read_log()

        record("进程存活", alive,
               "运行中" if alive else f"提前退出 code={proc.returncode}")
        record("启动完成日志", bool(STARTED_RE.search(log)))

        m = PLUGIN_RE.search(log)
        expected = 3 if args.lite else 4
        if m:
            got = int(m.group(1))
            record("插件数量", got == expected, f"{got}（期望 {expected}）")
        else:
            record("插件数量", False, "日志中没有插件加载记录")

        # 常见失败信号：插件模块导入报错
        failed_imports = re.findall(r"加载插件模块 .*? 失败: (.+)", log)
        record("插件导入无报错", not failed_imports,
               "; ".join(failed_imports[:2]))

        crashes = crash_logs()
        record("无崩溃日志", not crashes,
               crashes[0].name if crashes else "")
    finally:
        if not args.keep and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    print("\n" + "=" * 60)
    print("  打包产物冒烟")
    print("=" * 60)
    for name, ok, detail in results:
        mark = "✓" if ok else "✗"
        print(f"  {mark} {name}" + (f"  — {detail}" if detail else ""))
    failed = [r for r in results if not r[1]]
    print("-" * 60)
    print(f"  通过 {len(results) - len(failed)} / {len(results)}")
    print("=" * 60 + "\n")

    if failed and APP_LOG.exists():
        print("日志尾部（排查用）：")
        for line in read_log().splitlines()[-15:]:
            print("  " + line)

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
