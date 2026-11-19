"""动态数组溢出到相邻单元格。"""
import pandas as pd
from beeoffice.plugins.beesheet import BeeSheetView


def make_sheet(qtbot):
    s = BeeSheetView(); qtbot.addWidget(s)
    s.model._loaded_df = pd.DataFrame([[1, 10], [2, 20], [3, 30]], columns=["A", "B"])
    s.model.layoutChanged.emit()
    return s


def test_sequence_spills(qtbot):
    s = make_sheet(qtbot)
    s.table_view.setCurrentIndex(s.model.index(0, 0))
    s.formula_bar.setText("=SEQUENCE(2,3)")
    s._on_formula_enter()
    df = s.model._loaded_df
    assert df.iloc[0, 0] == 1
    assert df.iloc[0, 2] == 3
    assert df.iloc[1, 0] == 4
    assert df.iloc[1, 2] == 6
