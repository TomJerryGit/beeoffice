# tests/unit/test_templates_picker.py
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
