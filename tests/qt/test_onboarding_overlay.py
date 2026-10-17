# -*- coding: utf-8 -*-
"""
首次运行引导浮层：不能把用户卡死（P0）

真实故障（2026-10-18）：
    窗口起来后整片发灰、左上角一个黑底橙框，鼠标键盘全部无响应。
    原因有两个：
      1. 步骤卡片的 `sizeHint()` 在布局激活前取值可能为 0，
         卡片被设成 0 高 → 完全看不见；
      2. 高亮用 `CompositionMode_Clear` 在半透明子窗口上"挖洞"，
         某些平台渲染成实心黑块；
      3. 浮层没有任何退出通道（Esc / 点击遮罩都不响应）。

本文件锁定：
    1. 卡片必须可见且有合理高度
    2. Esc 能结束引导
    3. 点击遮罩能推进并最终结束
"""
import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QRect, Qt  # noqa: E402


@pytest.fixture
def overlay(qtbot):
    from PySide6.QtWidgets import QWidget

    from beeoffice.plugins.onboarding import OnboardingOverlay, OnboardingStep

    parent = QWidget()
    parent.resize(800, 600)
    qtbot.addWidget(parent)
    parent.show()

    ov = OnboardingOverlay(parent)
    qtbot.addWidget(ov)
    ov.set_steps([
        OnboardingStep(QRect(10, 5, 80, 30), "步骤一", "说明一", "right"),
        OnboardingStep(QRect(200, 100, 100, 40), "步骤二", "说明二", "bottom"),
    ])
    ov.show()
    qtbot.wait(80)
    yield ov
    try:
        ov.close()
    except Exception:
        pass


def test_tip_card_is_visible(overlay):
    """卡片必须真的显示出来，且高度合理（曾为 0）。"""
    tip = overlay._tip_widget
    assert tip is not None, "没有创建步骤卡片"
    assert tip.isVisible(), "步骤卡片不可见"
    assert tip.height() >= 100, f"步骤卡片高度异常: {tip.height()}"
    assert tip.width() >= 200


def test_escape_closes_overlay(qtbot, overlay):
    """Esc 必须能退出——这是用户唯一的自救通道。"""
    finished = []
    overlay.finished.connect(lambda: finished.append(True))

    qtbot.keyClick(overlay, Qt.Key_Escape)
    qtbot.wait(50)

    assert finished, "按 Esc 没有触发 finished"
    assert not overlay.isVisible(), "按 Esc 后浮层仍然显示"


def test_click_advances_and_finishes(qtbot, overlay):
    """点击遮罩任意位置能推进，最后一步后结束。"""
    finished = []
    overlay.finished.connect(lambda: finished.append(True))

    qtbot.mouseClick(overlay, Qt.LeftButton)
    qtbot.wait(30)
    assert overlay._current_step == 1, "第一次点击应推进到第 2 步"

    qtbot.mouseClick(overlay, Qt.LeftButton)
    qtbot.wait(30)
    assert finished, "最后一步点击后应结束引导"
    assert not overlay.isVisible()
