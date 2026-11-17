"""Wave 5 P1：Excel 条件格式管理器。"""
import pandas as pd
from beeoffice.plugins.beesheet import BeeSheetView


def make_sheet(qtbot):
    s = BeeSheetView()
    qtbot.addWidget(s)
    s.model.set_full_dataframe(pd.DataFrame({"金额": [1, 2, 3]}))
    s.table_view.setModel(s.model)
    return s


def test_remove_and_clear_conditional_formats(qtbot):
    sheet = make_sheet(qtbot)
    sheet._add_data_bars(0)
    assert 0 in sheet._conditional_formats
    sheet._remove_conditional_format(0)
    assert 0 not in sheet._conditional_formats
    sheet._add_color_scale(0)
    sheet._add_data_bars(0)
    sheet._clear_all_conditional_formats()
    assert sheet._conditional_formats == {}
