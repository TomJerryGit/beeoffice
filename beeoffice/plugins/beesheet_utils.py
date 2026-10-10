# beeoffice/plugins/beesheet_utils.py
"""
蜜算工具函数：公式引用调整、列名转换、公式引用提取
"""
import re


def adjust_formula_refs(formula, row_offset, col_offset):
    """
    将公式中的单元格引用按偏移量调整（用于复制/填充公式）
    支持 $A$1（绝对）、$A1（列绝对）、A$1（行绝对）、A1（相对）
    """
    if not formula or not formula.startswith('='):
        return formula

    def _idx_to_col(idx):
        name = ''
        idx += 1
        while idx > 0:
            idx, rem = divmod(idx - 1, 26)
            name = chr(65 + rem) + name
        return name

    def _col_to_idx(col):
        idx = 0
        for ch in col.upper():
            idx = idx * 26 + (ord(ch) - ord('A') + 1)
        return idx - 1

    def replace_ref(match):
        col_dollar = match.group(1) or ''
        col_str = match.group(2)
        row_dollar = match.group(3) or ''
        row_str = match.group(4)
        new_col_str = col_str
        new_row_str = row_str
        if not col_dollar:
            new_idx = _col_to_idx(col_str) + col_offset
            if new_idx < 0:
                new_idx = 0
            new_col_str = _idx_to_col(new_idx)
        if not row_dollar:
            new_row = int(row_str) + row_offset
            if new_row < 1:
                new_row = 1
            new_row_str = str(new_row)
        return f"{col_dollar}{new_col_str}{row_dollar}{new_row_str}"

    pattern = r'(\$?)([A-Za-z]+)(\$?)(\d+)(?!\s*\()'
    return re.sub(pattern, replace_ref, formula)


def col_index_to_name(index):
    """0 基索引 → 列字母（0→A, 25→Z, 26→AA）"""
    name = ''
    while index >= 0:
        name = chr(65 + index % 26) + name
        index = index // 26 - 1
    return name


def col_name_to_index(col_str):
    """列字母 → 0 基索引（A→0, B→1, AA→26）"""
    idx = 0
    for ch in col_str.upper():
        idx = idx * 26 + (ord(ch) - ord('A') + 1)
    return idx - 1


def extract_refs_from_formula(formula):
    """
    从公式中提取所有引用的单元格坐标
    :param formula: 公式字符串（以 = 开头）
    :return: set of (row, col)，0 基索引
    """
    if not formula or not formula.startswith('='):
        return set()
    refs = set()

    # 1. 范围引用 A1:B10
    range_spans = []
    for m in re.finditer(r'\$?([A-Z]+)\$?(\d+):\$?([A-Z]+)\$?(\d+)',
                         formula.upper()):
        c1s, r1s, c2s, r2s = m.groups()
        r1, r2 = int(r1s) - 1, int(r2s) - 1
        c1, c2 = col_name_to_index(c1s), col_name_to_index(c2s)
        for r in range(min(r1, r2), max(r1, r2) + 1):
            for c in range(min(c1, c2), max(c1, c2) + 1):
                refs.add((r, c))
        range_spans.append(m.span())

    # 2. 单个引用 A1（跳过范围内的部分）
    for m in re.finditer(r'\$?([A-Z]+)\$?(\d+)', formula.upper()):
        if any(s <= m.start() < e for s, e in range_spans):
            continue
        cs, rs = m.groups()
        # 排除函数名（后跟括号）
        tail = formula[m.end():m.end() + 2]
        if tail.startswith('('):
            continue
        refs.add((int(rs) - 1, col_name_to_index(cs)))

    return refs