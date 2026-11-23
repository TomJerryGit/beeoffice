"""动态数组溢出到相邻单元格。"""
import pandas as pd
from beeoffice.plugins.beesheet import BeeSheetView


def make_sheet(qtbot, empty=False):
    s = BeeSheetView(); qtbot.addWidget(s)
    if empty:
        s.model._loaded_df = pd.DataFrame(index=range(3), columns=["A", "B", "C"])
    else:
        s.model._loaded_df = pd.DataFrame([[1, 10], [2, 20], [3, 30]], columns=["A", "B"])
    s.model.layoutChanged.emit()
    return s


def test_sequence_spills(qtbot):
    s = make_sheet(qtbot, empty=True)
    s.table_view.setCurrentIndex(s.model.index(0, 0))
    s.formula_bar.setText("=SEQUENCE(2,3)")
    s._on_formula_enter()
    df = s.model._loaded_df
    assert df.iloc[0, 0] == 1
    assert df.iloc[0, 2] == 3
    assert df.iloc[1, 0] == 4
    assert df.iloc[1, 2] == 6


def test_spill_conflict_blocks_and_reports(qtbot):
    s = make_sheet(qtbot, empty=True)
    s.model._loaded_df.iloc[0, 1] = "占用"
    s.table_view.setCurrentIndex(s.model.index(0, 0))
    s.formula_bar.setText("=SEQUENCE(2,2)")
    s._on_formula_enter()
    assert s.model._loaded_df.iloc[0, 0] == "#SPILL!"
    assert s.model._loaded_df.iloc[0, 1] == "占用"


def test_spill_recovers_after_blocker_removed(qtbot):
    s = make_sheet(qtbot, empty=True)
    s.table_view.setCurrentIndex(s.model.index(0, 0))
    s.formula_bar.setText("=SEQUENCE(2,2)")
    s._on_formula_enter()
    assert s.model._loaded_df.iloc[0, 1] == 2
    s.model._loaded_df.iloc[0, 1] = "占用"
    s._recalc_formulas(force=True)
    assert s.model._loaded_df.iloc[0, 0] == "#SPILL!"
    s.model._loaded_df.iloc[0, 1] = None
    s._recalc_formulas(force=True)
    assert s.model._loaded_df.iloc[0, 0] == 1
    assert s.model._loaded_df.iloc[0, 1] == 2
    assert s.model._loaded_df.iloc[1, 0] == 3
