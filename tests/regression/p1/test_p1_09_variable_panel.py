# tests/test_p2_regression/test_p1_09_variable_panel.py
"""P1-9 回归：变量面板刷新保留数据源选择"""
import pytest


def test_source_combo_selection_preserved(qtbot):
    from beeoffice.plugins.variable_panel import VariablePanel
    panel = VariablePanel()
    qtbot.addWidget(panel)
    panel.update_variables([], ["源A", "源B", "源C"])
    panel.source_combo.setCurrentText("源B")
    assert panel.source_combo.currentText() == "源B"
    panel.update_variables([], ["源A", "源B", "源C"])
    assert panel.source_combo.currentText() == "源B"


def test_source_combo_fallback_when_removed(qtbot):
    from beeoffice.plugins.variable_panel import VariablePanel
    panel = VariablePanel()
    qtbot.addWidget(panel)
    panel.update_variables([], ["源A", "源B"])
    panel.source_combo.setCurrentText("源B")
    panel.update_variables([], ["源A", "源C"])
    assert panel.source_combo.currentText() in ("源A", "")
