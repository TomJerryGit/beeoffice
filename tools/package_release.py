#!/usr/bin/env python3
"""把 dist/BeeOffice 打成 ZIP，并写 SHA256。"""
from __future__ import annotations

import argparse
import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--dist", default=str(ROOT / "dist" / "BeeOffice"))
    args = parser.parse_args()
    src = Path(args.dist)
    if not (src / "BeeOffice.exe").is_file():
        print(f"missing exe: {src / 'BeeOffice.exe'}")
        return 1
    out = ROOT / f"BeeOffice-v{args.version}-windows.zip"
    tmp = out.with_suffix(".zip.tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(src.rglob("*")):
            rel = p.relative_to(src)
            arc = "BeeOffice/" + rel.as_posix() + ("/" if p.is_dir() else "")
            if p.is_dir():
                z.writestr(zipfile.ZipInfo(arc), b"")
            else:
                z.write(p, arc)
    tmp.replace(out)
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    (ROOT / (out.name + ".sha256")).write_text(f"{digest}  {out.name}\n", encoding="ascii")
    print(f"ZIP={out}")
    print(f"SIZE={out.stat().st_size}")
    print(f"SHA256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
