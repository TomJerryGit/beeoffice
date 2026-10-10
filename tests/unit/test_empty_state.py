# tests/unit/test_empty_state.py
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
