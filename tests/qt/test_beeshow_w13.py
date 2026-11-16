"""Wave 4 W13：BeeShow 幻灯片复制/隐藏/管理。"""
from beeoffice.plugins.beeshow import BeeShowView


def make_show(qtbot):
    s = BeeShowView()
    qtbot.addWidget(s)
    s.show()
    return s


def test_duplicate_slide(qtbot):
    s = make_show(qtbot)
    before = len(s._slides_md)
    s._duplicate_slide()
    assert len(s._slides_md) == before + 1
    assert s._current_slide == 1


def test_hide_slide(qtbot):
    s = make_show(qtbot)
    s._toggle_hide_slide()
    assert s._current_slide in s._slide_hidden
    assert "[隐藏]" in s._thumb_list.item(s._current_slide).text()
    s._toggle_hide_slide()
    assert s._current_slide not in s._slide_hidden


def test_slide_panel_has_actions(qtbot):
    s = make_show(qtbot)
    assert hasattr(s, "_add_slide")
    assert hasattr(s, "_delete_slide")
    assert hasattr(s, "_duplicate_slide")
    assert hasattr(s, "_toggle_hide_slide")
    assert hasattr(s, "_show_layout_picker")
