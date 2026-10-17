# -*- coding: utf-8 -*-
"""
蜜算公式引擎冒烟检查（Excel 语义基线）

背景（路线图 WP-11）：
    现有测试几乎只用 `>` / `<`，没有一条 `=IF(A1=1,…)`，于是"引擎不支持
    Excel 的 `=` 比较符"这个 P0 一直没被发现。本脚本用**Excel 的写法**
    做最小验证集，作为修复前后的事实基线。

用法：
    python tools/smoke_formula.py
退出码：
    0 全部符合 Excel 语义；1 存在偏差（打印期望值与实际值）
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from beeoffice.plugins.beesheet_engine import FormulaEngine  # noqa: E402


class _Model:
    """最小模型：A1=5, A2=10, A3=20。"""

    def __init__(self, rows):
        self._rows = rows

    def get_value(self, r, c):
        try:
            return self._rows[r][c]
        except IndexError:
            return None


DATA = [[5], [10], [20]]

# (公式, 期望值, 说明)
CASES = [
    ("=A1+A2", 15, "算术：引用相加"),
    ("=SUM(A1:A3)", 35, "聚合：区域求和"),
    ("=SUM(A1:A3)*2", 70, "聚合后继续运算"),
    ("=ROUND(3.14159,2)", 3.14, "嵌套：四舍五入"),
    ("=COUNTIF(A1:A3,\">5\")", 2, "条件计数"),
    ("=IF(A1>3,1,2)", 1, "比较：大于"),
    ("=IF(A1=5,1,2)", 1, "比较：等于（Excel 写法）"),
    ("=IF(A1<>5,1,2)", 2, "比较：不等于（Excel 写法）"),
    ("=IF(A1=5,\"yes\",\"no\")", "yes", "等于 + 字符串结果"),
]


def main():
    model = _Model(DATA)
    failed = 0
    width = max(len(c[0]) for c in CASES)
    for formula, expected, desc in CASES:
        try:
            actual = FormulaEngine.evaluate(formula, model)
        except Exception as e:  # 引擎本身抛异常也算失败
            actual = f"<EXC {type(e).__name__}: {e}>"
        ok = actual == expected or (
            isinstance(expected, float)
            and isinstance(actual, (int, float))
            and abs(float(actual) - expected) < 1e-9
        )
        flag = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"[{flag}] {formula:<{width}} 期望={expected!r:<8} 实际={actual!r}   # {desc}")

    print(f"\n共 {len(CASES)} 条，失败 {failed} 条")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
