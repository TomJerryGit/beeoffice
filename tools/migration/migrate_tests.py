# migrate_tests.py
"""
一次性把 tests/ 从旧结构迁移到新结构。

- 用 shutil.move 替代 git mv（无需 git）
- 用 glob 处理通配符（CMD 不支持）
- 幂等：重复运行不会出错
- 自动补 __init__.py
- 自动清理空目录

用法:
    python migrate_tests.py            # 实际执行
    python migrate_tests.py --dry-run  # 只打印，不改动
"""
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
TESTS = ROOT / "tests"
DRY = "--dry-run" in sys.argv


def log(action, src, dst=None):
    if dst is None:
        print(f"  [{action}] {src}")
    else:
        print(f"  [{action}] {src}  ->  {dst}")


def ensure_dir(path: Path):
    """创建目录（含父目录），幂等"""
    if path.exists():
        return False
    if not DRY:
        path.mkdir(parents=True, exist_ok=True)
    log("MKDIR", path.relative_to(ROOT))
    return True


def ensure_init(path: Path):
    """确保 __init__.py 存在"""
    init = path / "__init__.py"
    if init.exists():
        return
    if not DRY:
        init.write_text('"""\n测试包\n"""\n', encoding="utf-8")
    log("TOUCH", init.relative_to(ROOT))


def move(src: Path, dst_dir: Path):
    """移动文件到目标目录，幂等"""
    if not src.exists():
        log("SKIP (不存在)", src.relative_to(ROOT))
        return
    dst = dst_dir / src.name
    if dst.exists():
        log("SKIP (目标已存在)", src.relative_to(ROOT), dst.relative_to(ROOT))
        return
    if not DRY:
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    log("MOVE", src.relative_to(ROOT), dst.relative_to(ROOT))


def move_glob(pattern: str, dst_dir: Path):
    """按 glob 移动一批文件"""
    src_dir = TESTS / Path(pattern).parent
    for src in sorted(src_dir.glob(Path(pattern).name)):
        move(src, dst_dir)


def cleanup_empty(path: Path):
    """删除空目录"""
    if not path.exists():
        return
    remaining = [p for p in path.iterdir() if p.name != "__pycache__"]
    if remaining:
        log("SKIP (非空)", path.relative_to(ROOT))
        return
    if not DRY:
        shutil.rmtree(path, ignore_errors=True)
    log("RMDIR", path.relative_to(ROOT))


def main():
    if not TESTS.exists():
        print(f"❌ 找不到 tests/ 目录: {TESTS}")
        sys.exit(1)

    print("=" * 60)
    print(f"  BeeOffice 测试目录迁移  {'[DRY-RUN]' if DRY else ''}")
    print("=" * 60)
    print(f"  项目根目录: {ROOT}")
    print()

    # ---------- 1. 创建新目录 ----------
    print("【1】创建新目录")
    new_dirs = [
        TESTS / "unit",
        TESTS / "qt",
        TESTS / "regression",
        TESTS / "regression" / "p0",
        TESTS / "regression" / "p1",
        TESTS / "regression" / "v5",
        TESTS / "smoke",
        TESTS / "helpers",
    ]
    for d in new_dirs:
        ensure_dir(d)
    for d in new_dirs:
        ensure_init(d)
    print()

    # ---------- 2. 移动 unit 测试 ----------
    print("【2】移动 unit 测试")
    unit_files = [
        "test_ai_assist.py",
        "test_bee_export.py",
        "test_formula_engine.py",
        "test_nl_formula.py",
        "test_settings.py",
        "test_mobile_api.py",
    ]
    for name in unit_files:
        move(TESTS / name, TESTS / "unit")
    print()

    # ---------- 3. 移动 qt 测试 ----------
    print("【3】移动 qt 测试")
    qt_files = [
        "test_app.py",
        "test_command_palette.py",
        "test_tab_manager.py",
        "test_beewrite_basic.py",
        "test_beeshow_play.py",
        "test_md_conversion.py",
        "test_export_pdf.py",
    ]
    for name in qt_files:
        move(TESTS / name, TESTS / "qt")
    print()

    # ---------- 4. 移动 smoke ----------
    print("【4】移动 smoke 测试")
    move(TESTS / "test_smoke_imports.py", TESTS / "smoke")
    print()

    # ---------- 5. 移动回归测试（按通配符） ----------
    print("【5】移动 P0 回归")
    move_glob("test_p0_regression/test_p0_*.py", TESTS / "regression" / "p0")
    print()

    print("【6】移动 P1 回归")
    move_glob("test_p2_regression/test_p1_*.py", TESTS / "regression" / "p1")
    print()

    print("【7】移动 v5 回归")
    move_glob("test_p2_regression/test_v5*.py", TESTS / "regression" / "v5")
    print()

    # ---------- 8. 清理旧目录 ----------
    print("【8】清理旧目录")
    cleanup_empty(TESTS / "test_p0_regression")
    cleanup_empty(TESTS / "test_p2_regression")
    print()

    # ---------- 9. 汇报 ----------
    print("=" * 60)
    if DRY:
        print("  DRY-RUN 完成，未做任何改动")
        print("  去掉 --dry-run 参数可实际执行")
    else:
        print("  ✅ 迁移完成")
        print()
        print("  下一步：")
        print("    1. 手动创建 tests/helpers/fake_models.py 等（见文档）")
        print("    2. 更新 pytest.ini 里的 norecursedirs 增加 tests/helpers")
        print("    3. 运行: pytest tests/ --collect-only -q")
        print("    4. 运行: run_tests.bat")
    print("=" * 60)


if __name__ == "__main__":
    main()