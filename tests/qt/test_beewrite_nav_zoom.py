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
