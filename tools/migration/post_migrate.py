# post_migrate.py
"""
迁移收尾：
  1. 清理 test_p0_regression / test_p2_regression 残留
  2. 创建 tests/helpers/ 下的 3 个辅助模块
  3. 检查 pytest.ini 是否需要加 tests/helpers

用法:
    python post_migrate.py            # 执行
    python post_migrate.py --dry-run  # 只看会做什么
"""
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
TESTS = ROOT / "tests"
DRY = "--dry-run" in sys.argv


def log(action, path):
    print(f"  [{action}] {path}")


def remove_dir(path: Path):
    """删除目录（含 __pycache__ / __init__.py 等）"""
    if not path.exists():
        log("SKIP (不存在)", path.relative_to(ROOT))
        return
    if not DRY:
        shutil.rmtree(path, ignore_errors=True)
    log("RMDIR", path.relative_to(ROOT))


def write_file(path: Path, content: str):
    """写文件，幂等：已存在则不覆盖"""
    if path.exists():
        log("SKIP (已存在)", path.relative_to(ROOT))
        return
    if not DRY:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    log("CREATE", path.relative_to(ROOT))


def main():
    print("=" * 60)
    print(f"  BeeOffice 迁移收尾  {'[DRY-RUN]' if DRY else ''}")
    print("=" * 60)
    print()

    # ---------- 1. 清理旧目录 ----------
    print("【1】清理旧目录残留")
    remove_dir(TESTS / "test_p0_regression")
    remove_dir(TESTS / "test_p2_regression")
    print()

    # ---------- 2. 创建 helpers 文件 ----------
    print("【2】创建 tests/helpers/ 辅助模块")

    write_file(
        TESTS / "helpers" / "__init__.py",
        '"""\n测试辅助模块（非测试文件）。\n"""\n',
    )

    write_file(
        TESTS / "helpers" / "fake_models.py",
        '''# tests/helpers/fake_models.py
"""模拟 Qt Model / DataFrame 的小工具，供多个测试共享。"""


class FakeModel:
    """模拟 SheetDataModel：只实现 get_value(r, c)。"""

    def __init__(self, data):
        self._data = data

    def get_value(self, r, c):
        if 0 <= r < len(self._data) and 0 <= c < len(self._data[r]):
            return self._data[r][c]
        return None


class FakeMultiSheetModel(FakeModel):
    """模拟多 sheet 场景。"""

    def __init__(self, sheets: dict):
        super().__init__([[None]])
        self._sheets = sheets

    def get_sheet_data(self, name):
        return self._sheets.get(name)
''',
    )

    write_file(
        TESTS / "helpers" / "fake_widgets.py",
        '''# tests/helpers/fake_widgets.py
"""轻量 fake 控件，模拟 BeeApp 的部分接口。"""


class FakeTabManager:
    def __init__(self, widget=None):
        self._widget = widget

    def currentWidget(self):
        return self._widget

    def count(self):
        return 1 if self._widget else 0

    def widget(self, i):
        return self._widget if i == 0 else None

    def tabText(self, i):
        return "fake-tab"


class FakeParent:
    """模拟 BeeApp：提供 tab_manager 与 set_global_status。"""

    def __init__(self, widget=None):
        self.tab_manager = FakeTabManager(widget)
        self._status_calls = []

    def set_global_status(self, msg, timeout=0):
        self._status_calls.append((msg, timeout))
''',
    )

    write_file(
        TESTS / "helpers" / "qt_helpers.py",
        '''# tests/helpers/qt_helpers.py
"""Qt 相关的小工具：测试图片生成、事件循环 drain。"""
import time
from pathlib import Path


def make_test_image(path, w=200, h=100, color="red"):
    """生成一张测试图片，返回 Path。"""
    from PySide6.QtGui import QImage, QColor
    path = Path(path)
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(QColor(color))
    assert img.save(str(path)), f"图片写入失败: {path}"
    return path


def drain_event_loop(rounds=5, delay=0.05):
    """跑几轮事件循环 + DeferredDelete，让 pending deleteLater 执行。"""
    from PySide6.QtCore import QEvent, QCoreApplication
    for _ in range(rounds):
        QCoreApplication.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        time.sleep(delay)
        QCoreApplication.processEvents()
''',
    )
    print()

    # ---------- 3. 检查 pytest.ini ----------
    print("【3】检查 pytest.ini")
    pytest_ini = ROOT / "pytest.ini"
    if not pytest_ini.exists():
        log("SKIP (不存在)", pytest_ini.relative_to(ROOT))
    else:
        content = pytest_ini.read_text(encoding="utf-8")
        if "tests/helpers" in content:
            log("SKIP (已含 tests/helpers)", pytest_ini.relative_to(ROOT))
        else:
            print(f"  [MANUAL] {pytest_ini.relative_to(ROOT)}")
            print("           需要手动在 norecursedirs 末尾加一行:")
            print("               tests/helpers")
    print()

    # ---------- 汇报 ----------
    print("=" * 60)
    if DRY:
        print("  DRY-RUN 完成，未做任何改动")
    else:
        print("  ✅ 收尾完成")
        print()
        print("  下一步：")
        print("    1. 手动编辑 pytest.ini（若第 3 步提示 MANUAL）")
        print("    2. 运行: pytest tests/ --collect-only -q")
        print("    3. 运行: run_tests.bat")
    print("=" * 60)


if __name__ == "__main__":
    main()