# tests/fidelity/test_phase4_shell_2026_10_27.py
"""阶段 4 剩余：WPS 顶栏入口、折叠按钮、上下文标签基础能力。"""
from beeoffice.plugins.ribbon_widget import RibbonBar


def test_ribbon_collapse_toggle(qtbot):
    rib = RibbonBar()
    qtbot.addWidget(rib)
    page = rib.add_tab("开始")
    group = rib.add_group(page, "测试")
    rib.show()
    assert rib._stack.isVisible()
    rib.toggle_collapse()
    assert not rib._stack.isVisible()
    rib.toggle_collapse()
    assert rib._stack.isVisible()


def test_context_tab_hidden_and_shown(qtbot):
    rib = RibbonBar()
    qtbot.addWidget(rib)
    rib.add_tab("开始")
    rib.add_context_tab("表格工具")
    rib.show()
    assert "表格工具" in rib.tab_names()
    assert not rib._tabs.isTabVisible(1)
    rib.set_context_tab_visible("表格工具", True)
    assert rib._tabs.isTabVisible(1)
    rib.set_context_tab_visible("表格工具", False)
    assert not rib._tabs.isTabVisible(1)


def test_file_menu_attach(qtbot):
    from PySide6.QtWidgets import QMenu

    rib = RibbonBar()
    qtbot.addWidget(rib)
    menu = QMenu()
    rib.attach_file_menu(menu)
    assert rib._file_button is not None
    assert rib._file_button.menu() is menu


def test_app_wps_shell_hides_menubar_for_ribbon_page(app, qtbot):
    from beeoffice.plugins.beewrite import BeeWriteEditor

    app.resize(1200, 800)
    editor = BeeWriteEditor()
    idx = app.tab_manager.addTab(editor, "WPS测试")
    app.tab_manager.setCurrentWidget(editor)
    app._sync_wps_shell()
    assert app.menuBar().maximumHeight() == 0
    ribbon = editor._ribbon
    assert ribbon._file_button is not None
    assert ribbon._file_button.menu() is not None
