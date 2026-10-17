# fix_3_failures.py
"""
修复 v5.0.6 测试运行中暴露的 3 个失败 + 补 templates.py 覆盖率测试。

修复：
  1. tests/qt/test_beewrite_ai_mixin.py
     cursor.End → QTextCursor.End
     （PySide6 6.6 里 End 是 QTextCursor 的枚举成员，
       实例上访问 cursor.End 会 AttributeError）

  2. beeoffice/plugins/memory_monitor.py
     _reset() 不再调 _update()
     （原实现 _reset 立刻调 _update，会把 _peak 重新设为当前内存，
       导致用户点"重置统计"后看到非零数字）

  3. beeoffice/plugins/empty_state.py
     lambda checked → lambda checked=False
     （QPushButton.clicked 信号会传 bool，lambda 没有默认参数会
       TypeError: missing 1 required positional argument: 'checked'）

新增：
  4. tests/unit/test_templates_picker_extra.py
     不弹模态对话框，覆盖 templates.py 的 UI 构建 + 业务逻辑
     （原 test_templates_picker.py 只验证了函数可调用，
       templates.py 覆盖率停在 5%）

用法：
    python fix_3_failures.py            # 执行
    python fix_3_failures.py --dry-run  # 只打印，不改动
    python fix_3_failures.py --force    # 强制覆盖已存在的新测试文件
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
DRY = "--dry-run" in sys.argv
FORCE = "--force" in sys.argv


# ============================================================
# 1. 修 test_beewrite_ai_mixin.py 的 cursor.End
# ============================================================
def fix_test_cursor():
    print("【1】tests/qt/test_beewrite_ai_mixin.py — cursor.End")
    target = ROOT / "tests" / "qt" / "test_beewrite_ai_mixin.py"
    if not target.exists():
        print(f"  ⏭️  不存在: {target.relative_to(ROOT)}")
        return False

    text = target.read_text(encoding="utf-8")

    # 幂等检查
    if "QTextCursor.End" in text and "cursor.End" not in text:
        print("  ⏭️  已修复，跳过")
        return True

    old = "        cursor.movePosition(cursor.End)\n"
    new = "        cursor.movePosition(QTextCursor.End)\n"
    if old not in text:
        print("  ⚠️  未找到目标行：cursor.movePosition(cursor.End)")
        return False

    text = text.replace(old, new, 1)

    # 确保顶部导入 QTextCursor
    if "from PySide6.QtGui import QTextCursor" not in text:
        # 优先在已有的 PySide6.QtGui import 后追加
        lines = text.split("\n")
        inserted = False
        for i, line in enumerate(lines):
            if line.startswith("from PySide6.QtGui import"):
                lines.insert(i + 1, "from PySide6.QtGui import QTextCursor")
                inserted = True
                break
        if not inserted:
            # 兜底：在最后一个 import 后插入
            for i in range(len(lines) - 1, -1, -1):
                if lines[i].startswith("import ") or lines[i].startswith("from "):
                    lines.insert(i + 1, "from PySide6.QtGui import QTextCursor")
                    inserted = True
                    break
        text = "\n".join(lines)

    if not DRY:
        target.write_text(text, encoding="utf-8")
    print(f"  ✅ {target.relative_to(ROOT)}")
    return True


# ============================================================
# 2. 修 memory_monitor._reset
# ============================================================
def fix_memory_monitor():
    print()
    print("【2】beeoffice/plugins/memory_monitor.py — _reset 语义")
    target = ROOT / "beeoffice" / "plugins" / "memory_monitor.py"
    if not target.exists():
        print(f"  ⏭️  不存在: {target.relative_to(ROOT)}")
        return False

    text = target.read_text(encoding="utf-8")

    old = '''    def _reset(self):
        self._peak = 0
        self._history = []
        self._update()'''

    new = '''    def _reset(self):
        self._peak = 0
        self._history = []
        # 不调 _update()，避免立刻把 _peak 更新为当前内存。
        # 只清空显示，等下一次定时器触发再刷新。
        self.current_label.setText("当前: -- MB")
        self.peak_label.setText("峰值: 0.0 MB")
        self.trend_label.setText("趋势: 监测中...")
        self.progress.setValue(0)'''

    # 幂等检查：已经改成不含 _update() 的版本
    if old not in text:
        if "只清空显示，等下一次定时器触发再刷新" in text:
            print("  ⏭️  已修复，跳过")
            return True
        print("  ⚠️  未找到目标 _reset 实现（可能已被手动修改）")
        return False

    text = text.replace(old, new, 1)
    if not DRY:
        target.write_text(text, encoding="utf-8")
    print(f"  ✅ {target.relative_to(ROOT)}")
    return True


# ============================================================
# 3. 修 empty_state lambda 参数
# ============================================================
def fix_empty_state():
    print()
    print("【3】beeoffice/plugins/empty_state.py — lambda 默认参数")
    target = ROOT / "beeoffice" / "plugins" / "empty_state.py"
    if not target.exists():
        print(f"  ⏭️  不存在: {target.relative_to(ROOT)}")
        return False

    text = target.read_text(encoding="utf-8")

    old = "lambda checked, a=action_name: self.action_triggered.emit(a)"
    new = "lambda checked=False, a=action_name: self.action_triggered.emit(a)"

    # 幂等检查
    if old not in text and new in text:
        print("  ⏭️  已修复，跳过")
        return True
    if old not in text:
        print("  ⚠️  未找到目标 lambda")
        return False

    text = text.replace(old, new, 1)
    if not DRY:
        target.write_text(text, encoding="utf-8")
    print(f"  ✅ {target.relative_to(ROOT)}")
    return True


# ============================================================
# 4. 新增 templates.py 覆盖率测试
# ============================================================
NEW_TEST_CONTENT = '''# tests/unit/test_templates_picker_extra.py
"""
templates.py 补充测试：不弹模态对话框。

