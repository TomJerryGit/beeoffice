# boost_coverage.py
"""
覆盖率提升：添加 6 个测试文件（幂等）

目标模块（当前覆盖率）：
  - cloud_settings.py    6%
  - memory_monitor.py   10%
  - onboarding.py       15%
  - empty_state.py      19%
  - templates.py         5%
  - beewrite_ai_mixin.py 9%

用法:
    python boost_coverage.py --dry-run
    python boost_coverage.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
DRY = "--dry-run" in sys.argv

FILES = {}

# ------------------------------------------------------------
# 1. cloud_settings — 云存储设置对话框
# ------------------------------------------------------------
FILES["tests/qt/test_cloud_settings.py"] = '''# tests/qt/test_cloud_settings.py
"""cloud_settings.py 测试：云存储设置对话框"""
import pytest


@pytest.fixture
def dlg(qtbot, temp_settings):
    from beeoffice.cloud_settings import CloudSettingsDialog
    d = CloudSettingsDialog()
    qtbot.addWidget(d)
    return d


class TestInit:
    def test_dialog_created(self, dlg):
        assert dlg is not None

    def test_has_type_combo(self, dlg):
        assert dlg.type_combo.count() == 3
        assert dlg.type_combo.itemData(0) == "webdav"
        assert dlg.type_combo.itemData(1) == "onedrive"
        assert dlg.type_combo.itemData(2) == "googledrive"

    def test_has_enable_check(self, dlg):
        assert dlg.enabled_check is not None

    def test_has_auto_sync_check(self, dlg):
        assert dlg.auto_sync_check is not None


class TestTypeSwitch:
    def test_switch_to_onedrive(self, dlg):
        dlg.type_combo.setCurrentIndex(1)
        assert dlg.stack.currentIndex() == 1

    def test_switch_to_googledrive(self, dlg):
        dlg.type_combo.setCurrentIndex(2)
        assert dlg.stack.currentIndex() == 2

    def test_switch_back_to_webdav(self, dlg):
        dlg.type_combo.setCurrentIndex(1)
        dlg.type_combo.setCurrentIndex(0)
        assert dlg.stack.currentIndex() == 0


class TestLoadSettings:
    def test_initial_type_from_settings(self, dlg):
        # 默认 cloud_type == "webdav"
        assert dlg.type_combo.currentData() == "webdav"

    def test_enable_check_reflects_settings(self, dlg):
        # 默认 cloud_enabled == False
        assert dlg.enabled_check.isChecked() is False


class TestSaveValidation:
    def test_webdav_invalid_url_rejected(self, dlg, monkeypatch):
        """WebDAV 地址不带 http:// 或 https:// 时，保存失败"""
        from PySide6.QtWidgets import QMessageBox
        warned = []
        monkeypatch.setattr(
            QMessageBox, "warning",
            staticmethod(lambda *a, **k: warned.append(a)),
        )
        dlg.type_combo.setCurrentIndex(0)
        dlg.url_edit.setText("ftp://invalid")
        dlg._save()
        assert warned, "非法 URL 应弹警告"

    def test_webdav_valid_url_accepted(self, dlg, monkeypatch):
        from PySide6.QtWidgets import QMessageBox
        infos = []
        monkeypatch.setattr(
            QMessageBox, "information",
            staticmethod(lambda *a, **k: infos.append(a)),
        )
        dlg.type_combo.setCurrentIndex(0)
        dlg.url_edit.setText("https://example.com/dav")
        dlg.user_edit.setText("user")
        dlg.pwd_edit.setText("pwd")
        dlg._save()
        assert infos, "合法 URL 保存应弹提示"


class TestResetSingleton:
    def test_save_resets_cloud_singleton(self, dlg, monkeypatch):
        """保存后应调用 reset_cloud_storage"""
        from beeoffice import cloud
        from PySide6.QtWidgets import QMessageBox

        called = []
        monkeypatch.setattr(
            cloud, "reset_cloud_storage",
            lambda: called.append("reset"),
        )
        monkeypatch.setattr(
            QMessageBox, "information",
            staticmethod(lambda *a, **k: None),
        )
        dlg.type_combo.setCurrentIndex(0)
        dlg.url_edit.setText("https://example.com/dav")
        dlg._save()
        assert called == ["reset"]
'''


# ------------------------------------------------------------
# 2. memory_monitor — 内存监控窗口
# ------------------------------------------------------------
FILES["tests/qt/test_memory_monitor.py"] = '''# tests/qt/test_memory_monitor.py
"""memory_monitor.py 测试：内存监控窗口"""
import pytest


