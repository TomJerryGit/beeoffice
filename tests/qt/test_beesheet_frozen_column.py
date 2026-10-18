# -*- coding: utf-8 -*-
"""
蜜算冻结首列：与行冻结对称的视图级冻结（P1-18 第二步）

背景：
    行冻结已完成（`_frozen_row_view`）；列冻结此前同样只是把列的
    resizeMode 设为 Fixed —— 那只锁住列宽，横向滚动时列照样跑掉。

实现（与行冻结对称）：
    在主表 viewport 左侧浮一个只显示第 0 列的 QTableView
    （`_SingleColumnProxy`，O(1)），
    行高与主表同步、纵向滚动同步、viewport 尺寸变化时重新贴合。

已知取舍：
    冻结区域覆盖在主表之上，会拦截点击 —— 与行冻结相同。
    v1 优先保证"看得到"，编辑冻结区单元格需要先解除冻结。
"""
import pytest

pytest.importorskip("PySide6.QtWidgets")

pd = pytest.importorskip("pandas")


@pytest.fixture(scope="module")
def view(qapp):
    from beeoffice.plugins.beesheet import BeeSheetView

    v = BeeSheetView()
    v.show()
    yield v
    try:
        v._remove_frozen_column()
        v._remove_frozen_row()
    except Exception:
        pass
    v.close()
    v.deleteLater()


@pytest.fixture(autouse=True)
def _reset(view):
    view.model.set_full_dataframe(
        pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    )


def test_freeze_creates_overlay(view):
    view._freeze_column(0)
    frozen = getattr(view, "_frozen_column_view", None)
    assert frozen is not None, "冻结首列没有创建视图"
    assert frozen.isVisible(), "冻结列视图不可见"


def test_frozen_view_shows_only_first_column(view):
    view._freeze_column(0)
    frozen = view._frozen_column_view
    assert frozen.model().columnCount() == 1
    assert frozen.model().rowCount() == view.model.rowCount()


def test_frozen_view_width_matches_column(view):
    view._freeze_column(0)
    frozen = view._frozen_column_view
    assert frozen.width() >= 20
    assert abs(frozen.width() - max(view.table_view.columnWidth(0), 20)) <= 4


def test_frozen_data_matches_source(view):
    from PySide6.QtCore import Qt

    view._freeze_column(0)
    proxy = view._frozen_column_view.model()
    assert proxy.data(proxy.index(0, 0), Qt.DisplayRole) == "1"
    assert proxy.data(proxy.index(2, 0), Qt.DisplayRole) == "3"


def test_unfreeze_removes_overlay(view):
    view._freeze_column(0)
    assert view._frozen_column_view is not None
    view._unfreeze_all()
    assert getattr(view, "_frozen_column_view", None) is None


def test_freeze_twice_is_idempotent(view):
    view._freeze_column(0)
    first = view._frozen_column_view
    view._freeze_column(0)
    assert view._frozen_column_view is first


def test_row_and_column_can_coexist(view):
    view._freeze_row(0)
    view._freeze_column(0)
    assert view._frozen_row_view is not None
    assert view._frozen_column_view is not None
    view._unfreeze_all()
    assert getattr(view, "_frozen_row_view", None) is None
    assert getattr(view, "_frozen_column_view", None) is None
