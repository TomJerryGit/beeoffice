"""BeeSheet 行列与填充 Mixin 补测。"""
import pandas as pd
import pytest
from PySide6.QtCore import Qt

from beeoffice.plugins.beesheet import BeeSheetView


@pytest.fixture
def sheet(qtbot):
    view = BeeSheetView()
    qtbot.addWidget(view)
    view.model.set_full_dataframe(pd.DataFrame({
        "A": [1, 2, None], "B": ["x", "y", None]
    }))
    view.table_view.setModel(view.model)
    view.table_view.setCurrentIndex(view.model.index(1, 0))
    return view


def test_insert_delete_rows(sheet):
    n = len(sheet.model._loaded_df)
    sheet._insert_row_above()
    assert len(sheet.model._loaded_df) == n + 1
    sheet._insert_row_below()
    assert len(sheet.model._loaded_df) == n + 2
    sheet._delete_current_row()
    assert len(sheet.model._loaded_df) == n + 1


def test_insert_delete_cols(sheet):
    n = len(sheet.model._loaded_df.columns)
    sheet._insert_col_left()
    assert len(sheet.model._loaded_df.columns) == n + 1
    sheet._insert_col_right()
    assert len(sheet.model._loaded_df.columns) == n + 2
    sheet._delete_current_col()
    assert len(sheet.model._loaded_df.columns) == n + 1


def test_delete_last_row_protected(sheet):
    sheet.model.set_full_dataframe(pd.DataFrame({"A": [1]}))
    sheet.table_view.setCurrentIndex(sheet.model.index(0, 0))
    sheet._delete_current_row()
    assert len(sheet.model._loaded_df) == 1


def test_merge_no_selection(sheet):
    sheet._merge_cells()  # 无选区：直接返回


def test_fill_down_value(sheet):
    sheet.model.set_full_dataframe(pd.DataFrame({"A": [1, "", ""]}))
    sheet.table_view.setCurrentIndex(sheet.model.index(0, 0))
    sheet._fill_down([0], 0)
    assert sheet.model.get_value(1, 0) == 1
    assert sheet.model.get_value(2, 0) == 1


def test_fill_down_formula(sheet):
    sheet.model.set_full_dataframe(pd.DataFrame({"A": [1, "", ""]}))
    sheet.table_view.setCurrentIndex(sheet.model.index(0, 0))
    sheet._formula_cells = {(0, 0): "=A1"}
    sheet._fill_down([0], 0)
    assert (1, 0) in sheet._formula_cells
    assert sheet._formula_cells[(1, 0)] == "=A2"


def test_shortcut_fill_down_and_right(sheet):
    sheet.model.set_full_dataframe(pd.DataFrame({"A": [1, ""], "B": [2, ""]}))
    sheet._shortcut_fill_down()  # 无选区：安全返回
    sheet._shortcut_fill_right()
