"""覆盖率门槛：核心模块 100%，GUI 只报告不设硬门槛。

用法：
    pytest tests --cov=beeoffice --cov-report=json:coverage.json
    python tools/coverage_gate.py coverage.json

核心模块清单是"纯逻辑/数据/协议"层，不包含 Qt 弹窗、导出集成、
安装器和构建脚本。新增核心模块时必须先更新 CORE_MODULES。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# 核心模块：算法、数据模型、配置、云协议、文本转换。
CORE_MODULES = [
    "beeoffice/cloud_sync/base.py",
    "beeoffice/cloud_sync/webdav.py",
    "beeoffice/i18n.py",
    "beeoffice/plugins/beesheet_model.py",
    "beeoffice/plugins/beesheet_utils.py",
    "beeoffice/plugins/data_insights.py",
    "beeoffice/plugins/formula_engine.py",
    "beeoffice/plugins/macro_recorder.py",
    "beeoffice/plugins/nl_formula.py",
    "beeoffice/secret_store.py",
    "beeoffice/settings.py",
    "beeoffice/update_checker.py",
]


def normalize(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def main() -> int:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "coverage.json")
    if not src.exists():
        print(f"coverage json 不存在: {src}")
        return 2

    data = json.loads(src.read_text(encoding="utf-8"))
    files = {normalize(k): v for k, v in data.get("files", {}).items()}

    failures = []
    print("核心模块覆盖率：")
    for name in CORE_MODULES:
        entry = files.get(name)
        if entry is None:
            failures.append(name)
            print(f"  MISSING  {name}")
            continue
        summary = entry["summary"]
        pct = summary["percent_covered"]
        print(
            f"  {pct:6.2f}%  {summary['missing_lines']:4d} missed  {name}"
        )
        if summary["missing_lines"]:
            failures.append(name)

    total = data.get("totals", {}).get("percent_covered")
    if total is not None:
        print(f"\n全仓（含 GUI）覆盖率：{total:.2f}%")
        print("GUI 覆盖率仅报告，不设 100% 门槛。")

    if failures:
        print(f"\n核心门槛失败：{len(failures)} 个模块未达到 100%")
        return 1
    print("\n核心模块 100% 门槛通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
