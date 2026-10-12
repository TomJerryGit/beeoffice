# tests/unit/test_beesheet_utils_refs.py
"""
优化规划 §2.5 回归：公式引用调整 / 提取的边界正确性。

原缺陷
------
`adjust_formula_refs`（复制、填充公式时用）的正则为

    r'(\\$?)([A-Za-z]+)(\\$?)(\\d+)(?!\\s*\\()'

末尾的否定前瞻本意是排除函数名（如 `SUM(`），但它只看**数字之后**的一个字符，
而 `\\d+` 只吃下第一位数字。于是 `=LOG10(A1)` 中的 `LOG1` 被当成
"列 LOG、行 1"的引用（后面的 `0` 不在匹配内），LOG 列右移一位后把函数名
改写成 `LOH10`：

    =LOG10(A1)      offset(+0,+1) -> =LOH10(B1)
    =A1+LOG10(B1)   offset(+1,+1) -> =B2+LOH20(C2)

复制/填充含 `LOG10` 的公式会**静默产出错公式**。

`extract_refs_from_formula`（公式审计用）的单引用正则没有边界约束，
同样会把 `LOG1` 当成引用，进而把 `LOG10(A1)` 报成引用了 LOG 列。

修复：前后都加标识符边界，行号之后既不能是字母/数字，也不能紧跟 `(`
（函数调用）；列名限制为 1~3 个字母（Excel 上限 XFD）。
"""
import pytest

from beeoffice.plugins.beesheet_utils import (
    adjust_formula_refs,
    extract_refs_from_formula,
)


# ==================== 调整引用：不得改坏函数名 ====================

@pytest.mark.parametrize("formula,row_off,col_off,expected", [
    # 函数名含数字：整体不能被当成单元格引用
    ("=LOG10(A1)", 0, 1, "=LOG10(B1)"),
    ("=LOG10(A1)", 1, 1, "=LOG10(B2)"),
    ("=LOG10(A1)", 1, 0, "=LOG10(A2)"),
    ("=A1+LOG10(B1)", 1, 1, "=B2+LOG10(C2)"),
    ("=SUM(LOG10(B1))", 0, 1, "=SUM(LOG10(C1))"),
    ("=LOG10(100)", 1, 1, "=LOG10(100)"),
    # 常规引用仍要正确偏移
    ("=A1+1", 1, 1, "=B2+1"),
    ("=SUM(A1:A3)", 1, 0, "=SUM(A2:A4)"),
    ("=ROUND(A1,2)", 1, 0, "=ROUND(A2,2)"),
    ("=SUM(A1:B2)+C3", 1, 1, "=SUM(B2:C3)+D4"),
    # 绝对引用不参与偏移
    ("=$A$1+A1", 1, 1, "=$A$1+B2"),
    ("=$A1+A$1", 1, 1, "=$A2+B$1"),
])
def test_adjust_formula_refs(formula, row_off, col_off, expected):
    assert adjust_formula_refs(formula, row_off, col_off) == expected


def test_log10_is_never_rewritten():
    """专门守住这个具体缺陷：函数名 LOG10 一个字符都不能变。"""
    for row_off in (0, 1, 2, -1):
        for col_off in (0, 1, 2, -1):
            out = adjust_formula_refs("=LOG10(A1)", row_off, col_off)
            assert out.startswith("=LOG10("), (
                f"offset({row_off},{col_off}) 把函数名改坏了: {out}"
            )


def test_other_digit_suffixed_functions_are_safe():
    """同类函数名（含数字）都不应被误改。"""
    for name in ("LOG10", "ATAN2", "BIN2DEC", "DEC2BIN", "CHISQ2"):
        out = adjust_formula_refs(f"={name}(A1)", 1, 1)
        assert f"{name}(" in out, f"{name} 被改坏: {out}"


def test_non_ascii_and_plain_text_untouched():
    assert adjust_formula_refs("普通文本", 1, 1) == "普通文本"
    assert adjust_formula_refs("A1", 1, 1) == "A1"      # 非公式（无 =）不动
    assert adjust_formula_refs("", 1, 1) == ""


# ==================== 提取引用：不得凭空造出引用 ====================

def test_extract_refs_ignores_function_names_with_digits():
    # 只有 A1 是真正的引用；原实现会额外报出 LOG 列
    assert extract_refs_from_formula("=LOG10(A1)") == {(0, 0)}
    assert extract_refs_from_formula("=LOG10(100)") == set()
    assert extract_refs_from_formula("=SUM(LOG10(B1))") == {(0, 1)}


def test_extract_refs_handles_ranges_and_absolutes():
    # A1:A3 → 三行
    assert extract_refs_from_formula("=SUM(A1:A3)") == {(0, 0), (1, 0), (2, 0)}
    # 绝对引用同样被识别
    assert extract_refs_from_formula("=$A$1+A1") == {(0, 0)}
    # 两个散引用
    assert extract_refs_from_formula("=A1+B2") == {(0, 0), (1, 1)}


def test_extract_refs_range_not_double_counted():
    """范围已展开，不应再把端点当作单独引用重复统计。"""
    refs = extract_refs_from_formula("=SUM(A1:A3)")
    assert refs == {(0, 0), (1, 0), (2, 0)}
