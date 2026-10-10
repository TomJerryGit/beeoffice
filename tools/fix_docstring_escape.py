# fix_docstring_escape.py
"""
一次性批量修复 docstring 里的非法转义序列。

背景：
  Python 3.12+ 对 docstring 里的非法转义序列（如 \\w、\\d、\\[）
  会抛 DeprecationWarning，甚至未来版本会变成 SyntaxWarning。
  本脚本扫描 beeoffice/ 下所有 .py，把含非法转义的 docstring
  前缀改为 r（raw string），从而消除警告。

实现：
  - 用 tokenize 精确识别所有 STRING token
  - 只处理三引号字符串
  - 只处理尚未是 raw string 的
  - 内容里含非法转义序列才改

用法：
  python fix_docstring_escape.py

  （默认扫描 beeoffice/ 目录；如需指定，修改 ROOT 常量）
"""
import io
import re
import tokenize
from pathlib import Path


# 默认扫描的目录
ROOT = Path(__file__).parent / "beeoffice"

# 非法反斜杠转义序列：反斜杠后不是已知转义字符
# 已知转义字符：\\ \' \" \a \b \f \n \r \t \v \0-\7 \x \u \U \N
# 另外排除反斜杠+换行（续行符）
BAD_ESCAPE = re.compile(r"\\[^\\'\"abfnrtv0-7xuUN\n]")


def fix_file(py: Path) -> bool:
    """
    修复单个 Python 文件里的 docstring 转义。

    :return: 是否修改了文件
    """
    try:
        src = py.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False

    # 用 tokenize 扫描所有 STRING token，记录需要插入 'r' 的位置
    insertions = []   # [(row, col), ...]，row 从 1 开始，col 从 0 开始
    try:
        tokens = list(
            tokenize.generate_tokens(io.StringIO(src).readline)
        )
    except (tokenize.TokenError, SyntaxError):
        return False

    for tok in tokens:
        if tok.type != tokenize.STRING:
            continue
        text = tok.string
        # 只处理三引号字符串
        m = re.match(r'^([rRbBuUfF]*)("""|\'\'\')', text)
        if not m:
            continue
        prefix = m.group(1)
        quote = m.group(2)
        # 已经是 raw string，跳过
        if 'r' in prefix.lower():
            continue
        # 提取字符串 body（去掉前缀和首尾引号）
        body = text[len(prefix) + len(quote): -len(quote)]
        if BAD_ESCAPE.search(body):
            row, col = tok.start
            insertions.append((row, col))

    if not insertions:
        return False

    # 按行拆分，从后往前插入 'r'（避免偏移）
    lines = src.split('\n')
    # 元组排序：先比 row 大的（后面的行），同行比 col 大的
    for row, col in sorted(insertions, reverse=True):
        line = lines[row - 1]
        lines[row - 1] = line[:col] + 'r' + line[col:]

    new_src = '\n'.join(lines)
    py.write_text(new_src, encoding="utf-8")
    return True


def main():
    print("=" * 60)
    print("  BeeOffice docstring 转义修复工具")
    print("=" * 60)
    print()

    if not ROOT.exists():
        print(f"❌ 目录不存在: {ROOT}")
        print(f"   请确认脚本放在项目根目录，且 beeoffice/ 目录存在")
        return

    print(f"📁 扫描目录: {ROOT}")
    print()

    total = 0
    fixed = 0
    failed = 0

    for py in sorted(ROOT.rglob("*.py")):
        total += 1
        try:
            if fix_file(py):
                rel = py.relative_to(ROOT.parent)
                print(f"  ✅ 已修复: {rel}")
                fixed += 1
        except Exception as e:
            rel = py.relative_to(ROOT.parent)
            print(f"  ❌ 处理失败: {rel} — {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"  扫描 {total} 个文件，修复 {fixed} 个，失败 {failed} 个")
    print("=" * 60)
    print()
    if fixed:
        print("建议：")
        print("  1. 用 git diff 检查修改是否符合预期")
        print("  2. 运行 pytest 确认警告已消失")
        print("  3. 若某个 docstring 原本依赖 \\n 等转义，请手工改回")
    else:
        print("未发现需要修复的文件。")


if __name__ == "__main__":
    main()