# tests/test_command_palette.py
"""命令面板测试"""
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeyEvent


class TestRegisterCommand:
    def test_register_basic(self, qtbot):
        from beeoffice.command_palette import CommandPalette
        palette = CommandPalette()
        qtbot.addWidget(palette)
        palette.register_command("测试命令", "描述", lambda: None)
        assert "测试命令" in palette.all_commands


class TestFilterCommands:
    def _make_palette(self, qtbot):
        from beeoffice.command_palette import CommandPalette
        palette = CommandPalette()
        qtbot.addWidget(palette)
        palette.register_command("导出 PDF", "导出为 PDF", lambda: None)
        palette.register_command("导出 DOCX", "导出为 Word", lambda: None)
        return palette

    def test_filter_single_keyword(self, qtbot):
        palette = self._make_palette(qtbot)
        palette.filter_commands("导出")
        assert palette.list_widget.count() == 2


class TestKeyNavigation:
    def test_escape_closes(self, qtbot):
        from beeoffice.command_palette import CommandPalette
        palette = CommandPalette()
        qtbot.addWidget(palette)
        palette.show()
        assert palette.isVisible()
        evt = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
        palette.keyPressEvent(evt)
        assert not palette.isVisible()
