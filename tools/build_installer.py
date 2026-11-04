# tools/build_installer.py
"""构建 Windows 安装器（Inno Setup）并生成 sha256。"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def find_iscc() -> str | None:
    env = os.environ.get("INNO_SETUP_HOME")
    candidates = []
    if env:
        candidates.append(Path(env) / "ISCC.exe")
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs"
    candidates += [
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
        local / "Inno Setup 6" / "ISCC.exe",
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    found = shutil.which("ISCC.exe") or shutil.which("iscc")
    return found


def read_version() -> str:
    text = (ROOT / "beeoffice" / "__version__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__ = "([^"]+)"', text)
    if not match:
        raise SystemExit("无法读取版本号")
    return match.group(1)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-build", action="store_true")
    args = ap.parse_args()

    iscc = find_iscc()
    if not iscc:
        print("❌ 未找到 Inno Setup (ISCC.exe)。安装：winget install JRSoftware.InnoSetup")
        return 1
    version = read_version()
    print(f"BeeOffice version: {version}")

    exe = ROOT / "dist" / "BeeOffice" / "BeeOffice.exe"
    if not args.skip_build and not exe.is_file():
        print("dist 不存在，先构建 release...")
        subprocess.run([sys.executable, str(ROOT / "beeoffice" / "build_release.py")],
                       cwd=str(ROOT), check=True)
    if not exe.is_file():
        print(f"❌ 缺少 {exe}")
        return 1

    iss = ROOT / "installer" / "BeeOffice.iss"
    cmd = [iscc, f"/DMyAppVersion={version}", str(iss)]
    print("ISCC:", " ".join(cmd))
    completed = subprocess.run(cmd, cwd=str(ROOT))
    if completed.returncode != 0:
        print(f"❌ Inno Setup 编译失败：{completed.returncode}")
        return completed.returncode
    setup = ROOT / "release-archive" / f"BeeOffice-Setup-v{version}.exe"
    if not setup.is_file():
        print(f"❌ 安装器输出不存在：{setup}")
        return 1
    digest = sha256(setup)
    (setup.parent / (setup.name + ".sha256")).write_text(
        f"{digest}  {setup.name}\n", encoding="ascii"
    )
    print(f"✅ 安装器已生成：{setup}")
    print(f"sha256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
