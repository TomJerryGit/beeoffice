"""BeeSheet W3 数据整理工具测试。"""
import pandas as pd
from PySide6.QtWidgets import QInputDialog

from beeoffice.plugins.beesheet import BeeSheetView
from beeoffice.plugins.beesheet_data_tools_mixin import (
    consolidate, remove_duplicate_rows, split_column, subtotal,
)


def test_remove_duplicates():
    df = pd.DataFrame({"A": [1, 1, 2], "B": ["x", "x", "y"]})
    out = remove_duplicate_rows(df)
    assert len(out) == 2
    assert list(out["A"]) == [1, 2]


def test_split_column():
    df = pd.DataFrame({"A": ["x,y", "p,q"], "C": [1, 2]})
    out = split_column(df, "A", ",")
    assert list(out.columns) == ["A_1", "A_2", "C"]
    assert out.iloc[0, 0] == "x"


def test_subtotal():
    df = pd.DataFrame({"组": ["a", "a", "b"], "值": [1, 2, 3]})
    out = subtotal(df, "组", ["值"])
    assert list(out["值"]) == [3, 3]


def test_consolidate():
    a = pd.DataFrame({"x": [1, 2]})
    b = pd.DataFrame({"x": [3, 4]})
    out = consolidate([a, b])
    assert list(out["x"]) == [4, 6]


def make_sheet(qtbot, df):
    v = BeeSheetView()
    qtbot.addWidget(v)
    v.model.set_full_dataframe(df)
    v.table_view.setModel(v.model)
    return v


def test_remove_duplicates_ui(qtbot):
    sheet = make_sheet(qtbot, pd.DataFrame({"A": [1, 1, 2]}))
    sheet._remove_duplicates()
    assert len(sheet.model.df) == 2


def test_split_column_ui(qtbot, monkeypatch):
    sheet = make_sheet(qtbot, pd.DataFrame({"A": ["x,y", "p,q"]}))
    sheet.table_view.setCurrentIndex(sheet.model.index(0, 0))
    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: (",", True))
    )
    sheet._split_column_dialog()
    assert "A_1" in sheet.model.df.columns
