# tests/fidelity/test_ribbon_ui_2026_10_23.py
"""WPS 式 Ribbon 标签栏：蜜算平铺工具栏收进标签页。"""
from PySide6.QtWidgets import QFrame, QTabBar

from beeoffice.plugins.beesheet import BeeSheetView
from beeoffice.plugins.ribbon_widget import RibbonBar


def test_sheet_has_wps_ribbon_tabs(qtbot):
    view = BeeSheetView()
    qtbot.addWidget(view)
    view.resize(1000, 700)
    view.show()
    ribbon = view._ribbon
    assert isinstance(ribbon, RibbonBar)
    assert [t for t in ribbon.tab_names() if t != "表格工具"] == ["文件", "开始", "插入", "数据", "公式", "视图"]
    assert view.findChild(QTabBar) is not None


def test_ribbon_switches_visible_rows(qtbot):
    view = BeeSheetView()
    qtbot.addWidget(view)
    view.resize(1000, 700)
    view.show()
    ribbon = view._ribbon
    # 新增“文件”页后，开始页是索引 1；视图页是索引 5
    ribbon.set_current_tab(1)          # 开始
    qtbot.wait(30)
    assert view._print_btn.isVisibleTo(view)
    assert not view._freeze_btn.isVisibleTo(view)
    ribbon.set_current_tab(5)          # 视图
    qtbot.wait(30)
    assert view._freeze_btn.isVisibleTo(view)
    assert not view._print_btn.isVisibleTo(view)
    ribbon.set_current_tab(1)
    qtbot.wait(30)
    assert view._print_btn.isVisibleTo(view)


def test_word_has_wps_ribbon_tabs(beewrite_editor, qtbot):
    editor = beewrite_editor
    qtbot.addWidget(editor)
    editor.resize(1000, 700)
    editor.show()
    qtbot.waitExposed(editor)
    ribbon = editor._ribbon
    assert isinstance(ribbon, RibbonBar)
    assert [t for t in ribbon.tab_names() if t != "表格工具"] == ["文件", "开始", "插入", "页面", "引用", "审阅", "视图"]
    # 工具栏已被收进对应 Ribbon 页的分组框（结构断言，避免 offscreen 可见性抖动）
    page1 = ribbon._stack.widget(1)
    page2 = ribbon._stack.widget(2)
    assert page1.isAncestorOf(editor._toolbar1)
    assert page2.isAncestorOf(editor._toolbar2)
    ribbon.set_current_tab(2)
    qtbot.wait(30)
    assert ribbon.current_index() == 2
    assert ribbon._stack.currentWidget() is page2


def test_ribbon_groups_have_titles(qtbot):
    view = BeeSheetView()
    qtbot.addWidget(view)
    view.resize(1000, 700)
    view.show()
    groups = view._ribbon.findChildren(QFrame, "RibbonGroup")
    titles = [g._title.text() for g in groups]
    assert "📄 文件" in titles and "🖋 格式" in titles


def test_quick_access_bar(qtbot):
    view = BeeSheetView()
    qtbot.addWidget(view)
    rib = view._ribbon
    buttons = [rib._quick_layout.itemAt(i).widget() for i in range(rib._quick_layout.count())]
    buttons = [b for b in buttons if b is not None]
    assert len(buttons) == 3
    tips = [b.toolTip() for b in buttons]
    assert any("保存" in x for x in tips)
    assert any("撤销" in x for x in tips)
    assert any("重做" in x for x in tips)


def test_large_button_callback(qtbot):
    from beeoffice.plugins.ribbon_widget import RibbonBar
    clicks = []
    rib = RibbonBar()
    page = rib.add_tab("放映")
    group = rib.add_group(page, "控制")
    btn = group.add_large_button("▶\n播放", "播放", lambda: clicks.append(1))
    btn.click()
    assert clicks == [1]


def test_ribbon_does_not_absorb_vertical_space(qtbot):
    """全屏时 Ribbon 只能占内容高度，不能把菜单与表格之间拉出大块空白。"""
    view = BeeSheetView()
    qtbot.addWidget(view)
    view.resize(1600, 900)
    view.show()
    qtbot.wait(50)
    ribbon = view._ribbon
    assert ribbon.height() <= ribbon.sizeHint().height() + 12
    assert view.table_view.geometry().top() < 260
