# tests/fidelity/test_beesheet_multisort.py
"""
蜜算多级排序回归（2026-10-22，WPS 式细节 4.3）。

## 修的是什么
原实现只有单列排序（`sort_by_column`），多列需求要反复排序——后一次会覆盖前一次，
并不是真正的多级排序。现在：
- 排序对话框最多 3 个键（列 + 升降序），一次性 `sort_values(by=[...])`；
- 只对**真实数据行**排序，模型补齐的 1000 行显示空行不参与（否则空行会排到前面）；
- 排序/撤销通过 `SortCommand → model.set_full_dataframe()` 同步 `_real_rows/_full_df`；
- 保留 `sort_by_column` 兼容旧调用。

## 测试点
1. 两级排序结果正确（姓名升序 + 分数降序）；
2. 单级排序仍可用；
3. 撤销恢复原顺序；
4. 空 keys/越界列给出正确行为；
5. 排序后模型真实行数与列名不变（不给空行插队）。
"""
import pandas as pd
import pytest

from beeoffice.plugins.beesheet import BeeSheetView


DATA = {
    "姓名": ["b", "a", "a", "b", "c"],
    "分数": [2, 3, 1, 1, 2],
    "备注": ["x", "y", "z", "w", "v"],
}


def _view():
    view = BeeSheetView()
    view.model.set_full_dataframe(pd.DataFrame(DATA))
    return view


def _rows(view):
    model = view.model
    real = int(getattr(model, "_real_rows", 0) or 0)
    return [
        tuple(model.get_value(r, c) for c in range(model.columnCount()))
        for r in range(real)
    ]


def test_two_level_sort(qtbot):
    view = _view()
    qtbot.addWidget(view)
    assert view.sort_by_columns([(0, True), (1, False)]) is True
    assert _rows(view) == [
        ("a", 3, "y"),
        ("a", 1, "z"),
        ("b", 2, "x"),
        ("b", 1, "w"),
        ("c", 2, "v"),
    ]


def test_single_level_legacy_method(qtbot):
    view = _view()
    qtbot.addWidget(view)
    assert view.sort_by_column(1, ascending=True) is True
    assert [r[1] for r in _rows(view)] == [1, 1, 2, 2, 3]


def test_undo_restores_original_order(qtbot):
    view = _view()
    qtbot.addWidget(view)
    before = _rows(view)
    view.sort_by_columns([(1, False), (0, True)])
    view.undo()
    assert _rows(view) == before


def test_empty_keys_returns_false(qtbot):
    view = _view()
    qtbot.addWidget(view)
    assert view.sort_by_columns([]) is False


def test_out_of_range_column_raises(qtbot):
    view = _view()
    qtbot.addWidget(view)
    with pytest.raises(ValueError):
        view.sort_by_columns([(99, True)])


def test_real_rows_do_not_include_padding(qtbot):
    view = _view()
    qtbot.addWidget(view)
    view.sort_by_columns([(0, True)])
    assert view.model._real_rows == len(DATA["姓名"])
    # 真实行不能是空名字（空行是补齐行，不应被排序提前）
    assert all(row[0] != "" for row in _rows(view))
