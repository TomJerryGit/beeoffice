# apply_b1.py
"""
v5.1 B1 差量补丁：公式引擎新增 14 个函数 + 完善 XLOOKUP。

应用 3 处改动到 beeoffice/plugins/beesheet_engine.py：
  1. 替换 _xlookup（支持 if_not_found / match_mode / search_mode）
     同时新增 _match_xlookup + _wildcard_to_regex 辅助方法
  2. _get_all_functions 的 return 字典追加 14 项
  3. clear_errors 之后追加 14 个新函数方法

安全设计：
  - 幂等：每处独立检测，已应用则跳过
  - 备份：patch 前 copy2 → .py.bak（可用 --no-backup 关闭）
  - 预检：patch 后用 ast.parse 检查语法，错误则中止
  - 原子：只有全部成功才写回

用法：
    python apply_b1.py             # 执行
    python apply_b1.py --dry-run   # 只打印会改什么
    python apply_b1.py --no-backup # 不备份（不推荐）
"""
import ast
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
TARGET = ROOT / "beeoffice" / "plugins" / "beesheet_engine.py"
BACKUP = TARGET.with_suffix(".py.bak")

DRY = "--dry-run" in sys.argv
NO_BACKUP = "--no-backup" in sys.argv


# ============================================================
# 改动 1：替换 _xlookup，新增 _match_xlookup + _wildcard_to_regex
# ============================================================
OLD_XLOOKUP = '''\
    @classmethod
    def _xlookup(cls, a, m):
        p = cls._args(a)
        if len(p) < 3:
            return "#ERROR"
        lk = str(cls._av(p[0], m))
        lr = cls._range(p[1])
        rr = cls._range(p[2])
        if not lr or not rr:
            return "#ERROR"
        (r1, c1), (r2, c2) = lr
        (rr1, rc1), _ = rr
        for r in range(r1, r2 + 1):
            if str(m.get_value(r, c1)).strip() == lk:
                return m.get_value(rr1 + (r - r1), rc1)
        return "#N/A"'''

NEW_XLOOKUP = '''\
    @classmethod
    def _xlookup(cls, a, m):
        """
        XLOOKUP(lookup_value, lookup_array, return_array,
                [if_not_found], [match_mode], [search_mode])

        v5.1 B1：
          - if_not_found：未找到时返回的默认值（默认 "#N/A"）
          - match_mode：0=精确 1=精确或下一个更大 -1=精确或下一个更小 2=通配符
          - search_mode：1=正序 -1=逆序 2=升序二分 -2=降序二分
                         （本实现只支持 1 / -1）
        """
        p = cls._args(a)
        if len(p) < 3:
            return "#ERROR"
        lk = cls._eval_arg(p[0], m)
        lr = cls._range(p[1])
        rr = cls._range(p[2])
        not_found = cls._eval_arg(p[3], m) if len(p) >= 4 else "#N/A"
        try:
            match_mode = int(cls._eval_arg(p[4], m)) if len(p) >= 5 else 0
        except (ValueError, TypeError):
            match_mode = 0
        try:
            search_mode = int(cls._eval_arg(p[5], m)) if len(p) >= 6 else 1
        except (ValueError, TypeError):
            search_mode = 1

        if not lr or not rr:
            return "#ERROR"
        (r1, c1), (r2, c2) = lr
        (rr1, rc1), (rr2, rc2) = rr

        # 收集待搜索单元格（保留原始偏移量 orig_idx）
        # 注意：不能用 enumerate 的 idx，因为 search_mode=-1 会反向列表，
        # 那时 idx 是反向后的下标，需要映射回原下标才能定位 return_array。
        items = []
        orig_idx = 0
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                items.append((orig_idx, m.get_value(r, c)))
                orig_idx += 1

        if search_mode == -1:
            items = list(reversed(items))

        for orig_i, v in items:
            if cls._match_xlookup(v, lk, match_mode):
                if rr1 == rr2:
                    target_c = rc1 + orig_i
                    if target_c <= rc2:
                        return m.get_value(rr1, target_c)
                else:
                    target_r = rr1 + orig_i
                    if target_r <= rr2:
                        return m.get_value(target_r, rc1)

        return not_found

    @classmethod
    def _match_xlookup(cls, cell_value, lookup_value, match_mode):
        """XLOOKUP / XMATCH 共用的匹配逻辑"""
        if cell_value is None:
            cell_value = ""
        if lookup_value is None:
            lookup_value = ""
        cv = str(cell_value).strip()
        lv = str(lookup_value).strip()

        if match_mode == 0:
            return cv == lv

        if match_mode == 2:
            pattern = cls._wildcard_to_regex(lv)
            return bool(re.match(pattern, cv, re.IGNORECASE | re.DOTALL))

        try:
            cnum = float(cv)
            lnum = float(lv)
        except (ValueError, TypeError):
            return False

        if match_mode == 1:
            return cnum >= lnum
        if match_mode == -1:
            return cnum <= lnum
        return False

    @staticmethod
    def _wildcard_to_regex(pattern):
        """把 Excel 通配符（* / ? / ~）转成正则"""
        result = ["^"]
        i = 0
        while i < len(pattern):
            ch = pattern[i]
            if ch == "~" and i + 1 < len(pattern):
                result.append(re.escape(pattern[i + 1]))
                i += 2
            elif ch == "*":
                result.append(".*")
                i += 1
            elif ch == "?":
                result.append(".")
                i += 1
            else:
                result.append(re.escape(ch))
                i += 1
        result.append("$")
        return "".join(result)'''


