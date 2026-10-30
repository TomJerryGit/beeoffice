"""蜜演动画面板核心：标记/顺序 CSS/注入。"""
from beeoffice.plugins.beeshow_animation import (
    AnimationEntry,
    animation_marker,
    build_animation_css,
    build_transition_css,
    config_dict,
    inject_markers,
    parse_animation,
)
from beeoffice.plugins.beeshow_animation_panel import AnimationPanelDialog


def test_marker_roundtrip():
    cfg = config_dict("fade", [AnimationEntry(".card", "fade_in", 400, 50)])
    marker = animation_marker(cfg)
    parsed, cleaned = parse_animation(f"<p>x</p>{marker}")
    assert parsed["transition"] == "fade"
    assert parsed["entries"][0]["selector"] == ".card"
    assert marker not in cleaned


def test_animation_css_sequential_delay():
    cfg = config_dict("none", [
        AnimationEntry("h1", "fade_in", 500, 0),
        AnimationEntry(".card", "pulse", 300, 100),
    ])
    css = build_animation_css(cfg)
    assert "h1{" in css and "500ms" in css
    assert ".card{" in css and "600ms" in css  # 第一段 500 + delay 100


def test_transition_css():
    assert "bee_t_fade" in build_transition_css("fade")
    assert build_transition_css("none") == ""


def test_inject_markers():
    text = "# 第一页\n\n---\n\n# 第二页"
    cfg = config_dict("none", [AnimationEntry("h1", "fade_in", 300, 0)])
    out = inject_markers(text, [cfg, None])
    assert "beeoffice-anim" in out
    assert out.count("beeoffice-anim") == 1


def test_panel_defaults(qtbot):
    dlg = AnimationPanelDialog()
    qtbot.addWidget(dlg)
    dlg._add_row()
    dlg._accept()
    cfg = dlg.get_config()
    assert len(cfg["entries"]) == 1
    assert cfg["entries"][0]["selector"] == "h1"
