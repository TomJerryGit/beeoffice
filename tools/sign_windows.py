# tools/sign_windows.py
"""Windows 代码签名（signtool）：PFX 文件或证书指纹。"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
from pathlib import Path


def find_signtool() -> str | None:
    kits = Path(r"C:\Program Files (x86)\Windows Kits\10\bin")
    if kits.is_dir():
        for child in sorted(kits.iterdir(), reverse=True):
            candidate = child / "x64" / "signtool.exe"
            if candidate.is_file():
                return str(candidate)
    return shutil.which("signtool.exe") or shutil.which("signtool")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    args = ap.parse_args()

    signtool = find_signtool()
    if not signtool:
        print("❌ 未找到 signtool.exe，请安装 Windows SDK Signing Tools")
        return 1

    timestamp = os.environ.get(
        "BEEOFFICE_SIGN_TIMESTAMP", "http://timestamp.digicert.com"
    )
    cmd = [signtool, "sign", "/fd", "SHA256", "/tr", timestamp, "/td", "SHA256"]
    pfx = os.environ.get("BEEOFFICE_SIGN_PFX")
    cert_sha1 = os.environ.get("BEEOFFICE_SIGN_CERT_SHA1")
    if pfx:
        if not Path(pfx).is_file():
            print(f"❌ BEEOFFICE_SIGN_PFX 不存在：{pfx}")
            return 1
        cmd += ["/f", pfx]
        if os.environ.get("BEEOFFICE_SIGN_PASSWORD"):
            cmd += ["/p", os.environ["BEEOFFICE_SIGN_PASSWORD"]]
    elif cert_sha1:
        cmd += ["/sha1", cert_sha1]
    else:
        print("❌ 未配置证书：BEEOFFICE_SIGN_PFX 或 BEEOFFICE_SIGN_CERT_SHA1")
        return 1

    signed = []
    for name in args.files:
        path = Path(name)
        if not path.is_file():
            print(f"❌ 待签名文件不存在：{path}")
            return 1
        print(f"签名：{path}")
        completed = subprocess.run(cmd + [str(path)])
        if completed.returncode != 0:
            return completed.returncode
        verify = subprocess.run(
            [signtool, "verify", "/pa", str(path)],
            stdout=subprocess.DEVNULL,
        )
        if verify.returncode != 0:
            print(f"❌ 签名校验失败：{path}")
            return verify.returncode
        signed.append(path)
    for path in signed:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        Path(str(path) + ".sha256").write_text(
            f"{digest}  {path.name}\n", encoding="ascii"
        )
        print(f"sha256: {digest}  {path.name}")
    print("✅ 签名完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
