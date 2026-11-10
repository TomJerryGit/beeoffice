"""BeeSheet 弹窗与公式栏冒烟测试（不弹真实模态框）。"""
import pandas as pd
import pytest

from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QInputDialog, QMenu, QMessageBox,
)

from beeoffice.plugins.beesheet import BeeSheetView


@pytest.fixture
def sheet(qtbot, monkeypatch):
    view = BeeSheetView()
    qtbot.addWidget(view)
    view.model.set_full_dataframe(
        pd.DataFrame({"城市": ["北京", "上海"], "金额": [1, 2]})
    )
    view.table_view.setModel(view.model)
    view.table_view.setCurrentIndex(view.model.index(0, 0))
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)
    monkeypatch.setattr(QMenu, "exec", lambda self, *a, **k: None)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("", False))
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: ("", False))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    for name in ("information", "warning", "question", "critical"):
        monkeypatch.setattr(QMessageBox, name, lambda *a, **k: None)
    return view


def test_data_validation_and_name_manager(sheet):
    sheet._show_data_validation_dialog()
    sheet._show_name_manager()


def test_selection_stats(sheet):
    sheet.table_view.selectRow(0)
    sheet._show_selection_stats()


def test_formula_bar_enter(sheet):
    sheet.formula_bar.setText("=1+1")
    sheet._on_formula_enter()
    assert sheet.model.get_value(0, 0) == 2
    sheet.formula_bar.setText("abc")
    sheet._on_formula_enter()
    assert sheet.model.get_value(0, 0) == "abc"


def test_formula_helpers(sheet):
    sheet.formula_bar.setText("=SUM(")
    sheet._update_param_tip("=SUM(")
    sheet._hide_param_tip()
    sheet._update_formula_preview("=1+1")
    sheet._f1_help()


def test_formula_undo_and_clear(sheet):
    sheet.formula_bar.setText("=1+1")
    sheet._on_formula_enter()
    sheet._clear_audit()
