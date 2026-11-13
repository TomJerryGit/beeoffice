"""BeeSheet 分类功能区（WPS 风格 Ribbon）测试。"""
import pandas as pd
from PySide6.QtWidgets import QAbstractButton
from beeoffice.plugins.beesheet_ui_mixin import RibbonGroup

from beeoffice.plugins.beesheet import BeeSheetView


def make_sheet(qtbot):
    v = BeeSheetView()
    qtbot.addWidget(v)
    v.model.set_full_dataframe(pd.DataFrame({"A": [1, 2], "B": ["x", "y"]}))
    v.table_view.setModel(v.model)
    return v


def test_ribbon_categories(qtbot):
    sheet = make_sheet(qtbot)
    tabs = sheet._ribbon_tabs
    assert tabs.count() == 6
    names = [tabs.tabText(i) for i in range(tabs.count())]
    assert names == ["开始", "插入", "数据", "公式", "视图", "表格工具"]
    assert tabs.isTabVisible(5) is False

    for i in range(5):
        tabs.setCurrentIndex(i)
        assert sheet._ribbon_stack.currentIndex() == i


def test_ribbon_groups(qtbot):
    sheet = make_sheet(qtbot)
    titles = {g.title.text() for g in sheet._ribbon.findChildren(RibbonGroup)}
    assert {"剪贴板", "字体", "对齐", "数字格式"} <= titles
    assert {"对象", "数据工具"} <= titles
    assert {"排序和筛选"} <= titles
    assert {"函数", "名称与审计"} <= titles
    assert {"冻结窗格", "显示"} <= titles


def test_ribbon_toggle(qtbot):
    sheet = make_sheet(qtbot)
    class Btn:
        def setText(self, text): self.text = text
    btn = Btn()
    assert sheet._ribbon.isHidden() is False
    sheet._toggle_toolbars(btn)
    assert sheet._ribbon.isHidden() is True
    assert "展开" in btn.text
    sheet._toggle_toolbars(btn)
    assert sheet._ribbon.isHidden() is False
    assert "隐藏" in btn.text


def test_ribbon_actions_exist(qtbot):
    sheet = make_sheet(qtbot)
    labels = {b.text() for b in sheet._ribbon.findChildren(QAbstractButton)}
    for required in ("粘贴", "查找替换", "自动求和", "图表",
                     "透视表", "批注", "排序", "筛选",
                     "清洗", "插入函数", "冻结", "样式"):
        assert required in labels


def test_contextual_table_tab(qtbot):
    sheet = make_sheet(qtbot)
    tabs = sheet._ribbon_tabs
    assert tabs.isTabVisible(5) is False
    sheet.table_view.selectAll()
    qtbot.wait(10)
    assert tabs.isTabVisible(5) is True
    sheet.table_view.clearSelection()
    qtbot.wait(10)
    assert tabs.isTabVisible(5) is False


def test_compact_on_narrow_window(qtbot):
    sheet = make_sheet(qtbot)
    sheet.resize(1200, 500)
    sheet.show()
    qtbot.wait(20)
    groups = sheet._ribbon.findChildren(RibbonGroup)
    assert groups
    assert all(not g.title.isHidden() for g in groups)
    sheet.resize(1000, 500)
    qtbot.wait(20)
    assert all(g.title.isHidden() for g in groups)
    assert sheet.width() < 1100
    assert sheet._ribbon.height() == 96
    from PySide6.QtCore import Qt
    assert all(
        b.toolButtonStyle() == Qt.ToolButtonIconOnly
        for b in sheet._ribbon_buttons if not b.icon().isNull()
    )


def test_border_fill_formats(qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor
    sheet = make_sheet(qtbot)
    sheet.table_view.selectAll()
    qtbot.wait(10)
    sheet._apply_cell_fill(QColor("#E3F2FD"))
    sheet._apply_cell_border(QColor("#1565C0"), 2)
    sheet._apply_cell_border(QColor("#1565C0"), 1, ("top",))
    fmt = sheet._cell_formats[(0, 0)]
    assert fmt["bg"].name() == "#e3f2fd"
    assert fmt["border"].name() == "#1565c0"
    assert fmt["border_width"] == 1
    assert fmt["border_sides"] == ("top",)
    assert sheet.model.data(sheet.model.index(0, 0), Qt.BackgroundRole).name() == "#e3f2fd"
    sheet._clear_cell_fill_border()
    assert "bg" not in sheet._cell_formats[(0, 0)]