# ============================================================
# 改动 2：_get_all_functions 的 return 字典追加 14 项
# ============================================================
OLD_FUNCS_TAIL = """\
            'SLN': cls._sln, 'DB': cls._db,
        }"""

NEW_FUNCS_TAIL = """\
            'SLN': cls._sln, 'DB': cls._db,
            # ---------- v5.1 B1 新增 ----------
            'XMATCH': cls._xmatch,
            'LET': cls._let,
            'SWITCH': cls._switch,
            'XOR': cls._xor,
            'MAXIFS': cls._maxifs,
            'MINIFS': cls._minifs,
            'TEXTBEFORE': cls._textbefore,
            'TEXTAFTER': cls._textafter,
            'VALUETOTEXT': cls._valuetotext,
            'ISBLANK': cls._isblank,
            'ISNUMBER': cls._isnumber,
            'ISTEXT': cls._istext,
            'ISLOGICAL': cls._islogical,
            'ISERROR': cls._iserror,
        }"""


# ============================================================
# 改动 3：clear_errors 之后追加 14 个新方法
# ============================================================
OLD_CLEAR_ERRORS = '''\
    @classmethod
    def clear_errors(cls):
        cls._error_trace.clear()'''

NEW_EXTRA_METHODS = r'''\
    @classmethod
    def clear_errors(cls):
        cls._error_trace.clear()

    # ==================== v5.1 B1：新增函数 ====================

    @classmethod
    def _xmatch(cls, a, m):
        """XMATCH(lookup_value, lookup_array, [match_mode], [search_mode])"""
        p = cls._args(a)
        if len(p) < 2:
            return "#ERROR"
        lk = cls._eval_arg(p[0], m)
        lr = cls._range(p[1])
        try:
            match_mode = int(cls._eval_arg(p[2], m)) if len(p) >= 3 else 0
        except (ValueError, TypeError):
            match_mode = 0
        try:
            search_mode = int(cls._eval_arg(p[3], m)) if len(p) >= 4 else 1
        except (ValueError, TypeError):
            search_mode = 1

        if not lr:
            return "#ERROR"
        (r1, c1), (r2, c2) = lr

        items = []
        orig_idx = 0
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                items.append((orig_idx, m.get_value(r, c)))
                orig_idx += 1

        if search_mode == -1:
            items = list(reversed(items))

        for orig_i, v in items:
            if cls._match_xlookup(v, lk, match_mode):
                return orig_i + 1  # 1 基

        return "#N/A"

    @classmethod
    def _let(cls, a, m):
        """
        LET(name1, value1, [name2, value2, ...], calculation)

        把 name 绑定到 value 的求值结果，在 calculation 中替换后求值。
        支持嵌套引用（后面的 name 可引用前面的 name）。

        已知限制（B3 会改进）：
          - 变量名不能是函数名
          - 字符串值替换后可能冲突（含运算符时）
        """
        p = cls._args(a)
        if len(p) < 3 or len(p) % 2 == 0:
            return "#ERROR"

        bindings = {}
        for i in range(0, len(p) - 1, 2):
            name = p[i].strip().strip('"').strip("'")
            value_expr = p[i + 1].strip()
            for n, v in bindings.items():
                value_expr = cls._substitute_var(value_expr, n, v)
            try:
                value = cls._eval(value_expr, m)
            except Exception:
                value = "#ERROR"
            bindings[name] = value

        calc = p[-1].strip()
        for n, v in bindings.items():
            calc = cls._substitute_var(calc, n, v)

        return cls._eval(calc, m)

    @staticmethod
    def _substitute_var(expr, name, value):
        """把 expr 里的 name 替换为 value（字符串加引号，数字直接转）"""
        if isinstance(value, str):
            replacement = '"' + value + '"'
        elif isinstance(value, bool):
            replacement = "TRUE" if value else "FALSE"
        else:
            replacement = str(value)
        pattern = (
            r'(?<![A-Za-z0-9_\u4e00-\u9fff])' +
            re.escape(name) +
            r'(?![A-Za-z0-9_\u4e00-\u9fff])'
        )
        return re.sub(pattern, replacement, expr)

    @classmethod
    def _switch(cls, a, m):
        """SWITCH(expr, val1, result1, [val2, result2, ...], [default])"""
        p = cls._args(a)
        if len(p) < 3:
            return "#ERROR"
        expr = cls._eval_arg(p[0], m)
        remaining = p[1:]
        has_default = len(remaining) % 2 == 1
        pairs = remaining[:-1] if has_default else remaining
        default = cls._eval_arg(remaining[-1], m) if has_default else "#N/A"

        for i in range(0, len(pairs), 2):
            val = cls._eval_arg(pairs[i], m)
            if str(val) == str(expr):
                return cls._eval_arg(pairs[i + 1], m)

        return default

    @classmethod
    def _xor(cls, a, m):
        """XOR(cond1, cond2, ...) — 奇数个为 TRUE"""
        p = cls._args(a)
        count_true = 0
        for arg in p:
            try:
                if cls._safe_eval(arg.strip(), m):
                    count_true += 1
            except Exception:
                continue
        return count_true % 2 == 1

    @classmethod
    def _maxifs(cls, a, m):
        """MAXIFS(max_range, criteria_range1, criteria1, ...)"""
        p = cls._args(a)
        if len(p) < 3:
            return "#ERROR"
        mr = cls._range(p[0])
        if not mr:
            return "#ERROR"
        (mr1, mc1), (mr2, mc2) = mr

        values = []
        for r in range(mr1, mr2 + 1):
            match = True
            for i in range(1, len(p) - 1, 2):
                cr = cls._range(p[i])
                cond = p[i + 1].strip().strip('"')
                if not cr:
                    continue
                cond_row = cr[0][0] + (r - mr1)
                cond_col = cr[0][1]
                if not cls._check_cond(m.get_value(cond_row, cond_col), cond):
                    match = False
                    break
            if match:
                try:
                    values.append(float(m.get_value(r, mc1)))
                except (ValueError, TypeError):
                    pass

        return max(values) if values else 0

    @classmethod
    def _minifs(cls, a, m):
        """MINIFS(min_range, criteria_range1, criteria1, ...)"""
        p = cls._args(a)
        if len(p) < 3:
            return "#ERROR"
        mr = cls._range(p[0])
        if not mr:
            return "#ERROR"
        (mr1, mc1), (mr2, mc2) = mr

        values = []
        for r in range(mr1, mr2 + 1):
            match = True
            for i in range(1, len(p) - 1, 2):
                cr = cls._range(p[i])
                cond = p[i + 1].strip().strip('"')
                if not cr:
                    continue
                cond_row = cr[0][0] + (r - mr1)
                cond_col = cr[0][1]
                if not cls._check_cond(m.get_value(cond_row, cond_col), cond):
                    match = False
                    break
            if match:
                try:
                    values.append(float(m.get_value(r, mc1)))
                except (ValueError, TypeError):
                    pass

        return min(values) if values else 0

    @classmethod
    def _textbefore(cls, a, m):
        """TEXTBEFORE(text, delimiter, [instance_num])"""
        p = cls._args(a)
        if len(p) < 2:
            return "#ERROR"
        text = str(cls._eval_arg(p[0], m))
        delim = str(cls._eval_arg(p[1], m))
        try:
            instance = int(cls._eval_arg(p[2], m)) if len(p) >= 3 else 1
        except (ValueError, TypeError):
            instance = 1

        if instance > 0:
            pos = -1
            for _ in range(instance):
                pos = text.find(delim, pos + 1)
                if pos < 0:
                    return "#N/A"
            return text[:pos]
        else:
            pos = len(text)
            for _ in range(-instance):
                pos = text.rfind(delim, 0, pos)
                if pos < 0:
                    return "#N/A"
            return text[:pos]

    @classmethod
    def _textafter(cls, a, m):
        """TEXTAFTER(text, delimiter, [instance_num])"""
        p = cls._args(a)
        if len(p) < 2:
            return "#ERROR"
        text = str(cls._eval_arg(p[0], m))
        delim = str(cls._eval_arg(p[1], m))
        try:
            instance = int(cls._eval_arg(p[2], m)) if len(p) >= 3 else 1
        except (ValueError, TypeError):
            instance = 1

        if instance > 0:
            pos = -1
            for _ in range(instance):
                pos = text.find(delim, pos + 1)
                if pos < 0:
                    return "#N/A"
            return text[pos + len(delim):]
        else:
            pos = len(text)
            for _ in range(-instance):
                pos = text.rfind(delim, 0, pos)
                if pos < 0:
                    return "#N/A"
            return text[pos + len(delim):]

    @classmethod
    def _valuetotext(cls, a, m):
        """VALUETOTEXT(value) — 转文本"""
        v = cls._eval_arg(a, m)
        return "" if v is None else str(v)

    @classmethod
    def _isblank(cls, a, m):
        """ISBLANK(value)"""
        v = cls._eval_arg(a, m)
        return v is None or str(v).strip() == ""

    @classmethod
    def _isnumber(cls, a, m):
        """ISNUMBER(value)"""
        v = cls._eval_arg(a, m)
        if isinstance(v, bool):
            return False
        if isinstance(v, (int, float)):
            return True
        if isinstance(v, str):
            try:
                float(v)
                return True
            except (ValueError, TypeError):
                return False
        return False

    @classmethod
    def _istext(cls, a, m):
        """ISTEXT(value)"""
        v = cls._eval_arg(a, m)
        return isinstance(v, str) and v.strip() != ""

    @classmethod
    def _islogical(cls, a, m):
        """ISLOGICAL(value)"""
        v = cls._eval_arg(a, m)
        return isinstance(v, bool)

    @classmethod
    def _iserror(cls, a, m):
        """ISERROR(value)"""
        try:
            v = cls._eval(a, m)
        except Exception:
            return True
        return isinstance(v, str) and v.startswith("#")'''


