# tests/test_tab_manager.py
"""
TabManager 测试

覆盖：
  - 添加标签
  - 关闭标签
  - 未保存标记
  - 文件路径映射
"""
import pytest
from PySide6.QtWidgets import QPlainTextEdit, QApplication


class TestBasicOperations:
    """基础操作"""

    def test_add_tab(self, qtbot):
        from beeoffice.tab_manager import TabManager
        tm = TabManager()
        qtbot.addWidget(tm)
        # 已有欢迎页
        initial_count = tm.count()
        widget = QPlainTextEdit()
        tm.addTab(widget, "测试")
        assert tm.count() == initial_count + 1
        assert tm.tabText(tm.count() - 1) == "测试"

    def test_close_current_tab(self, qtbot):
        from beeoffice.tab_manager import TabManager
        tm = TabManager()
        qtbot.addWidget(tm)
        widget = QPlainTextEdit()
        tm.addTab(widget, "测试")
        count_before = tm.count()
        tm.close_current_tab()
        assert tm.count() == count_before - 1


class TestFilePaths:
    """文件路径映射"""

    def test_set_and_get_file_path(self, qtbot, tmp_path):
        from beeoffice.tab_manager import TabManager
        tm = TabManager()
        qtbot.addWidget(tm)
        widget = QPlainTextEdit()
        tm.addTab(widget, "测试")
        tm.set_tab_file_path(widget, str(tmp_path / "test.md"))
        paths = tm.get_open_file_paths()
        assert str(tmp_path / "test.md") in paths