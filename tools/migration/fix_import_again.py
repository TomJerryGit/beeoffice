# fix_import_again.py
"""
修复上次 fix_3_failures.py 的导入逻辑 bug。

上次脚本用 `"from PySide6.QtGui import QTextCursor" not in text`
判断是否需要加全局导入，但原文件里 test_polish_with_selection
方法内部有局部导入，字符串匹配命中了 → 跳过加全局导入。

本脚本改为只检查"文件顶部区域（所有 def/class 之前）"是否存在
全局导入，避免被局部导入干扰。

用法:
    python fix_import_again.py
    python fix_import_again.py --dry-run
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
DRY = "--dry-run" in sys.argv

TARGET = ROOT / "tests" / "qt" / "test_beewrite_ai_mixin.py"

IMPORT_LINE = "from PySide6.QtGui import QTextCursor"


def has_top_level_import(text: str) -> bool:
    """
    检查文件顶部（第一个 def/class 之前）是否存在全局导入。
    """
    lines = text.split("\n")
    for line in lines:
        stripped = line.strip()
        # 遇到第一个 def 或 class，停止搜索
        if stripped.startswith("def ") or stripped.startswith("class "):
            return False
        # 检查是否是需要的那行
        if stripped == IMPORT_LINE:
            return True
    return False


def find_insert_position(lines):
    """
    找到文件顶部最后一个 import 语句的下一行索引。
    返回 None 表示没找到。
    """
    last_import_idx = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        # 遇到第一个 def/class，停止
        if stripped.startswith("def ") or stripped.startswith("class "):
            break
        if stripped.startswith("import ") or stripped.startswith("from "):
            last_import_idx = i
    return last_import_idx + 1 if last_import_idx >= 0 else None


def main():
    print("=" * 60)
    print(f"  修复 QTextCursor 导入  {'[DRY-RUN]' if DRY else ''}")
    print("=" * 60)
    print()

    if not TARGET.exists():
        print(f"❌ 找不到: {TARGET}")
        sys.exit(1)

    text = TARGET.read_text(encoding="utf-8")

    # 1. 检查是否已经有全局导入
    if has_top_level_import(text):
        print("⏭️  顶部已有全局导入，无需修改")
        print()
        print("直接运行验证：")
        print("  pytest tests/qt/test_beewrite_ai_mixin.py -v")
        return

    # 2. 检查是否真的需要导入（文件里是否有 QTextCursor.End 等用法）
    if "QTextCursor" not in text:
        print("⏭️  文件里没有用到 QTextCursor，无需导入")
        return

    # 3. 找到插入位置
    lines = text.split("\n")
    insert_idx = find_insert_position(lines)
    if insert_idx is None:
        print("❌ 未找到合适的插入位置（文件里没有 import 语句？）")
        sys.exit(1)

    # 4. 插入
    lines.insert(insert_idx, IMPORT_LINE)
    new_text = "\n".join(lines)

    if DRY:
        print(f"将在第 {insert_idx + 1} 行插入：")
        print(f"  {IMPORT_LINE}")
    else:
        TARGET.write_text(new_text, encoding="utf-8")
        print(f"✅ 已在第 {insert_idx + 1} 行插入：")
        print(f"  {IMPORT_LINE}")
        print()
        print(f"文件: {TARGET.relative_to(ROOT)}")

    print()
    print("=" * 60)
    if DRY:
        print("  DRY-RUN 完成，未做任何改动")
        print("  去掉 --dry-run 可执行")
    else:
        print("  下一步：")
        print("    pytest tests/qt/test_beewrite_ai_mixin.py -v")
        print("    run_tests.bat")
    print("=" * 60)


if __name__ == "__main__":
    main()