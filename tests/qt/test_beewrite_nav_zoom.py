"""S4：蜜写统一导航、页数状态与缩放。"""


def _seed(editor):
    editor.set_content("# 一级标题\n\n正文\n\n## 二级标题\n\n内容\n\n### 三级标题\n\n更多")


def test_navigation_tabs_and_chapters(beewrite_editor):
    ed = beewrite_editor
    _seed(ed)
    ed._toggle_outline()
    nav = ed._outline_panel
    assert not nav.isHidden()
    assert nav.tabs.count() == 4
    assert nav.tabs.tabText(0) == "目录"
    assert nav.chapter_list.count() >= 3


def test_bookmark_tab_refresh(beewrite_editor):
    ed = beewrite_editor
    ed._bookmark_manager.add("测试书签", 0, 0)
    ed._toggle_outline()
    assert ed._outline_panel.bookmark_list.count() == 1


def test_find_bar_in_navigation_panel(beewrite_editor):
    ed = beewrite_editor
    _seed(ed)
    ed._find_current()
    assert not ed._outline_panel.isHidden()
    assert ed._outline_panel.tabs.currentIndex() == 3
    assert not ed.find_bar.isHidden()


def test_page_count_status(beewrite_editor):
    ed = beewrite_editor
    _seed(ed)
    ed._update_status_bar()
    assert "页数：" in ed._page_count_label.text()
    assert ed._estimate_page_count() >= 1


def test_zoom_controls(beewrite_editor):
    ed = beewrite_editor
    _seed(ed)
    assert ed._zoom_percent == 100
    ed._zoom_in()
    assert ed._zoom_percent == 110
    assert ed._zoom_label.text() == "110%"
    ed._zoom_out()
    ed._zoom_out()
    assert ed._zoom_percent == 90
    ed._zoom_reset()
    assert ed._zoom_percent == 100


def test_page_view_dialog(beewrite_editor):
    ed = beewrite_editor
    _seed(ed)
    ed._header_text = "测试页眉"
    ed._footer_text = "测试页脚"
    dlg = ed._open_page_view()
    assert dlg is not None
    assert dlg._view.pages >= 1
    assert "共" in dlg._page_label.text()
    assert dlg._view._header == "测试页眉"
    assert dlg._view._footer == "测试页脚"
    dlg._set_zoom(150)
    assert dlg._zoom_label.text() == "150%"
    dlg.close()


def test_page_view_click_position_and_live_settings(beewrite_editor):
    from PySide6.QtCore import QPointF

    ed = beewrite_editor
    _seed(ed)
    dlg = ed._open_page_view()
    view = dlg._view
    pos = view._position_at(QPointF(
        view._gap + view._margin_l + 20,
        view._gap + view._margin_t + 20,
    ))
    assert pos is not None and pos >= 0

    # 页面设置变化后由 provider 轮询刷新
    ed._page_settings["margin_left"] = 2.0
    dlg._poll_settings()
    assert dlg._view._settings["margin_left"] == 2.0
    dlg.close()
