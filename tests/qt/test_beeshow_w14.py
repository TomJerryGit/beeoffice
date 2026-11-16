"""Wave 4 W14：BeeShow 设计/统一字体/过渡应用。"""
from beeoffice.plugins.beeshow import BeeShowView
from beeoffice.plugins.beeshow_animation import TRANSITIONS, build_transition_css


def make_show(qtbot):
    s = BeeShowView()
    qtbot.addWidget(s)
    s.show()
    return s


def test_design_tab_exists(qtbot):
    s = make_show(qtbot)
    names = s._ribbon.tab_names()
    assert "设计" in names


def test_unified_font(qtbot):
    s = make_show(qtbot)
    s._apply_unified_font("SimSun")
    assert "SimSun" in s._font_css


def test_apply_transition_all(qtbot):
    s = make_show(qtbot)
    s._apply_transition_all("fade")
    assert len(s._slide_animations) == len(s._slides_html)
    assert all(cfg.get("transition") == "fade" for cfg in s._slide_animations)


def test_transition_css_retention():
    css = build_transition_css("fade")
    assert "animation" in css or "transition" in css
    assert "fade" in TRANSITIONS
