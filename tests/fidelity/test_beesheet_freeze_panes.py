# tests/fidelity/test_beesheet_freeze_panes.py
"""
蜜算 WPS 式冻结窗格回归（2026-10-22，路线图 4.1）。

修的是"假冻结"：以前只保留文件里的 freeze_panes 状态、界面禁用，
滚动时表头并不会固定。现在用顶部/左侧/交叉角三个叠加 QTableView 实现
真冻结，并与主表的横向/纵向滚动、列宽/行高同步；选中/编辑仍落同一个 model。

测试点：
1. 解析 A1/A2/B1/B2/C3；
2. 冻结首行/首列/行列 → 叠加视图可见、`_freeze_panes` 正确；
3. 取消冻结 → 全部隐藏、状态清空；
4. 保存 xlsx 后 freeze_panes 写回；
5. 从文件状态恢复；
6. 滚动同步不抛异常。
"""
import pandas as pd
from openpyxl import load_workbook

from beeoffice.plugins.beesheet import BeeSheetView


def _view(qtbot):
    view = BeeSheetView()
    qtbot.addWidget(view)
    view.resize(900, 600)
    view.model.set_full_dataframe(
        pd.DataFrame({
            "姓名": [f"第{i}人" for i in range(10)],
            "分数": list(range(10)),
            "备注": [f"r{i}" for i in range(10)],
        })
    )
    view.show()
    qtbot.waitExposed(view)
    return view


def test_parse_freeze_ref(qtbot):
    view = _view(qtbot)
    assert view._parse_freeze_ref("A1") == (0, 0)
    assert view._parse_freeze_ref("A2") == (1, 0)
    assert view._parse_freeze_ref("B1") == (0, 1)
    assert view._parse_freeze_ref("B2") == (1, 1)
    assert view._parse_freeze_ref("C3") == (2, 2)
    assert view._freeze_ref_for(1, 0) == "A2"
    assert view._freeze_ref_for(0, 1) == "B1"
    assert view._freeze_ref_for(1, 1) == "B2"
    assert view._freeze_ref_for(0, 0) is None


def test_freeze_first_row(qtbot):
    view = _view(qtbot)
    view._freeze_first_row()
    assert view._freeze_panes == "A2"
    assert (view._frozen_top, view._frozen_left) == (1, 0)
    assert view._frozen_top_view.isVisible()
    assert view._frozen_top_view.height() > 0
    assert view._frozen_top_view.width() > 0
    assert not view._frozen_left_view.isVisible()


def test_freeze_first_col(qtbot):
    view = _view(qtbot)
    view._freeze_first_col()
    assert view._freeze_panes == "B1"
    assert view._frozen_left_view.isVisible()
    assert view._frozen_left_view.width() > 0
    assert not view._frozen_top_view.isVisible()


def test_freeze_first_row_and_col(qtbot):
    view = _view(qtbot)
    view._freeze_first_row_col()
    assert view._freeze_panes == "B2"
    assert view._frozen_top_view.isVisible()
    assert view._frozen_left_view.isVisible()
    assert view._frozen_corner_view.isVisible()


def test_unfreeze_hides_overlays(qtbot):
    view = _view(qtbot)
    view._freeze_first_row_col()
    view._unfreeze_panes()
    assert view._freeze_panes is None
    assert not view._frozen_top_view.isVisible()
    assert not view._frozen_left_view.isVisible()
    assert not view._frozen_corner_view.isVisible()


def test_freeze_is_saved_to_xlsx(qtbot, tmp_path):
    view = _view(qtbot)
    view._freeze_first_row_col()
    path = tmp_path / "frozen.xlsx"
    assert view._write_xlsx(str(path)) is True
    wb = load_workbook(path)
    assert wb.active.freeze_panes == "B2"


def test_apply_from_persisted_state(qtbot):
    view = _view(qtbot)
    view._freeze_panes = "C3"
    view._apply_freeze_from_state()
    assert (view._frozen_top, view._frozen_left) == (2, 2)
    assert view._frozen_top_view.isVisible()
    assert view._frozen_left_view.isVisible()


def test_scroll_sync_does_not_raise(qtbot):
    view = _view(qtbot)
    view.model.set_full_dataframe(
        pd.DataFrame({f"c{i}": list(range(30)) for i in range(8)})
    )
    view.resize(220, 220)          # 缩小视口，让横/纵滚动条都有可滚动范围
    qtbot.wait(100)
    view._freeze_first_row_col()
    hbar = view.table_view.horizontalScrollBar()
    vbar = view.table_view.verticalScrollBar()
    hvalue = min(1, hbar.maximum())
    vvalue = min(1, vbar.maximum())
    hbar.setValue(hvalue)
    vbar.setValue(vvalue)
    top_bar = view._frozen_top_view.horizontalScrollBar()
    left_bar = view._frozen_left_view.verticalScrollBar()
    assert top_bar.value() == hvalue
    # 左侧冻结列视图纵向偏移 = 主表滚动值 + 冻结首行数（受自身滚动范围裁剪）
    expected = max(0, min(left_bar.maximum(), vvalue + view._frozen_top))
    assert left_bar.value() == expected
