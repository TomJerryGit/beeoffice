# tests/fidelity/test_task_pane_shell_2026_10_28.py
"""S0：任务窗格壳（TaskPane / TaskPaneManager / app 入口）。"""
from PySide6.QtWidgets import QLabel, QMainWindow

from beeoffice.task_pane import TaskPaneManager


def test_task_pane_show_update_hide(qtbot):
    win = QMainWindow()
    qtbot.addWidget(win)
    win.show()
    manager = TaskPaneManager(win)
    label = QLabel("内容 A")
    dock = manager.show_pane("demo", "演示", label)
    assert dock.isVisible()
    assert dock.widget()._title.text() == "演示"

    label_b = QLabel("内容 B")
    manager.show_pane("demo", "更新标题", label_b)
    assert dock.widget()._title.text() == "更新标题"
    assert dock.widget()._content.count() == 1

    manager.hide_pane("demo")
    assert not dock.isVisible()
    manager.close_pane("demo")
    assert "demo" not in manager._panes


def test_app_show_task_pane(app, qtbot):
    from PySide6.QtWidgets import QDockWidget

    app.show()
    dock = app.show_task_pane("S0 测试", QLabel("hello"), "s0_test")
    assert isinstance(dock, QDockWidget)
    assert dock.isVisible()
    assert dock.widget()._title.text() == "S0 测试"
    app.task_pane_manager.close_pane("s0_test")
