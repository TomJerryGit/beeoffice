# apply_b1_fix.py
"""
v5.1 B1 三处失败的修复补丁。

应用 3 处改动到 beeoffice/plugins/beesheet_engine.py：

  1. _eval 函数识别正则：(.+) → (.*)
     修复 =XMATCH() / =SUM() 等空参数函数识别不到的问题。

  2. _xlookup 的 match_mode=1/-1 语义：
     从"第一个满足条件"改为"最接近的"（Excel 语义）。
     - match_mode=1：找 ≥ lookup 里最小的
     - match_mode=-1：找 ≤ lookup 里最大的

  3. _switch 数值比较归一化：
     "30" / "30.0" / 30 / 30.0 之间可正确比较。

安全设计：
  - 幂等：每处独立检测，已应用则跳过
  - 备份：patch 前 copy2 → .py.bak2（避免覆盖原 B1 备份）
  - 预检：ast.parse 通过才写回
  - 原子：全部成功才写回

用法：
    python apply_b1_fix.py             # 执行
    python apply_b1_fix.py --dry-run   # 只打印
    python apply_b1_fix.py --no-backup # 不备份
"""
import ast
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
TARGET = ROOT / "beeoffice" / "plugins" / "beesheet_engine.py"
BACKUP = TARGET.with_suffix(".py.bak2")

DRY = "--dry-run" in sys.argv
NO_BACKUP = "--no-backup" in sys.argv


# ============================================================
# 改动 1：_eval 函数识别正则支持空参数
# ============================================================
OLD_EVAL_REGEX = '''        m = re.match(r'^(\\w+)\\((.+)\\)$', expr_stripped, re.IGNORECASE)
        if m:
            return cls._func(m.group(1).upper(),
                             cls._substitute_named(m.group(2), model), model)'''

NEW_EVAL_REGEX = '''        # v5.1 B1fix：\\(.+\\) → \\((.*)\\)，允许空参数（如 =SUM() / =XMATCH()）
        # 空参数会走 _func 分支，由具体函数决定返回 #ERROR 还是默认值
        m = re.match(r'^(\\w+)\\((.*)\\)$', expr_stripped, re.IGNORECASE)
        if m:
            return cls._func(m.group(1).upper(),
                             cls._substitute_named(m.group(2), model), model)'''


# ============================================================
# 改动 2：_xlookup 的 match_mode=1/-1 改为"最接近"
# ============================================================
OLD_XLOOKUP_BODY = '''        if search_mode == -1:
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

        return not_found'''

NEW_XLOOKUP_BODY = '''        if search_mode == -1:
            items = list(reversed(items))

        # ---------- v5.1 B1fix：match_mode=1/-1 找"最接近的" ----------
        # 修复前：match_mode=±1 用"第一个满足条件"（_match_xlookup），
        #         例如 25 会匹配到 10（第一个 ≤ 25 的值）。
        # 修复后：找 ≤ 或 ≥ lookup 里最接近的那个（Excel XLOOKUP 语义）。
        if match_mode in (1, -1):
            try:
                lnum = float(lk)
            except (ValueError, TypeError):
                return not_found

            best_idx = None
            best_diff = None
            for orig_i, v in items:
                try:
                    cnum = float(str(v).strip())
                except (ValueError, TypeError):
                    continue
                if match_mode == 1 and cnum >= lnum:
                    diff = cnum - lnum
                elif match_mode == -1 and cnum <= lnum:
                    diff = lnum - cnum
                else:
                    continue
                if best_diff is None or diff < best_diff:
                    best_diff = diff
                    best_idx = orig_i

            if best_idx is None:
                return not_found
            if rr1 == rr2:
                target_c = rc1 + best_idx
                if target_c <= rc2:
                    return m.get_value(rr1, target_c)
            else:
                target_r = rr1 + best_idx
                if target_r <= rr2:
                    return m.get_value(target_r, rc1)
            return not_found

        # ---------- match_mode=0/-2：直接返回第一个匹配 ----------
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

        return not_found'''

