# tests/test_p2_regression/test_p1_04_lightweight_app.py
"""P1-4 回归：app fixture 不触发插件加载"""


def test_app_does_not_load_plugins(app):
    assert app.plugin_manager is None or len(app.plugins) == 0


def test_app_does_not_show_restore_dialog(app, qtbot):
    qtbot.wait(200)
    from PySide6.QtWidgets import QApplication
    assert QApplication.activeModalWidget() is None


def test_app_with_plugins_loads_plugins(app_with_plugins):
    assert app_with_plugins.plugin_manager is not None
    assert len(app_with_plugins.plugins) >= 3
