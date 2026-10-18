# -*- coding: utf-8 -*-
"""
蜜算排序：数值列必须能排（P1，实测缺陷）

缺陷（全功能扫描发现）：
    `set_full_dataframe` 会把数据补齐到 1000 行、用**空字符串**填充，
    数值列因此变成 object 类型（int 与 '' 混合）。
    `sort_by_column` 对整个 df 调 `sort_values` → TypeError，
    异常被 Qt 槽吞掉 —— 用户点"排序"完全没有反应。

    另一个隐藏问题：原实现只更新 `_loaded_df`，`_full_df` 仍是旧顺序，
    之后滚动加载分块会把未排序的数据拼回去。

修复：
    只对真实数据行排序，空行原样留在末尾，两个 DataFrame 同步更新；
    列内混合类型时给出可读提示而不是抛异常。

测试组织说明：
    整个文件复用**一个** BeeSheetView。此前每个用例各建一个视图，
    六个视图在同一进程里销毁时会触发 Qt 的访问违例（0xC0000005）——
    这是测试夹具的问题，不是产品崩溃。
"""
import pytest

pytest.importorskip("PySide6.QtWidgets")

pd = pytest.importorskip("pandas")

DATA = {"名称": ["甲", "乙", "丙"], "数量": [2, 3, 1]}


@pytest.fixture(scope="module")
def view(qapp):
    from beeoffice.plugins.beesheet import BeeSheetView

    v = BeeSheetView()
    v.show()
    yield v
    v.close()
    v.deleteLater()


@pytest.fixture(autouse=True)
def _reset(view):
    view.model.set_full_dataframe(pd.DataFrame(DATA))
    view._undo_stack = []
    view._redo_stack = []


def _col(view):
    real = view.model._real_rows
    return [int(x) for x in view.model.df["数量"].iloc[:real]]


def test_sort_descending_on_numeric_column(view):
    view.sort_by_column(1, ascending=False)
    assert _col(view) == [3, 2, 1]


def test_sort_ascending_on_numeric_column(view):
    view.sort_by_column(1, ascending=True)
    assert _col(view) == [1, 2, 3]


def test_sort_keeps_real_row_count(view):
    view.sort_by_column(1, ascending=True)
    assert view.model._real_rows == 3


def test_sort_updates_full_df_too(view):
    """`_full_df` 也必须同步，否则滚动加载会把旧顺序拼回来。"""
    view.sort_by_column(1, ascending=False)
    full_real = [int(x) for x in view.model._full_df["数量"].iloc[:3]]
    assert full_real == [3, 2, 1], f"_full_df 未同步: {full_real}"


def test_sort_mixed_types_does_not_raise(view):
    view.model.set_full_dataframe(pd.DataFrame({"混": [1, "文字", 3]}))
    view.sort_by_column(0, ascending=True)      # 不应抛异常
    assert view.model._real_rows == 3


def test_sort_undo_restores_order(view):
    before = _col(view)
    view.sort_by_column(1, ascending=False)
    assert _col(view) != before
    view.undo()
    assert _col(view) == before, "撤销没有恢复排序前的顺序"