# _xmatch 里也有一处相同的匹配循环，需要同步修复
OLD_XMATCH_BODY = '''        if search_mode == -1:
            items = list(reversed(items))

        for orig_i, v in items:
            if cls._match_xlookup(v, lk, match_mode):
                return orig_i + 1  # 1 基

        return "#N/A"'''

NEW_XMATCH_BODY = '''        if search_mode == -1:
            items = list(reversed(items))

        # ---------- v5.1 B1fix：match_mode=1/-1 找"最接近的" ----------
        if match_mode in (1, -1):
            try:
                lnum = float(lk)
            except (ValueError, TypeError):
                return "#N/A"

            best_idx = None
            best_diff = None
            for orig_i, v in items:
                try:
                    cnum = float(str(v).strip())
                except (ValueError, TypeError):
                    continue
                if match_mode == 1 and cnum >= lnum:
                    diff = cnum - lnum
                elif match_mode == -1 and cnum <= lnum:
                    diff = lnum - cnum
                else:
                    continue
                if best_diff is None or diff < best_diff:
                    best_diff = diff
                    best_idx = orig_i

            return best_idx + 1 if best_idx is not None else "#N/A"

        for orig_i, v in items:
            if cls._match_xlookup(v, lk, match_mode):
                return orig_i + 1  # 1 基

        return "#N/A"'''


# ============================================================
# 改动 3：_switch 数值比较归一化
# ============================================================
OLD_SWITCH = '''        for i in range(0, len(pairs), 2):
            val = cls._eval_arg(pairs[i], m)
            if str(val) == str(expr):
                return cls._eval_arg(pairs[i + 1], m)

        return default'''

NEW_SWITCH = '''        for i in range(0, len(pairs), 2):
            val = cls._eval_arg(pairs[i], m)
            # v5.1 B1fix：数值归一化比较
            # 30 / 30.0 / "30" / "30.0" 都应视为相等（Excel 行为）
            if cls._switch_values_equal(expr, val):
                return cls._eval_arg(pairs[i + 1], m)

        return default

    @staticmethod
    def _switch_values_equal(a, b):
        """SWITCH 的比较：先尝试数值比较，失败后按字符串比较。"""
        if a is None and b is None:
            return True
        if a is None or b is None:
            return False
        # 布尔值不参与数值比较（避免 True == 1）
        if isinstance(a, bool) or isinstance(b, bool):
            return a is b
        try:
            return float(a) == float(b)
        except (ValueError, TypeError):
            return str(a) == str(b)'''


# ============================================================
# 应用逻辑
# ============================================================
def _apply_one(text, old, new, marker):
    if marker in text:
        return text, "skipped"
    if old not in text:
        return text, "not_found"
    return text.replace(old, new, 1), "applied"


def main():
    print("=" * 60)
    print(f"  v5.1 B1 三处失败修复  {'[DRY-RUN]' if DRY else ''}")
    print("=" * 60)
    print()

    if not TARGET.exists():
        print(f"❌ 找不到目标文件: {TARGET}")
        sys.exit(1)

    original = TARGET.read_text(encoding="utf-8")
    text = original

    patches = [
        ("1. _eval 函数识别支持空参数 (.+) → (.*)",
         OLD_EVAL_REGEX, NEW_EVAL_REGEX,
         "允许空参数（如 =SUM() / =XMATCH()）"),

        ("2. _xlookup match_mode=±1 找最接近的",
         OLD_XLOOKUP_BODY, NEW_XLOOKUP_BODY,
         "修复前：match_mode=±1 用\"第一个满足条件\""),

        ("3. _xmatch match_mode=±1 找最接近的",
         OLD_XMATCH_BODY, NEW_XMATCH_BODY,
         "修复前：match_mode=±1 用\"第一个满足条件\""),

        ("4. _switch 数值归一化比较",
         OLD_SWITCH, NEW_SWITCH,
         "def _switch_values_equal"),
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
        print("   可能原因：apply_b1.py 未执行 / 文件已被手动修改")
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