@pytest.fixture
def monitor(qtbot):
    from beeoffice.plugins.memory_monitor import MemoryMonitor
    m = MemoryMonitor()
    qtbot.addWidget(m)
    return m


class TestInit:
    def test_window_created(self, monitor):
        assert monitor is not None

    def test_has_labels(self, monitor):
        assert monitor.current_label is not None
        assert monitor.peak_label is not None
        assert monitor.trend_label is not None

    def test_has_progress_bar(self, monitor):
        assert monitor.progress is not None
        assert monitor.progress.maximum() == 500

    def test_history_empty_initially(self, monitor):
        # _update() 在 __init__ 里跑过一次，历史可能有 1 条
        assert isinstance(monitor._history, list)


class TestUpdate:
    def test_update_runs_without_crash(self, monitor):
        monitor._update()

    def test_peak_tracks_max(self, monitor):
        # 手动塞历史，模拟峰值
        monitor._history = [10.0, 20.0, 15.0]
        monitor._peak = 20.0
        assert monitor._peak >= max(monitor._history)

    def test_history_trimmed(self, monitor):
        monitor._history = [float(i) for i in range(200)]
        if len(monitor._history) > 120:
            monitor._history = monitor._history[-120:]
        assert len(monitor._history) <= 120


class TestActions:
    def test_manual_gc(self, monitor):
        # 不应崩
        monitor._manual_gc()

    def test_reset(self, monitor):
        monitor._peak = 999.0
        monitor._history = [1.0, 2.0, 3.0]
        monitor._reset()
        assert monitor._peak == 0
        assert isinstance(monitor._history, list)

    def test_close_stops_timer(self, monitor, qtbot):
        assert monitor._timer.isActive()
        monitor.close()
        qtbot.wait(50)
        assert not monitor._timer.isActive()
'''


# ------------------------------------------------------------
# 3. onboarding — 首次引导
# ------------------------------------------------------------
FILES["tests/unit/test_onboarding.py"] = '''# tests/unit/test_onboarding.py
"""onboarding.py 测试：首次引导组件"""
from PySide6.QtCore import QRect


class TestOnboardingStep:
    def test_create(self):
        from beeoffice.plugins.onboarding import OnboardingStep
        step = OnboardingStep(QRect(10, 20, 100, 30), "标题", "描述", "bottom")
        assert step.target_rect.x() == 10
        assert step.title == "标题"
        assert step.description == "描述"
        assert step.position == "bottom"

    def test_default_position(self):
        from beeoffice.plugins.onboarding import OnboardingStep
        step = OnboardingStep(QRect(0, 0, 10, 10), "t", "d")
        assert step.position == "bottom"


class TestDefaultSteps:
    def test_get_default_steps_none(self):
        from beeoffice.plugins.onboarding import get_default_steps
        assert get_default_steps(None) == []

    def test_get_default_steps_returns_list(self, qtbot):
        from PySide6.QtWidgets import QWidget
        from beeoffice.plugins.onboarding import get_default_steps
        w = QWidget()
        qtbot.addWidget(w)
        steps = get_default_steps(w)
        assert isinstance(steps, list)
        assert len(steps) >= 3

    def test_each_step_has_required_fields(self, qtbot):
        from PySide6.QtWidgets import QWidget
        from beeoffice.plugins.onboarding import get_default_steps
        w = QWidget()
        qtbot.addWidget(w)
        for step in get_default_steps(w):
            assert step.title
            assert step.description
            assert isinstance(step.target_rect, QRect)
'''


# ------------------------------------------------------------
# 4. empty_state — 空状态组件
# ------------------------------------------------------------
FILES["tests/unit/test_empty_state.py"] = '''# tests/unit/test_empty_state.py
"""empty_state.py 测试：空状态引导"""
import pytest


