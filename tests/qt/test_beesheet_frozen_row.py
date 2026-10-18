# -*- coding: utf-8 -*-
"""
蜜算冻结首行：真正的视图级冻结（P1-18 第一步）

缺陷：
    `_freeze_row(0)` 只是把行的 resizeMode 设为 Fixed —— 那只锁住行高，
    滚动时表头照样被顶走，用户看不到任何冻结效果。
    上下文菜单里明明写着"冻结首行"。

修复（v1）：
    在表格 viewport 顶部浮一个只显示第 0 行的 QTableView，
    与主表共用列宽、横向滚动同步、纵向不动。
"""
import pytest

pytest.importorskip("PySide6.QtWidgets")

pd = pytest.importorskip("pandas")


@pytest.fixture
def view(qtbot):
    from beeoffice.plugins.beesheet import BeeSheetView

    v = BeeSheetView()
    qtbot.addWidget(v)
    v.model.set_full_dataframe(
        pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    )
    v.show()          # 子控件的 isVisible() 依赖父窗口已显示
    qtbot.wait(50)
    yield v
    # 只解除冻结，不显式 close()：
    # close() 会立刻销毁子控件，而状态栏的定时器随后才触发，
    # 于是 teardown 时报 "Internal C++ object already deleted"。
    # 交给 qtbot 在会话结束时统一回收即可。
    try:
        v._remove_frozen_row()
    except Exception:
        pass


def test_freeze_creates_overlay(view):
    view._freeze_row(0)
    frozen = getattr(view, "_frozen_row_view", None)
    assert frozen is not None, "冻结首行没有创建任何视图"
    assert frozen.isVisible(), "冻结视图不可见"


def test_frozen_view_shows_only_first_row(view):
    view._freeze_row(0)
    frozen = view._frozen_row_view
    assert frozen.model().rowCount() == 1
    assert frozen.model().columnCount() == view.model.columnCount()


def test_frozen_view_matches_row_height(view):
    view._freeze_row(0)
    frozen = view._frozen_row_view
    assert frozen.height() >= 20
    # 高度应贴着主表首行（允许 ±2px 的边框误差）
    assert abs(frozen.height() - max(view.table_view.rowHeight(0), 20)) <= 4


def test_unfreeze_removes_overlay(view):
    view._freeze_row(0)
    assert view._frozen_row_view is not None
    view._unfreeze_all()
    assert getattr(view, "_frozen_row_view", None) is None


def test_freeze_twice_is_idempotent(view):
    view._freeze_row(0)
    first = view._frozen_row_view
    view._freeze_row(0)
    assert view._frozen_row_view is first


def test_frozen_data_matches_source(view):
    """冻结行显示的内容必须来自第 0 行。"""
    from PySide6.QtCore import Qt

    view._freeze_row(0)
    proxy = view._frozen_row_view.model()
    got = proxy.data(proxy.index(0, 0), Qt.DisplayRole)
    assert got == "1"
