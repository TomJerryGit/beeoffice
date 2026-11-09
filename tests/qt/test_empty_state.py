"""EmptyStateWidget 高对比度/样式回归测试。"""
from PySide6.QtWidgets import QApplication

from beeoffice.plugins.empty_state import EmptyStateWidget
from beeoffice.theme import Theme


def test_empty_state_primary_and_secondary_styles(qtbot):
    old = Theme.is_high_contrast()
    try:
        Theme.set_high_contrast(True)
        widget = EmptyStateWidget()
        qtbot.addWidget(widget)
        widget.set_state(
            "🐝", "标题", "描述",
            [("主要按钮", "primary", True), ("次要按钮", "secondary", False)],
        )
        assert widget.title_label.text() == "标题"
        assert widget.button_layout.count() == 2
    finally:
        Theme.set_high_contrast(old)
