"""S4 UI：快捷键覆盖与按钮可访问名称回归。"""
from PySide6.QtWidgets import QWidget


def _menu_actions(window):
    result = []

    def walk(menu):
        for action in menu.actions():
            if action.isSeparator():
                continue
            result.append(action)
            if action.menu():
                walk(action.menu())

    walk(window.menuBar())
    return result


def test_high_frequency_shortcuts(app):
    actions = _menu_actions(app)
    by_shortcut = {}
    for action in actions:
        key = action.shortcut().toString()
        if key:
            by_shortcut.setdefault(key, []).append(action.text().replace("&", ""))

    expected = {
        "Ctrl+Alt+D": "导出 DOCX",
        "Ctrl+Alt+F": "导出 PDF",
        "Ctrl+Alt+X": "导出 PPTX",
        "Ctrl+Alt+T": "保存为模板",
        "Ctrl+Alt+A": "PDF 批注",
        "Ctrl+Alt+G": "页面工具",
        "Ctrl+Alt+K": "宏控制台",
        "Ctrl+Alt+U": "检查更新",
    }
    for key, label in expected.items():
        assert key in by_shortcut, f"缺少快捷键 {key}"
        assert any(label in name for name in by_shortcut[key]), by_shortcut[key]

    duplicates = {k: v for k, v in by_shortcut.items() if len(v) > 1}
    assert not duplicates, f"快捷键冲突：{duplicates}"


def test_ribbon_buttons_have_accessible_names(qtbot):
    from beeoffice.plugins.ribbon_widget import RibbonBar, RibbonGroup

    host = QWidget()
    qtbot.addWidget(host)
    group = RibbonGroup("开始", host)
    large = group.add_large_button("📄\n保存", "保存文档", lambda: None)
    small = group.add_small_button("复制", "复制内容", lambda: None)
    bar = RibbonBar(host)
    quick = bar.add_quick_action("💾", "保存", lambda: None, icon_name="save")

    for button in (large, small, quick, bar._collapse_button):
        assert button.accessibleName(), f"{button} 缺少 accessibleName"
