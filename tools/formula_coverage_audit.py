#!/usr/bin/env python3
"""Excel 公式函数覆盖审计（按财务/统计/文本/日期等分类）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from beeoffice.plugins.beesheet_engine import FormulaEngine  # noqa: E402

REFERENCE = {
    "财务": ["PMT", "FV", "PV", "NPV", "IRR", "RATE", "NPER", "SLN", "DB", "SYD", "DDB", "IPMT", "PPMT"],
    "统计": ["SUM", "AVERAGE", "MAX", "MIN", "COUNT", "COUNTA", "COUNTBLANK", "MEDIAN", "MODE", "STDEV", "VAR", "LARGE", "SMALL", "RANK", "COUNTIF", "SUMIF", "AVERAGEIF", "COUNTIFS", "SUMIFS", "AVERAGEIFS", "MAXIFS", "MINIFS", "PERCENTILE", "QUARTILE"],
    "文本": ["LEFT", "RIGHT", "MID", "LEN", "TRIM", "UPPER", "LOWER", "PROPER", "CONCATENATE", "TEXTJOIN", "FIND", "SEARCH", "REPLACE", "SUBSTITUTE", "TEXT", "VALUE", "REPT", "EXACT", "CHAR", "CODE", "CLEAN", "TEXTBEFORE", "TEXTAFTER"],
    "日期": ["TODAY", "NOW", "YEAR", "MONTH", "DAY", "DATE", "DATEDIF", "EDATE", "EOMONTH", "WEEKDAY", "WEEKNUM", "NETWORKDAYS", "WORKDAY", "HOUR", "MINUTE", "SECOND", "DAYS", "ISOWEEKNUM"],
    "查找": ["VLOOKUP", "HLOOKUP", "XLOOKUP", "INDEX", "MATCH", "CHOOSE", "XMATCH"],
    "逻辑": ["IF", "IFERROR", "IFNA", "AND", "OR", "NOT", "IFS", "SWITCH", "XOR"],
    "动态数组": ["FILTER", "SORT", "UNIQUE", "SEQUENCE"],
    "数学": ["ROUND", "ROUNDUP", "ROUNDDOWN", "POWER", "MOD", "INT", "TRUNC", "CEILING", "FLOOR", "SUMPRODUCT", "ABS", "SQRT", "EXP", "LN", "LOG", "SIGN", "PI"],
}


def audit() -> dict:
    supported = set(FormulaEngine._get_all_functions().keys())
    categories = {}
    total = hit = 0
    for cat, names in REFERENCE.items():
        ok = [n for n in names if n in supported]
        missing = [n for n in names if n not in supported]
        total += len(names); hit += len(ok)
        categories[cat] = {"supported": ok, "missing": missing, "coverage": round(len(ok) / len(names), 3)}
    return {"total": total, "supported": hit, "coverage": round(hit / total, 3),
            "categories": categories, "all_registered": len(supported)}


def main() -> int:
    result = audit()
    out = ROOT.parent / "analysis" / "formula-coverage.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for cat, info in result["categories"].items():
        print(f"{cat}: {info['coverage']:.1%} missing={','.join(info['missing']) or '-'}")
    print(f"TOTAL {result['coverage']:.1%} ({result['supported']}/{result['total']}) registered={result['all_registered']}")
    print("REPORT", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
