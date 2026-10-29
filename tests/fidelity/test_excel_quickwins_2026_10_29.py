# tests/fidelity/test_excel_quickwins_2026_10_29.py
"""S1：Excel 快赢回归（冻结窗格 / 多级排序 / 数字格式）。"""
import pandas as pd

from beeoffice.plugins.beesheet import BeeSheetView


def _view(qtbot):
    view = BeeSheetView()
    qtbot.addWidget(view)
    view.resize(900, 600)
    view.show()
    return view


def test_freeze_first_row_and_unfreeze(qtbot):
    view = _view(qtbot)
    view.model.set_full_dataframe(pd.DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]}))
    view._freeze_first_row()
    qtbot.wait(20)
    assert view._freeze_panes == "A2"
    assert view._frozen_top == 1
    assert view._frozen_top_view.isVisible()
    view._unfreeze_panes()
    assert view._freeze_panes is None
    assert not view._frozen_top_view.isVisible()


def test_multi_level_sort(qtbot):
    view = _view(qtbot)
    view.model.set_full_dataframe(pd.DataFrame({
        "组": ["B", "A", "B", "A"],
        "值": [2, 9, 1, 5],
    }))
    view.sort_by_columns([(0, True), (1, False)])
    rows = [
        (view.model.index(r, 0).data(), view.model.index(r, 1).data())
        for r in range(4)
    ]
    assert rows == [("A", "9"), ("A", "5"), ("B", "2"), ("B", "1")]


def test_number_formats_wan_and_sign(qtbot):
    view = _view(qtbot)
    view.model.set_full_dataframe(pd.DataFrame({"金额": [12345.678, -200.0]}))
    idx = view.model.index(0, 0)
    view.table_view.setCurrentIndex(idx)
    view.table_view.selectionModel().select(
        idx, view.table_view.selectionModel().SelectionFlag.ClearAndSelect
    )
    view._apply_num_format("万元")
    shown = view.model.index(0, 0).data()
    assert "万" in str(shown)

    view._apply_num_format("正负号")
    shown = view.model.index(0, 0).data()
    assert str(shown).startswith("+")


def test_freeze_button_is_ribbon_dropdown(qtbot):
    from PySide6.QtWidgets import QToolButton

    view = _view(qtbot)
    assert isinstance(view._freeze_btn, QToolButton)
    assert view._freeze_btn.menu() is not None


def test_custom_number_format(qtbot):
    view = _view(qtbot)
    view.model.set_full_dataframe(pd.DataFrame({"金额": [12.5]}))
    idx = view.model.index(0, 0)
    view.table_view.setCurrentIndex(idx)
    view.table_view.selectionModel().select(
        idx, view.table_view.selectionModel().SelectionFlag.ClearAndSelect
    )
    view._custom_format_edit.setText('0.00" 元"')
    view._apply_custom_number_format()
    assert "元" in str(view.model.index(0, 0).data())


def test_custom_sequence_sort(qtbot):
    view = _view(qtbot)
    view.model.set_full_dataframe(pd.DataFrame({"优先级": ["低", "高", "中"]}))
    view.sort_by_custom_sequence(0, ["高", "中", "低"])
    rows = [view.model.index(r, 0).data() for r in range(3)]
    assert rows == ["高", "中", "低"]
