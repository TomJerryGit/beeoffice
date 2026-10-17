# finalize_session.py
"""
会话收尾：
  1. 归档一次性脚本到 tools/migration/
  2. 在 CHANGELOG.md 顶部插入 v5.0.6 段落
  3. 打印 git 状态（不自动提交）

用法:
    python finalize_session.py
"""
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.resolve()
ARCHIVE = ROOT / "tools" / "migration"

SCRIPTS_TO_ARCHIVE = [
    "optimize_tests.py",
    "fix_remaining.py",
    "fix_p0_08_ast.py",
]

CHANGELOG_SNIPPET = '''## [5.0.6] - 2026-09-17

### 修复

- **蜜算**：公式引擎 `_eval` 支持算术表达式
  - `=A1+A2` 现在返回数值而非字符串 `"A1+A2"`
  - `=IFERROR(1/A1, SUM(...))` 正确处理除零，走兜底
  - `=IFS(A1>10, ..., A1+100)` 分支支持算术
  - 复用 P0-5 加固的 `_safe_eval`，安全性不变
- **蜜演**：插件 `edit_notes` fallback 属性名修正
  - `getattr(view, "current_index")` → `_current_slide`
  - `view.speaker_notes.get(...)` → `_speaker_notes` 列表
  - v5.0.1 只修了 `play_show`，`edit_notes` 漏修
- **蜜写**：10 个 `beewrite_*.py` 文件头注释拼写修正
  - `bewrite_`（少一个 e）→ `beewrite_`
  - v5.0.1 只改了文件名，头注释未动

### 测试

- **目录分层**：`tests/` 重组为
  `unit/` + `qt/` + `regression/p0|p1|v5/` + `smoke/` + `helpers/`
- **测试数量**：483 → 513（+30）
- **覆盖率**：34.54% → 35.06%
- **关键模块覆盖率**：
  - `plugin_manager`: 56% → 80%
  - `cloud`: 14% → 76%
  - `tab_manager`: 38% → 44%
- **新增回归**：P0-8、P1-11
- **新增单元测试**：
  - `test_plugin_manager.py`（10 个用例）
  - `test_cloud_factory.py`（6 个用例）
- **断言改进**：
  - P0-8 测试从字符串匹配改为 AST 分析，避免误伤 docstring

---

'''


def archive_scripts():
    print("【1】归档一次性脚本")
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    for name in SCRIPTS_TO_ARCHIVE:
        src = ROOT / name
        if not src.exists():
            print(f"  ⏭️  {name}（不存在）")
            continue
        dst = ARCHIVE / name
        if dst.exists():
            print(f"  ⏭️  {name}（已归档）")
            continue
        shutil.move(str(src), str(dst))
        print(f"  ✅ {name} → tools/migration/")


def update_changelog():
    print()
    print("【2】更新 CHANGELOG.md")
    path = ROOT / "CHANGELOG.md"
    if not path.exists():
        print("  ❌ 找不到 CHANGELOG.md")
        return
    text = path.read_text(encoding="utf-8")
    if "## [5.0.6]" in text:
        print("  ⏭️  已含 5.0.6 段落")
        return
    # 在第一个 "## [" 之前插入
    marker = "## ["
    idx = text.find(marker)
    if idx < 0:
        print("  ⚠️  找不到版本标题，追加到文末")
        text += "\n" + CHANGELOG_SNIPPET
    else:
        text = text[:idx] + CHANGELOG_SNIPPET + text[idx:]
    path.write_text(text, encoding="utf-8")
    print("  ✅ 已在顶部插入 [5.0.6]")


def show_git_status():
    print()
    print("【3】git 状态")
    try:
        r = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode != 0:
            print("  ⚠️  不是 git 仓库，或 git 未安装")
            print("     建议：git init 后再 commit")
        else:
            out = r.stdout.strip()
            if out:
                print("  改动：")
                for line in out.split("\n")[:30]:
                    print(f"    {line}")
                if len(out.split("\n")) > 30:
                    print(f"    ...（还有更多）")
            else:
                print("  （无改动）")
    except FileNotFoundError:
        print("  ⚠️  未找到 git 命令")


def main():
    print("=" * 60)
    print("  会话收尾")
    print("=" * 60)
    print()
    archive_scripts()
    update_changelog()
    show_git_status()
    print()
    print("=" * 60)
    print("  ✅ 完成")
    print()
    print("  下一步（可选）：")
    print("    git add -A")
    print('    git commit -m "chore: 会话收尾 + CHANGELOG v5.0.6"')
    print("=" * 60)


if __name__ == "__main__":
    main()