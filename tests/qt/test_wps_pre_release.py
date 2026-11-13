"""v5.4.7 发布前校验：WPS Ribbon 重构后关键控件仍在。"""
from beeoffice.plugins.beewrite import BeeWriteEditor
from beeoffice.plugins.beeshow import BeeShowView


def test_beewrite_start_controls_visible(qtbot):
    w = BeeWriteEditor()
    qtbot.addWidget(w)
    w.resize(1200, 600)
    w.show()
    qtbot.wait(30)
    w._ribbon.set_current_tab(1)  # 开始
    qtbot.wait(30)
    for name in ("_font_combo", "_size_combo", "_head_combo"):
        widget = getattr(w, name)
        assert widget.isVisible(), name
        assert widget.width() > 10
    w.close()


def test_beeshow_start_controls_visible(qtbot):
    s = BeeShowView()
    qtbot.addWidget(s)
    s.resize(1200, 600)
    s.show()
    qtbot.wait(30)
    s._ribbon.set_current_tab(1)  # 开始
    qtbot.wait(30)
    assert s._theme_combo.isVisible()
    assert s._theme_combo.width() > 10
    assert s._play_btn.isVisible()
    s.close()
