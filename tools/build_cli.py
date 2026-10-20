# tools/build_cli.py
"""
**构建独立 `beecmd.exe`**（阶段③交付物：外部用户无需 Python/GUI 也能用一条命令）。

## 为什么
GUI 安装包（224.7 MB）按设计不含 `beecmd`/`tools`。要拿到
"外部用户不开 GUI 用一条命令完成一件真实工作"的证据，最直接的门槛是
**用户机器上不用装 Python**。本工具用 PyInstaller 打一个单文件 exe：
零 Qt、体积小、可在 CMD/PowerShell 直接调用。

## 支持矩阵（与 `beecmd` 的能力一致）
* ✅ 表格：xlsx/csv/json/md/html 互转、merge 多表汇总、verify、clean 表格清洗
* ✅ 文稿：md → beshow（`.beshow` 是纯 JSON 格式，不需要 Qt）
* ✅ AI：ai 六任务（调 OpenAI 兼容端点，本地 Ollama 不需要 Key）
* ❌ md → docx / pdf：这两条走蜜写的 Qt 打印引擎（`QT_OUTPUTS`），
  本 exe 明确排除 PySide6 —— 需要时用 GUI 或源码方式运行

## 用法
    python tools/build_cli.py                 # 构建 + 生成 zip + sha256
    python tools/build_cli.py --no-zip        # 只构建 exe
产物：`dist-cli/beecmd.exe`、`dist-cli/BeeOffice-beecmd-vX.Y.Z-windows.zip`
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "tools" / "beecmd_entry.py"
DIST = ROOT / "_ptmp" / "dist_cli"
WORK = ROOT / "_ptmp" / "build_cli"

#: 明确排除的模块（零 Qt + 不把科学计算全家桶塞进来）
EXCLUDES = [
    "PySide6", "shiboken6", "PySide2", "PyQt5", "PyQt6",
    "tkinter", "matplotlib", "scipy", "IPython", "jupyter",
]

#: 随压缩包发布的说明文件
README_TEXT = """BeeOffice beecmd v{version}（独立命令行，零 Qt）
====================================================

用法：把解压后的 beecmd.exe 放到任意目录，在 CMD/PowerShell 里运行：

  beecmd.exe --version
  beecmd.exe info 你的表格.xlsx
  beecmd.exe convert 表格.xlsx --to csv -o 表格.csv
  beecmd.exe merge 一月.xlsx 二月.xlsx -o 汇总.xlsx
  beecmd.exe clean 脏数据.csv -o 清洗后.xlsx --plan 计划.json
  beecmd.exe ai summarize 报告.md --api-base http://127.0.0.1:11434/v1 --model llama3.2

支持（不依赖 Qt）：
  * 表格 xlsx/csv/json/md/html 互转、merge、verify、clean
  * md → beshow（.beshow 是纯 JSON）
  * ai 六任务（本地 Ollama 不需要 Key）

不支持：
  * md → docx / pdf（这两条依赖蜜写的 Qt 打印引擎；请用 GUI 或源码运行）

注意：
  * 这是未签名的 exe，Windows SmartScreen 可能提示"未知发布者"，请核对
    随附的 SHA256SUMS 后再运行；
  * AI 任务需要可用的 OpenAI 兼容端点（本地 Ollama 或云端 Key）。

构建信息：BeeOffice {app_version} / beecmd {version}
"""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(no_zip: bool = False) -> dict:
    from beeoffice.__version__ import __version__ as app_version
    from beeoffice.beecmd import __version__ as cli_version

    DIST.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    exe_path = DIST / "beecmd.exe"
    if exe_path.exists():
        exe_path.unlink()

    cmd = [
        sys.executable, "-m", "PyInstaller", str(ENTRY),
        "--onefile", "--name", "beecmd",
        "--distpath", str(DIST), "--workpath", str(WORK),
        "--specpath", str(WORK), "--noconfirm", "--clean",
        "--paths", str(ROOT),
        "--log-level", "WARN",
    ]
    for module in EXCLUDES:
        cmd += ["--exclude-module", module]

    started = time.perf_counter()
    completed = subprocess.run(cmd, cwd=str(ROOT))
    elapsed = time.perf_counter() - started
    if completed.returncode != 0 or not exe_path.is_file():
        raise SystemExit(f"PyInstaller 构建失败（exit={completed.returncode}）")

    result = {
        "app_version": app_version,
        "cli_version": cli_version,
        "exe": str(exe_path),
        "size_mb": round(exe_path.stat().st_size / 1024 / 1024, 1),
        "sha256": _sha256(exe_path),
        "elapsed_s": round(elapsed, 1),
        "excludes": EXCLUDES,
    }
    if not no_zip:
        result.update(_make_zip(exe_path, cli_version, app_version))
    return result


def _make_zip(exe_path: Path, cli_version: str, app_version: str) -> dict:
    stem = f"BeeOffice-beecmd-v{cli_version}-windows"
    zip_path = DIST / f"{stem}.zip"
    readme = DIST / "README-beecmd.txt"
    readme.write_text(
        README_TEXT.format(version=cli_version, app_version=app_version),
        encoding="utf-8",
    )
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(exe_path, arcname="beecmd.exe")
        archive.write(readme, arcname="README-beecmd.txt")
    sha = _sha256(zip_path)
    sha_path = DIST / f"{stem}.zip.sha256"
    sha_path.write_text(f"{sha}  {zip_path.name}\n", encoding="utf-8")
    return {
        "zip": str(zip_path),
        "zip_size_mb": round(zip_path.stat().st_size / 1024 / 1024, 1),
        "zip_sha256": sha,
        "readme": str(readme),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="构建独立 beecmd.exe")
    parser.add_argument("--no-zip", action="store_true", help="只构建 exe，不打包")
    args = parser.parse_args(argv)
    result = build(no_zip=args.no_zip)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