覆盖：
  - _create_from_template    : 从模板创建文档的完整流程 + 异常分支
  - save_as_template_dialog  : 空内容 / 取消 / 成功 / 失败 / 异常
  - show_template_picker     : UI 构建 + 加载失败 / 空列表

策略：
  - monkeypatch QDialog.exec            → 立即返回，避免模态阻塞
  - monkeypatch QInputDialog.getText    → 提供预设返回值
  - monkeypatch QMessageBox.information/warning
  - monkeypatch TemplateManager         → 跳过真实的 ~/.beeoffice_templates 读写
  - 用 _FakeApp（继承 QWidget）作为 parent，
    同时提供 tab_manager 与 set_global_status

原 test_templates_picker.py 只验证了函数可调用，
本文件补齐真实 UI 构建与业务逻辑路径。
"""
from datetime import datetime

import pytest
from PySide6.QtWidgets import (
    QWidget, QDialog, QInputDialog, QMessageBox,
)


# ==================== Fake ====================
class _FakeTabManager:
    def __init__(self):
        self._tabs = []
        self._current = None

    def addTab(self, widget, title):
        self._tabs.append((widget, title))

    def setCurrentWidget(self, widget):
        self._current = widget

    def count(self):
        return len(self._tabs)

    def widget(self, i):
        return self._tabs[i][0] if 0 <= i < len(self._tabs) else None

    def tabText(self, i):
        return self._tabs[i][1] if 0 <= i < len(self._tabs) else ""

    def indexOf(self, widget):
        for i, (w, _) in enumerate(self._tabs):
            if w is widget:
                return i
        return -1


class _FakeApp(QWidget):
    """既像 QWidget（QDialog 需要），又像 BeeApp。"""

    def __init__(self):
        super().__init__()
        self.tab_manager = _FakeTabManager()
        self._status_calls = []

    def set_global_status(self, msg, timeout=0):
        self._status_calls.append((msg, timeout))


class _FakeEditor:
    """模拟 BeeWriteEditor：只实现测试用到的方法。"""

    def __init__(self):
        self._content = ""

    def set_content(self, text):
        self._content = text


# ==================== fixture ====================
@pytest.fixture
def parent(qtbot):
    p = _FakeApp()
    qtbot.addWidget(p)
    return p


@pytest.fixture
def patch_editor(monkeypatch):
    """把 BeeWriteEditor 替换为 _FakeEditor。"""
    from beeoffice.plugins import beewrite as beewrite_mod
    monkeypatch.setattr(beewrite_mod, "BeeWriteEditor", _FakeEditor)


@pytest.fixture
def patch_tm_success(monkeypatch):
    """让 TemplateManager 初始化 + save_user_template 都不真的碰文件。"""
    from beeoffice.resources.template_manager import TemplateManager
    monkeypatch.setattr(TemplateManager, "__init__", lambda self: None)
    monkeypatch.setattr(
        TemplateManager, "save_user_template",
        lambda self, name, content, category: True,
    )


# ==================== _create_from_template ====================
class TestCreateFromTemplate:
    def test_creates_editor_and_adds_tab(self, parent, patch_editor):
        from beeoffice.templates import _create_from_template
        tpl = {"name": "测试模板", "content": "# 标题\\n\\n正文"}
        _create_from_template(parent, tpl)

        assert parent.tab_manager.count() == 1
        editor = parent.tab_manager.widget(0)
        assert isinstance(editor, _FakeEditor)
        assert "# 标题" in editor._content
        assert "正文" in editor._content

    def test_replaces_date_placeholder(self, parent, patch_editor):
        from beeoffice.templates import _create_from_template
        tpl = {"name": "日报", "content": "日期：{date}"}
        _create_from_template(parent, tpl)

        editor = parent.tab_manager.widget(0)
        today = datetime.now().strftime("%Y年%m月%d日")
        assert today in editor._content
        assert "{date}" not in editor._content

    def test_calls_set_global_status(self, parent, patch_editor):
        from beeoffice.templates import _create_from_template
        _create_from_template(parent, {"name": "x", "content": "y"})
        assert parent._status_calls, "应调用 set_global_status"

    def test_add_tab_exception_shows_warning(
        self, parent, patch_editor, monkeypatch
    ):
        warned = []
        monkeypatch.setattr(
            QMessageBox, "warning",
            staticmethod(lambda *a, **k: warned.append(a)),
        )

        class _BrokenTabManager:
            def addTab(self, *a, **k):
                raise RuntimeError("tab 添加失败")

        parent.tab_manager = _BrokenTabManager()

        from beeoffice.templates import _create_from_template
        _create_from_template(parent, {"name": "x", "content": "y"})
        assert warned, "addTab 失败应弹警告"

    def test_empty_content_still_creates_doc(self, parent, patch_editor):
        from beeoffice.templates import _create_from_template
        _create_from_template(parent, {"name": "空", "content": ""})
        assert parent.tab_manager.count() == 1


# ==================== save_as_template_dialog ====================
class TestSaveAsTemplateDialog:
    def test_empty_content_shows_info(self, parent, monkeypatch):
        infos = []
        monkeypatch.setattr(
            QMessageBox, "information",
            staticmethod(lambda *a, **k: infos.append(a)),
        )
        from beeoffice.templates import save_as_template_dialog
        save_as_template_dialog(parent, "")
        assert infos

    def test_whitespace_content_shows_info(self, parent, monkeypatch):
        infos = []
        monkeypatch.setattr(
            QMessageBox, "information",
            staticmethod(lambda *a, **k: infos.append(a)),
        )
        from beeoffice.templates import save_as_template_dialog
        save_as_template_dialog(parent, "   \\n\\t  ")
        assert infos

    def test_user_cancels_name(self, parent, monkeypatch):
        monkeypatch.setattr(
            QInputDialog, "getText",
            staticmethod(lambda *a, **k: ("", False)),
        )
        from beeoffice.templates import save_as_template_dialog
        save_as_template_dialog(parent, "内容")

    def test_user_cancels_category(
        self, parent, monkeypatch, patch_tm_success
    ):
        responses = iter([("模板名", True), ("", False)])
        monkeypatch.setattr(
            QInputDialog, "getText",
            staticmethod(lambda *a, **k: next(responses)),
        )
        from beeoffice.templates import save_as_template_dialog
        save_as_template_dialog(parent, "内容")

    def test_save_success(self, parent, monkeypatch, patch_tm_success):
        responses = iter([("模板A", True), ("工作", True)])
        monkeypatch.setattr(
            QInputDialog, "getText",
            staticmethod(lambda *a, **k: next(responses)),
        )
        infos = []
        monkeypatch.setattr(
            QMessageBox, "information",
            staticmethod(lambda *a, **k: infos.append(a)),
        )

        from beeoffice.templates import save_as_template_dialog
        save_as_template_dialog(parent, "内容")

        assert infos, "保存成功应弹信息框"
        assert "模板A" in str(infos[0])

    def test_save_failure(self, parent, monkeypatch):
        from beeoffice.resources.template_manager import TemplateManager
        monkeypatch.setattr(TemplateManager, "__init__", lambda self: None)
        monkeypatch.setattr(
            TemplateManager, "save_user_template",
            lambda self, n, c, cat: False,
        )
        responses = iter([("模板B", True), ("工作", True)])
        monkeypatch.setattr(
            QInputDialog, "getText",
            staticmethod(lambda *a, **k: next(responses)),
        )
        warned = []
        monkeypatch.setattr(
            QMessageBox, "warning",
            staticmethod(lambda *a, **k: warned.append(a)),
        )

        from beeoffice.templates import save_as_template_dialog
        save_as_template_dialog(parent, "内容")
        assert warned

    def test_empty_category_falls_back_to_other(
        self, parent, monkeypatch
    ):
        captured = {}
        from beeoffice.resources.template_manager import TemplateManager

        def fake_save(self, name, content, category):
            captured["name"] = name
            captured["category"] = category
            return True

        monkeypatch.setattr(TemplateManager, "__init__", lambda self: None)
        monkeypatch.setattr(
            TemplateManager, "save_user_template", fake_save
        )
        responses = iter([("模板C", True), ("   ", True)])
        monkeypatch.setattr(
            QInputDialog, "getText",
            staticmethod(lambda *a, **k: next(responses)),
        )
        monkeypatch.setattr(
            QMessageBox, "information",
            staticmethod(lambda *a, **k: None),
        )

        from beeoffice.templates import save_as_template_dialog
        save_as_template_dialog(parent, "内容")
        assert captured["category"] == "其他"

    def test_save_exception(self, parent, monkeypatch):
        from beeoffice.resources.template_manager import TemplateManager

        def boom(self, name, content, category):
            raise RuntimeError("测试异常")

        monkeypatch.setattr(TemplateManager, "__init__", lambda self: None)
        monkeypatch.setattr(TemplateManager, "save_user_template", boom)
        responses = iter([("模板D", True), ("分类D", True)])
        monkeypatch.setattr(
            QInputDialog, "getText",
            staticmethod(lambda *a, **k: next(responses)),
        )
        warned = []
        monkeypatch.setattr(
            QMessageBox, "warning",
            staticmethod(lambda *a, **k: warned.append(a)),
        )

        from beeoffice.templates import save_as_template_dialog
        save_as_template_dialog(parent, "内容")
        assert warned


# ==================== show_template_picker ====================
class TestShowTemplatePicker:
    def test_constructs_ui_without_crash(self, parent, monkeypatch):
        monkeypatch.setattr(QDialog, "exec", lambda self: 0)
        from beeoffice.templates import show_template_picker
        show_template_picker(parent)

    def test_handles_template_load_error(self, parent, monkeypatch):
        from beeoffice.resources.template_manager import TemplateManager

        def boom(self):
            raise RuntimeError("加载模板失败")

        monkeypatch.setattr(TemplateManager, "__init__", lambda self: None)
        monkeypatch.setattr(TemplateManager, "get_all_templates", boom)

        warned = []
        monkeypatch.setattr(
            QMessageBox, "warning",
            staticmethod(lambda *a, **k: warned.append(a)),
        )
        monkeypatch.setattr(QDialog, "exec", lambda self: 0)

        from beeoffice.templates import show_template_picker
        show_template_picker(parent)
        assert warned, "加载模板失败应弹警告"

    def test_handles_empty_templates(self, parent, monkeypatch):
        from beeoffice.resources.template_manager import TemplateManager
        monkeypatch.setattr(TemplateManager, "__init__", lambda self: None)
        monkeypatch.setattr(
            TemplateManager, "get_all_templates", lambda self: [],
        )
        monkeypatch.setattr(QDialog, "exec", lambda self: 0)

        from beeoffice.templates import show_template_picker
        show_template_picker(parent)
'''


def add_templates_test():
    print()
    print("【4】新增 tests/unit/test_templates_picker_extra.py")
    target = ROOT / "tests" / "unit" / "test_templates_picker_extra.py"

    if target.exists() and not FORCE:
        print(f"  ⏭️  已存在，跳过: {target.relative_to(ROOT)}")
        print("     （如需覆盖，请加 --force）")
        return False

    if not DRY:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(NEW_TEST_CONTENT, encoding="utf-8")
    print(f"  ✅ {target.relative_to(ROOT)}")
    return True


# ============================================================
# main
# ============================================================
def main():
    print("=" * 60)
    print(f"  修复 3 个失败 + 补 templates.py 覆盖率  "
          f"{'[DRY-RUN]' if DRY else ''}")
    print("=" * 60)
    print()

    results = [
        fix_test_cursor(),
        fix_memory_monitor(),
        fix_empty_state(),
        add_templates_test(),
    ]

    print()
    print("=" * 60)
    if DRY:
        print("  DRY-RUN 完成，未做任何改动")
        print("  去掉 --dry-run 参数可实际执行")
    else:
        ok = sum(1 for r in results if r)
        print(f"  ✅ 完成 {ok}/{len(results)} 项")
        print()
        print("  下一步：")
        print("    pytest tests/qt/test_beewrite_ai_mixin.py -v")
        print("    pytest tests/qt/test_memory_monitor.py -v")
        print("    pytest tests/unit/test_empty_state.py -v")
        print("    pytest tests/unit/test_templates_picker_extra.py -v")
        print("    run_tests.bat")
    print("=" * 60)


if __name__ == "__main__":
    main()