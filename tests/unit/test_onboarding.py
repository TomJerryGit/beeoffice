# tests/unit/test_onboarding.py
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