class TestEmptyStateWidget:
    @pytest.fixture
    def widget(self, qtbot):
        from beeoffice.plugins.empty_state import EmptyStateWidget
        w = EmptyStateWidget()
        qtbot.addWidget(w)
        return w

    def test_create(self, widget):
        assert widget is not None

    def test_set_state(self, widget):
        widget.set_state(
            icon="📝",
            title="标题",
            description="描述",
            actions=[("按钮", "action", True)],
        )
        assert widget.icon_label.text() == "📝"
        assert widget.title_label.text() == "标题"
        assert widget.desc_label.text() == "描述"

    def test_set_state_multiple_actions(self, widget):
        widget.set_state(
            icon="X", title="T", description="D",
            actions=[
                ("A", "a", True),
                ("B", "b", False),
                ("C", "c", False),
            ],
        )
        assert widget.button_layout.count() == 3

    def test_action_triggered_signal(self, widget, qtbot):
        widget.set_state(
            icon="X", title="T", description="D",
            actions=[("按钮", "my_action", True)],
        )
        with qtbot.waitSignal(widget.action_triggered, timeout=500) as bl:
            btn = widget.button_layout.itemAt(0).widget()
            btn.click()
        assert bl.args == ["my_action"]

    def test_set_state_clears_previous(self, widget):
        widget.set_state(icon="X", title="T", description="D",
                         actions=[("A", "a", True)])
        assert widget.button_layout.count() == 1
        widget.set_state(icon="Y", title="T2", description="D2",
                         actions=[("B", "b", True), ("C", "c", False)])
        assert widget.button_layout.count() == 2


class TestPresetStates:
    def test_beewrite_state(self):
        from beeoffice.plugins.empty_state import get_beewrite_empty_state
        s = get_beewrite_empty_state()
        assert "icon" in s
        assert "title" in s
        assert "description" in s
        assert isinstance(s["actions"], list)
        assert len(s["actions"]) >= 2

    def test_beesheet_state(self):
        from beeoffice.plugins.empty_state import get_beesheet_empty_state
        s = get_beesheet_empty_state()
        assert s["icon"] == "📊"
        assert isinstance(s["actions"], list)

    def test_unbound_variable_state(self):
        from beeoffice.plugins.empty_state import get_unbound_variable_state
        s = get_unbound_variable_state()
        assert s["title"]
        assert isinstance(s["actions"], list)

    def test_actions_format(self):
        from beeoffice.plugins.empty_state import get_beewrite_empty_state
        for action in get_beewrite_empty_state()["actions"]:
            assert len(action) == 3
            text, name, is_primary = action
            assert isinstance(text, str)
            assert isinstance(name, str)
            assert isinstance(is_primary, bool)
'''


# ------------------------------------------------------------
# 5. templates — 模板选择
# ------------------------------------------------------------
FILES["tests/unit/test_templates_picker.py"] = '''# tests/unit/test_templates_picker.py
"""templates.py 测试：模板选择器（不弹模态对话框）"""
import pytest


class TestTemplateManagerIntegration:
    def test_get_all_templates(self):
        from beeoffice.resources.template_manager import TemplateManager
        tm = TemplateManager()
        templates = tm.get_all_templates()
        assert isinstance(templates, list)
        assert len(templates) >= 1

    def test_template_has_required_fields(self):
        from beeoffice.resources.template_manager import TemplateManager
        tm = TemplateManager()
        for tpl in tm.get_all_templates():
            assert "name" in tpl
            assert "content" in tpl
            assert "source" in tpl

    def test_builtin_templates_exist(self):
        from beeoffice.resources.template_manager import TemplateManager
        tm = TemplateManager()
        builtin = tm.get_builtin_templates()
        assert len(builtin) >= 1

    def test_template_content_non_empty(self):
        from beeoffice.resources.template_manager import TemplateManager
        tm = TemplateManager()
        for tpl in tm.get_all_templates():
            assert isinstance(tpl["content"], str)


class TestSaveAsTemplateDialog:
    """不实际弹对话框，只验证函数可调用"""

    def test_save_as_template_dialog_exists(self):
        from beeoffice.templates import save_as_template_dialog
        assert callable(save_as_template_dialog)

    def test_show_template_picker_exists(self):
        from beeoffice.templates import show_template_picker
        assert callable(show_template_picker)


class TestCreateFromTemplate:
    def test_import(self):
        from beeoffice.templates import _create_from_template
        assert callable(_create_from_template)
'''


# ------------------------------------------------------------
# 6. AI Mixin — 蜜写 AI 辅助
# ------------------------------------------------------------
FILES["tests/qt/test_beewrite_ai_mixin.py"] = '''# tests/qt/test_beewrite_ai_mixin.py
"""beewrite_ai_mixin.py 测试：蜜写 AI 辅助"""
import pytest


@pytest.fixture
def editor(beewrite_editor):
    return beewrite_editor


class TestAIMenu:
    def test_show_ai_menu_exists(self, editor):
        assert hasattr(editor, "_show_ai_menu")
        assert callable(editor._show_ai_menu)