# ============================================================
# 应用逻辑
# ============================================================
def _apply_one(text, old, new, marker):
    """应用单处改动。
    :return: (new_text, status)
        status ∈ {"applied", "skipped", "not_found"}
    """
    if marker in text:
        return text, "skipped"
    if old not in text:
        return text, "not_found"
    return text.replace(old, new, 1), "applied"


def main():
    print("=" * 60)
    print(f"  v5.1 B1 差量补丁  {'[DRY-RUN]' if DRY else ''}")
    print("=" * 60)
    print()

    if not TARGET.exists():
        print(f"❌ 找不到目标文件: {TARGET}")
        sys.exit(1)

    original = TARGET.read_text(encoding="utf-8")
    text = original

    patches = [
        ("1. 替换 _xlookup + 新增 2 个辅助方法",
         OLD_XLOOKUP, NEW_XLOOKUP,
         "def _match_xlookup"),

        ("2. _get_all_functions 追加 14 项",
         OLD_FUNCS_TAIL, NEW_FUNCS_TAIL,
         "'XMATCH': cls._xmatch"),

        ("3. clear_errors 之后追加 14 个新方法",
         OLD_CLEAR_ERRORS, NEW_EXTRA_METHODS,
         "def _xmatch"),
    ]

    results = []
    for name, old, new, marker in patches:
        text, status = _apply_one(text, old, new, marker)
        icon = {"applied": "✅", "skipped": "⏭️ ", "not_found": "❌"}[status]
        label = {
            "applied": "已应用",
            "skipped": "已存在，跳过",
            "not_found": "未找到目标片段",
        }[status]
        print(f"  {icon} {name}: {label}")
        results.append(status)

    print()

    if "not_found" in results:
        print("❌ 有片段未找到，中止（未写回任何改动）")
        print("   可能原因：")
        print("     - 目标文件已被手动修改")
        print("     - 目标文件版本不匹配（如已是 v5.1）")
        print("   建议：检查 beesheet_engine.py 的 _xlookup / clear_errors 方法")
        sys.exit(1)

    if all(s == "skipped" for s in results):
        print("⏭️  所有改动已应用，无需修改")
        sys.exit(0)

    # 语法预检
    try:
        ast.parse(text)
    except SyntaxError as e:
        print(f"❌ 补丁后语法错误: {e}")
        if e.lineno:
            print(f"   行 {e.lineno}: {e.text}")
        print("   中止（未写回）")
        sys.exit(1)
    print("✅ 语法检查通过")

    if DRY:
        print()
        print("DRY-RUN 完成，未做任何改动")
        print(f"  原文件行数: {len(original.splitlines())}")
        print(f"  新文件行数: {len(text.splitlines())}")
        print(f"  增量: +{len(text.splitlines()) - len(original.splitlines())} 行")
        return

    # 备份
    if not NO_BACKUP:
        if BACKUP.exists():
            print(f"⏭️  备份已存在，跳过: {BACKUP.name}")
        else:
            shutil.copy2(TARGET, BACKUP)
            print(f"📦 已备份: {BACKUP.name}")

    # 写回
    TARGET.write_text(text, encoding="utf-8")
    print(f"✅ 已写回: {TARGET.relative_to(ROOT)}")
    print(f"   行数: {len(original.splitlines())} → {len(text.splitlines())}")

    print()
    print("=" * 60)
    print("  下一步：")
    print("    pytest tests/unit/test_beesheet_engine_v51.py -v")
    print("    pytest tests/unit/test_formula_engine.py -v")
    print("    pytest tests/regression/p0/ -v")
    print("    run_tests.bat")
    print("=" * 60)


if __name__ == "__main__":
    main()