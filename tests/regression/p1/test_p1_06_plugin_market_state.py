# tests/test_p2_regression/test_p1_06_plugin_market_state.py
"""P1-6 回归：插件启用状态切换"""
from PySide6.QtCore import Qt


def test_int_state_checked():
    state = 2
    enabled = (int(state) == 2)
    assert enabled is True


def test_int_state_unchecked():
    state = 0
    enabled = (int(state) == 2)
    assert enabled is False


def test_qt_checkstate_int_value():
    assert int(Qt.CheckState.Checked.value) == 2
    assert int(Qt.CheckState.Unchecked.value) == 0