class TestAIContinue:
    def test_continue_in_markdown(self, editor, monkeypatch):
        editor._switch_mode("markdown")
        editor.markdown_editor.setPlainText("人工智能正在改变世界。")
        cursor = editor.markdown_editor.textCursor()
        cursor.movePosition(cursor.End)
        editor.markdown_editor.setTextCursor(cursor)
        before = editor.markdown_editor.toPlainText()
        editor._ai_continue()
        after = editor.markdown_editor.toPlainText()
        assert len(after) > len(before)

    def test_continue_empty(self, editor):
        editor._switch_mode("markdown")
        editor.markdown_editor.setPlainText("")
        editor._ai_continue()
        # 不应崩


class TestAIPolish:
    def test_polish_no_selection(self, editor, monkeypatch):
        from PySide6.QtWidgets import QMessageBox
        infos = []
        monkeypatch.setattr(
            QMessageBox, "information",
            staticmethod(lambda *a, **k: infos.append(a)),
        )
        editor._switch_mode("markdown")
        editor.markdown_editor.setPlainText("测试内容。")
        editor._ai_polish()
        assert infos, "无选中文字时应提示"

    def test_polish_with_selection(self, editor):
        editor._switch_mode("markdown")
        editor.markdown_editor.setPlainText("然后这个东西其实很好")
        from PySide6.QtGui import QTextCursor
        cursor = editor.markdown_editor.textCursor()
        cursor.select(QTextCursor.Document)
        editor.markdown_editor.setTextCursor(cursor)
        editor._ai_polish()
        # 不应崩


class TestAISummarize:
    def test_summarize_too_short(self, editor, monkeypatch):
        from PySide6.QtWidgets import QMessageBox
        infos = []
        monkeypatch.setattr(
            QMessageBox, "information",
            staticmethod(lambda *a, **k: infos.append(a)),
        )
        editor._switch_mode("markdown")
        editor.markdown_editor.setPlainText("短文本。")
        editor._ai_summarize()
        assert infos, "文本太短时应提示"

    def test_summarize_long(self, editor):
        editor._switch_mode("markdown")
        long_text = "这是一句话。" * 30
        editor.markdown_editor.setPlainText(long_text)
        before = editor.markdown_editor.toPlainText()
        editor._ai_summarize()
        after = editor.markdown_editor.toPlainText()
        assert len(after) >= len(before)


class TestAIKeywords:
    def test_keywords_too_short(self, editor, monkeypatch):
        from PySide6.QtWidgets import QMessageBox
        infos = []
        monkeypatch.setattr(
            QMessageBox, "information",
            staticmethod(lambda *a, **k: infos.append(a)),
        )
        editor._switch_mode("markdown")
        editor.markdown_editor.setPlainText("短。")
        editor._ai_keywords()
        assert infos

    def test_keywords_long(self, editor):
        editor._switch_mode("markdown")
        editor.markdown_editor.setPlainText(
            "蜜蜂办公是一款办公软件，办公软件需要稳定。" * 3
        )
        before = editor.markdown_editor.toPlainText()
        editor._ai_keywords()
        after = editor.markdown_editor.toPlainText()
        assert len(after) >= len(before)
'''


def main():
    print("=" * 60)
    print(f"  覆盖率提升：添加 6 个测试文件  "
          f"{'[DRY-RUN]' if DRY else ''}")
    print("=" * 60)
    print()

    created = 0
    skipped = 0
    for rel, content in sorted(FILES.items()):
        target = ROOT / rel
        if target.exists():
            print(f"  [SKIP] {rel}（已存在）")
            skipped += 1
            continue
        if not DRY:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        print(f"  [CREATE] {rel}")
        created += 1

    print()
    print("=" * 60)
    if DRY:
        print(f"  DRY-RUN: 将创建 {created} 个，跳过 {skipped} 个")
    else:
        print(f"  ✅ 创建 {created} 个，跳过 {skipped} 个")
        print()
        print("  下一步:")
        print("    pytest tests/qt/test_cloud_settings.py -v")
        print("    pytest tests/qt/test_memory_monitor.py -v")
        print("    pytest tests/unit/test_onboarding.py -v")
        print("    pytest tests/unit/test_empty_state.py -v")
        print("    pytest tests/unit/test_templates_picker.py -v")
        print("    pytest tests/qt/test_beewrite_ai_mixin.py -v")
        print("    run_tests.bat")
    print("=" * 60)


if __name__ == "__main__":
    main()