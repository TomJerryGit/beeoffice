"""本地/CI 发布前检查（M1A 零成本门禁）。

检查内容：
  - 版本号与 CHANGELOG / Release Notes 一致
  - ZIP / 安装包存在，SHA-256 文件与实际一致
  - ZIP 可解压，且包含 BeeOffice/BeeOffice.exe
  - 安全扫描无 high 项
  - 可选：coverage.json 通过核心 100% 门槛
  - Release Notes 包含未签名/无干净机验收/Win11 未验证披露

用法：
    python tools/release_check.py
    python tools/release_check.py --skip-coverage
    python tools/release_check.py --require-signed
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ZIP_TEMPLATE = "BeeOffice-v{version}-windows.zip"
SETUP_TEMPLATE = "BeeOffice-Setup-v{version}.exe"
REQUIRED_NOTES = (
    "未签名",
    "未做 Windows 10/11 干净机安装验收",
    "Windows 11 未验证",
)


def read_version() -> str:
    text = (ROOT / "beeoffice" / "__version__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not match:
        raise SystemExit("无法读取版本号")
    return match.group(1)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_hash_file(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.is_file():
        return [f"缺少文件: {path}"]
    sum_file = Path(str(path) + ".sha256")
    if not sum_file.is_file():
        return [f"缺少校验文件: {sum_file}"]
    expected = ((sum_file.read_text(encoding="ascii", errors="ignore").strip().split() or [""])[0]).lower()
    actual = sha256(path).lower()
    if expected != actual:
        errors.append(f"SHA256 不一致: {path.name} expected={expected} actual={actual}")
    return errors


def check_zip(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.is_file():
        return [f"缺少 ZIP: {path}"]
    try:
        with zipfile.ZipFile(path) as z:
            bad = z.testzip()
            if bad is not None:
                errors.append(f"ZIP 损坏，首个错误文件: {bad}")
            names = set(z.namelist())
            if "BeeOffice/BeeOffice.exe" not in names:
                errors.append("ZIP 缺少 BeeOffice/BeeOffice.exe")
    except Exception as e:
        errors.append(f"ZIP 打开失败: {e}")
    return errors


def check_signature(path: Path) -> str:
    if os.name != "nt":
        return "Unknown"
    safe = str(path).replace("'", "''")
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-AuthenticodeSignature -LiteralPath '{safe}').Status"],
            text=True, timeout=30,
        )
        return out.strip() or "Unknown"
    except Exception:
        return "Unknown"


def check_notes(version: str) -> list[str]:
    path = ROOT / "docs" / f"release-notes-v{version}.md"
    if not path.is_file():
        return [f"缺少 Release Notes: {path}"]
    text = path.read_text(encoding="utf-8")
    errors = [f"Release Notes 缺少披露: {phrase}" for phrase in REQUIRED_NOTES if phrase not in text]
    return errors


def check_changelog(version: str) -> list[str]:
    path = ROOT / "CHANGELOG.md"
    text = path.read_text(encoding="utf-8")
    if not re.search(rf"^## \[{re.escape(version)}\]", text, re.MULTILINE):
        return [f"CHANGELOG 缺少版本段落: {version}"]
    return []


def check_security() -> list[str]:
    try:
        out = subprocess.check_output(
            [sys.executable, str(ROOT / "tools" / "security_scan.py"), "--json"],
            cwd=str(ROOT), text=True, timeout=60,
        )
        findings = json.loads(out)
    except Exception as e:
        return [f"安全扫描执行失败: {e}"]
    high = [f for f in findings if f.get("severity") == "high"]
    if high:
        return [f"安全扫描存在 high: {f.get('path')}:{f.get('line')} {f.get('kind')}" for f in high]
    guarded = [f for f in findings if f.get("severity") == "guarded"]
    for f in guarded:
        print(f"[WARN] guarded {f.get('kind')} {f.get('path')}:{f.get('line')}")
    return []


def check_coverage() -> list[str]:
    cov = ROOT / "coverage.json"
    if not cov.is_file():
        return ["缺少 coverage.json（先运行 pytest --cov ... --cov-report=json）"]
    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "coverage_gate.py"), str(cov)],
            cwd=str(ROOT), text=True, timeout=60,
        )
    except Exception as e:
        return [f"覆盖率门槛执行失败: {e}"]
    return [] if result.returncode == 0 else ["核心覆盖率门槛未通过"]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="BeeOffice 发布前检查")
    parser.add_argument("--skip-coverage", action="store_true")
    parser.add_argument("--skip-security", action="store_true")
    parser.add_argument("--require-signed", action="store_true")
    args = parser.parse_args(argv)

    version = read_version()
    zip_path = ROOT / ZIP_TEMPLATE.format(version=version)
    setup_path = ROOT / "release-archive" / SETUP_TEMPLATE.format(version=version)

    errors: list[str] = []
    errors += check_changelog(version)
    errors += check_notes(version)
    errors += check_hash_file(zip_path)
    errors += check_hash_file(setup_path)
    errors += check_zip(zip_path)

    sig = check_signature(setup_path)
    print(f"安装包签名状态: {sig}")
    if args.require_signed and sig != "Valid":
        errors.append(f"要求签名，但安装包状态为 {sig}")

    if not args.skip_security:
        errors += check_security()
    if not args.skip_coverage:
        errors += check_coverage()

    if errors:
        print("\n发布检查失败：")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"\n发布检查通过：v{version}")
    print(f"  ZIP:   {zip_path.name}")
    print(f"  Setup: {setup_path.name}")
    if sig != "Valid":
        print("  [WARN] 安装包未签名；只能按 Beta/Unsigned 发布")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
