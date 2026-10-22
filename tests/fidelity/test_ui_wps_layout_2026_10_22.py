# tests/fidelity/test_ui_wps_layout_2026_10_22.py
"""
WPS 式 UI/版式提升回归（2026-10-22，第 2 批）：

1. **蜜算工作表页签**：底部 QTabBar 显示工作簿全部工作表；切换/新建/重命名/删除
   都要同步 `_workbook` 与当前模型（WPS 底部 sheet 页签的等价物）。
2. **WPS 式表头**：列字母 A/B/C + 列名（如 `A  订单编号`），可切回仅列名。
3. **蜜写页面视图**：页面视图/打印预览按 `_page_settings` 的纸张/方向/页边距
   构造 QPrinter（原先写死 A4）。
"""
import pandas as pd
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPageLayout, QPageSize

from beeoffice.plugins.beesheet import BeeSheetView
from beeoffice.plugins.beesheet_workbook import SheetData, WorkbookData


def _workbook_two_sheets():
    return WorkbookData(
        sheets=[
            SheetData(name="订单", df=pd.DataFrame({"编号": [1, 2]})),
            SheetData(name="客户", df=pd.DataFrame({"客户": ["甲", "乙", "丙"]})),
        ],
        active="订单",
    )


# ==================== 1. 工作表页签 ====================

def test_sheet_tabs_show_all_worksheets(qtbot):
    view = BeeSheetView()
    qtbot.addWidget(view)
    view._workbook = _workbook_two_sheets()
    view._active_sheet_name = "订单"
    view._refresh_sheet_tabs()

    bar = view._sheet_tab_bar
    assert bar.count() == 2
    assert [bar.tabText(i) for i in range(bar.count())] == ["订单", "客户"]
    assert not view._sheet_tabs_container.isHidden()


def test_switch_sheet_loads_target_dataframe(qtbot, monkeypatch):
    view = BeeSheetView()
    qtbot.addWidget(view)
    view._workbook = _workbook_two_sheets()
    view._active_sheet_name = "订单"
    view._refresh_sheet_tabs()
    monkeypatch.setattr(view, "_load_view_styles_from", lambda *a, **k: None)

    view._on_sheet_tab_changed(1)

    assert view._active_sheet_name == "客户"
    assert view.model.get_value(0, 0) == "甲"
    assert list(view.model.df.columns) == ["客户"]


def test_add_rename_delete_sheets(qtbot, monkeypatch):
    view = BeeSheetView()
    qtbot.addWidget(view)
    view._workbook = _workbook_two_sheets()
    view._active_sheet_name = "订单"
    view._refresh_sheet_tabs()

    view._add_workbook_sheet()
    assert len(view._workbook.sheets) == 3

    monkeypatch.setattr(
        "PySide6.QtWidgets.QInputDialog.getText",
        staticmethod(lambda *a, **k: ("新客户表", True)),
    )
    view._rename_workbook_sheet(1)
    assert view._workbook.sheets[1].name == "新客户表"

    view._delete_workbook_sheet(2)
    assert len(view._workbook.sheets) == 2


# ==================== 2. WPS 式表头 ====================

def test_wps_headers_show_column_letters(qtbot):
    view = BeeSheetView()
    qtbot.addWidget(view)
    view.model.set_full_dataframe(pd.DataFrame({"编号": [1], "金额": [2.0]}))
    assert view.model.wps_headers is True
    h0 = view.model.headerData(0, Qt.Horizontal, Qt.DisplayRole)
    assert h0.startswith("A")
    assert "编号" in h0
    h1 = view.model.headerData(1, Qt.Horizontal, Qt.DisplayRole)
    assert h1.startswith("B")

    view.model.wps_headers = False
    assert view.model.headerData(0, Qt.Horizontal, Qt.DisplayRole) == "编号"


# ==================== 3. 蜜写页面视图 ====================

def test_page_printer_uses_page_settings(beewrite_editor):
    editor = beewrite_editor
    editor._page_settings.update({
        "paper": "A3",
        "orientation": "landscape",
        "margin_top": 20,
        "margin_bottom": 25,
        "margin_left": 30,
        "margin_right": 35,
    })
    printer = editor._build_page_printer()
    layout = printer.pageLayout()
    assert layout.pageSize().id() == QPageSize.A3
    assert layout.orientation() == QPageLayout.Landscape
    margins_mm = layout.margins(QPageLayout.Millimeter)
    assert abs(margins_mm.left() - 30) < 0.6
    assert abs(margins_mm.right() - 35) < 0.6


# ==================== 4. 真实打开多工作表文件 ====================

def test_open_multisheet_workbook_shows_tabs_and_switches(
    app, qtbot, tmp_path, monkeypatch
):
    import pandas as pd
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    path = tmp_path / "multi.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"编号": [1, 2]}).to_excel(
            writer, sheet_name="订单", index=False
        )
        pd.DataFrame({"客户": ["A", "B", "C"]}).to_excel(
            writer, sheet_name="客户", index=False
        )
    app._open_sheet_file(str(path))
    view = app.tab_manager.currentWidget()
    qtbot.waitUntil(
        lambda: hasattr(view, "_sheet_tab_bar") and view._sheet_tab_bar.count() == 2,
        timeout=5000,
    )
    assert [view._sheet_tab_bar.tabText(i) for i in range(2)] == ["订单", "客户"]
    view._sheet_tab_bar.setCurrentIndex(1)
    qtbot.waitUntil(lambda: view._active_sheet_name == "客户", timeout=5000)
    assert view.model.get_value(0, 0) == "A"
