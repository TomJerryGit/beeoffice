# fix_pytest_ini.py
"""在 pytest.ini 的 norecursedirs 末尾加 tests/helpers。"""
from pathlib import Path

ini = Path(__file__).parent / "pytest.ini"
if not ini.exists():
    print(f"❌ 找不到 {ini}")
    raise SystemExit(1)

text = ini.read_text(encoding="utf-8")
if "tests/helpers" in text:
    print("✅ 已包含 tests/helpers，无需修改")
    raise SystemExit(0)

# 找 norecursedirs 块，末尾插一行
lines = text.split("\n")
out = []
in_block = False
inserted = False
for i, line in enumerate(lines):
    stripped = line.strip()
    # 进入 norecursedirs 块
    if stripped.startswith("norecursedirs"):
        in_block = True
        out.append(line)
        continue
    # 块内：以空白开头（缩进）的非空行
    if in_block:
        if line and (line[0] in " \t"):
            out.append(line)
            continue
        else:
            # 块结束，插在末尾前
            if not inserted:
                out.append("    tests/helpers")
                inserted = True
            in_block = False
            out.append(line)
            continue
    out.append(line)

if not inserted and in_block:
    out.append("    tests/helpers")

ini.write_text("\n".join(out), encoding="utf-8")
print("✅ 已修改 pytest.ini，在 norecursedirs 加了 tests/helpers")