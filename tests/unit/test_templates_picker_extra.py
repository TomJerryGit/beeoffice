# tests/unit/test_templates_picker_extra.py
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
        tpl = {"name": "测试模板", "content": "# 标题\n\n正文"}
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
        save_as_template_dialog(parent, "   \n\t  ")
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
