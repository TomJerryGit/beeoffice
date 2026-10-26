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
    assert ribbon.tab_names() == ["开始", "插入", "数据", "视图"]
    assert view.findChild(QTabBar) is not None


def test_ribbon_switches_visible_rows(qtbot):
    view = BeeSheetView()
    qtbot.addWidget(view)
    view.resize(1000, 700)
    view.show()
    ribbon = view._ribbon
    # 默认“开始”：文件/字体控件可见，冻结按钮隐藏
    assert view._print_btn.isVisibleTo(view)
    assert not view._freeze_btn.isVisibleTo(view)
    ribbon.set_current_tab(3)          # 视图
    qtbot.wait(30)
    assert view._freeze_btn.isVisibleTo(view)
    assert not view._print_btn.isVisibleTo(view)
    ribbon.set_current_tab(0)
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
    assert ribbon.tab_names() == ["开始", "插入", "页面"]
    # 工具栏已被收进对应 Ribbon 页的分组框（结构断言，避免 offscreen 可见性抖动）
    page0 = ribbon._stack.widget(0)
    page1 = ribbon._stack.widget(1)
    assert page0.isAncestorOf(editor._toolbar1)
    assert page1.isAncestorOf(editor._toolbar2)
    ribbon.set_current_tab(1)
    qtbot.wait(30)
    assert ribbon.current_index() == 1
    assert ribbon._stack.currentWidget() is page1


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
