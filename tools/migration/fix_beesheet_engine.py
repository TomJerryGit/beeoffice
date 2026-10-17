# fix_beesheet_engine.py
"""
修复 beesheet_engine.py 的 3 个算术表达式 bug。

- 自动备份原文件为 .py.bak
- 幂等：已修复则跳过
- 不做其他任何改动

用法:
    python fix_beesheet_engine.py
"""
from pathlib import Path
import shutil
import sys

TARGET = Path(__file__).parent / "beeoffice" / "plugins" / "beesheet_engine.py"


# ---------- 补丁 1：_eval 支持算术表达式 ----------
OLD_EVAL_TAIL = '''        try:
            return float(expr_stripped) if '.' in expr_stripped else int(expr_stripped)
        except:
            return expr_stripped'''

NEW_EVAL_TAIL = '''        try:
            return float(expr_stripped) if '.' in expr_stripped else int(expr_stripped)
        except (ValueError, TypeError):
            pass

        # v5.0.5：算术表达式（A1+A2、A1*2、1/A1 等）
        try:
            return cls._safe_eval(expr_stripped, model)
        except ZeroDivisionError:
            raise
        except Exception:
            pass

        return expr_stripped'''


# ---------- 补丁 2：_iferror 捕获求值异常 ----------
OLD_IFERROR = '''        v = cls._eval(p[0].strip(), m)
        # v5.0.5：兜底值改用 _eval_arg，支持嵌套函数
        if isinstance(v, str) and v.startswith('#'):
            return cls._eval_arg(p[1], m)
        return v'''

NEW_IFERROR = '''        try:
            v = cls._eval(p[0].strip(), m)
        except Exception:
            # 求值抛异常（如除零）→ 走兜底值
            return cls._eval_arg(p[1], m)
        # v5.0.5：兜底值改用 _eval_arg，支持嵌套函数
        if isinstance(v, str) and v.startswith('#'):
            return cls._eval_arg(p[1], m)
        return v'''


# ---------- 补丁 3：_ifna 捕获求值异常 ----------
OLD_IFNA = '''        v = cls._eval(p[0].strip(), m)
        # v5.0.5：兜底值改用 _eval_arg，支持嵌套函数
        if str(v) == '#N/A':
            return cls._eval_arg(p[1], m)
        return v'''

NEW_IFNA = '''        try:
            v = cls._eval(p[0].strip(), m)
        except Exception:
            return cls._eval_arg(p[1], m)
        # v5.0.5：兜底值改用 _eval_arg，支持嵌套函数
        if str(v) == '#N/A':
            return cls._eval_arg(p[1], m)
        return v'''


PATCHES = [
    ("_eval 算术表达式", OLD_EVAL_TAIL, NEW_EVAL_TAIL),
    ("_iferror 异常兜底", OLD_IFERROR, NEW_IFERROR),
    ("_ifna 异常兜底", OLD_IFNA, NEW_IFNA),
]


def main():
    if not TARGET.exists():
        print(f"❌ 找不到: {TARGET}")
        sys.exit(1)

    text = TARGET.read_text(encoding="utf-8")

    # 幂等检查
    if "v5.0.5：算术表达式" in text:
        print("✅ 已修复过，无需重复执行")
        sys.exit(0)

    # 备份
    backup = TARGET.with_suffix(".py.bak")
    if not backup.exists():
        shutil.copy2(TARGET, backup)
        print(f"📦 已备份: {backup.name}")
    else:
        print(f"📦 备份已存在，跳过: {backup.name}")

    # 应用补丁
    changed = 0
    for name, old, new in PATCHES:
        if old not in text:
            print(f"⚠️  找不到片段: {name}")
            continue
        text = text.replace(old, new, 1)
        print(f"✅ 已应用: {name}")
        changed += 1

    if changed == 0:
        print("❌ 无任何改动，请检查文件是否已被手动修改")
        sys.exit(1)

    TARGET.write_text(text, encoding="utf-8")
    print()
    print(f"✅ 共应用 {changed}/{len(PATCHES)} 个补丁")
    print(f"   文件: {TARGET}")
    print(f"   备份: {backup.name}")
    print()
    print("下一步:")
    print("   pytest tests/regression/p0/test_p0_05_safe_eval_boundary.py -v")


if __name__ == "__main__":
    main()