# tests/test_beewrite_basic.py
"""
BeeWriteEditor 基础功能测试

覆盖：
  - 初始化
  - 模式切换
  - 内容接口
  - 文档类型
"""
import pytest


class TestInit:
    """初始化"""

    def test_editor_created(self, beewrite_editor):
        """编辑器应成功创建"""
        assert beewrite_editor is not None

    def test_default_mode_is_markdown(self, beewrite_editor):
        """默认模式为 Markdown"""
        assert beewrite_editor._edit_mode == "markdown"

    def test_default_doc_kind_is_markdown(self, beewrite_editor):
        """默认文档类型为 markdown"""
        assert beewrite_editor._doc_kind == "markdown"

    def test_current_file_path_is_none(self, beewrite_editor):
        """初始无当前路径"""
        assert beewrite_editor._current_file_path is None


class TestModeSwitch:
    """模式切换"""

    def test_switch_to_rich(self, beewrite_editor):
        """切到富文本"""
        beewrite_editor._switch_mode("rich_text")
        assert beewrite_editor._edit_mode == "rich_text"

    def test_switch_back_to_md(self, beewrite_editor):
        """切回 Markdown"""
        beewrite_editor._switch_mode("rich_text")
        beewrite_editor._switch_mode("markdown")
        assert beewrite_editor._edit_mode == "markdown"

    def test_switch_preserves_content(self, beewrite_editor):
        """切模式保留内容"""
        beewrite_editor.set_content("# 测试标题\n\n正文内容\n")
        beewrite_editor._switch_mode("rich_text")
        beewrite_editor._switch_mode("markdown")
        content = beewrite_editor.content()
        assert "测试标题" in content
        assert "正文内容" in content


class TestContentInterface:
    """内容接口"""

    def test_set_get_content(self, beewrite_editor):
        """设置和获取内容"""
        beewrite_editor.set_content("测试内容")
        assert beewrite_editor.content() == "测试内容"

    def test_get_rendered_content(self, beewrite_editor):
        """获取渲染后内容"""
        beewrite_editor.set_content("# 标题\n")
        rendered = beewrite_editor.get_rendered_content()
        assert "标题" in rendered


class TestDocKind:
    """文档类型"""

    def test_set_doc_kind_word(self, beewrite_editor):
        """设置 Word 类型"""
        beewrite_editor.set_doc_kind("word")
        assert beewrite_editor._doc_kind == "word"

    def test_set_doc_kind_markdown(self, beewrite_editor):
        """设置 Markdown 类型"""
        beewrite_editor.set_doc_kind("markdown")
        assert beewrite_editor._doc_kind == "markdown"

    def test_set_doc_kind_invalid(self, beewrite_editor):
        """无效类型应被忽略"""
        beewrite_editor.set_doc_kind("invalid")
        assert beewrite_editor._doc_kind == "markdown"  # 保持默认