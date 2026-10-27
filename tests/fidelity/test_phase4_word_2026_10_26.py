# tests/fidelity/test_phase4_word_2026_10_26.py
"""阶段 4：蜜写 WPS 式三页 Ribbon，旧模式栏/快速栏收进标签页。"""

def test_word_phase4_tabs_and_embedded_rows(qtbot, beewrite_editor):
    editor = beewrite_editor
    ribbon = editor._ribbon
    assert ribbon.tab_names() == ["文件", "开始", "插入", "页面", "引用", "审阅", "视图"]
    # 旧的外置模式栏/快速栏不再是主布局的直接子布局
    direct = [
        editor.layout().itemAt(i).layout()
        for i in range(editor.layout().count())
        if editor.layout().itemAt(i).layout() is not None
    ]
    assert editor._mode_toolbar not in direct
    assert editor._quick_toolbar not in direct
    # 三块内容都在 Ribbon 内
    assert ribbon.isAncestorOf(editor._toolbar1)
    assert ribbon.isAncestorOf(editor._toolbar2)
    page1 = ribbon._stack.widget(1)
    assert page1.isAncestorOf(editor._toolbar1)


def test_word_phase4_rich_mode_shows_formatting(qtbot, beewrite_editor):
    editor = beewrite_editor
    editor._rich_btn.click()
    qtbot.wait(30)
    # fixture 未 show 窗口，isVisible 恒为 False；用 hidden 状态判断模式切换
    assert not editor._toolbar1.isHidden()
    assert editor._ribbon.tab_names()[1] == "开始"
    editor._md_btn.click()
