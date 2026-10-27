# tests/fidelity/test_theme_phase3_2026_10_26.py
"""阶段 3：控件样式 token 化 + 深色清理。"""
from beeoffice.theme import Theme


def test_theme_tokens_expose_dark_and_light():
    Theme.set_theme("light")
    light = Theme.tokens()
    assert light["surface"] == "#FFFFFF"
    assert light["text"] == "#333333"
    assert light["is_dark"] is False

    Theme.set_theme("dark")
    dark = Theme.tokens()
    assert dark["surface"] == "#252525"
    assert dark["text"] == "#DDDDDD"
    assert dark["is_dark"] is True
    Theme.set_theme("light")


def test_button_qss_uses_theme_tokens():
    Theme.set_theme("light")
    light_qss = Theme.button_qss()
    assert "#EEE" not in light_qss
    assert Theme.tokens()["surface_alt"] in light_qss

    Theme.set_theme("dark")
    dark_qss = Theme.button_qss()
    assert Theme.tokens()["surface_alt"] in dark_qss
    assert "#DDDDDD" in dark_qss
    Theme.set_theme("light")


def test_toolbar_qss_follows_theme():
    Theme.set_theme("dark")
    assert "#2D2D2D" in Theme.toolbar_qss()
    Theme.set_theme("light")
    assert "#FFFFFF" in Theme.toolbar_qss()


def test_sheet_and_word_refresh_on_theme_switch(qtbot, beewrite_editor):
    from beeoffice.plugins.beesheet import BeeSheetView

    view = BeeSheetView()
    qtbot.addWidget(view)
    Theme.set_theme("dark")
    view.apply_theme()
    assert "#252525" in view._name_box.styleSheet()

    editor = beewrite_editor
    Theme.set_theme("light")
    editor.apply_theme()
    assert "#FFFFFF" in editor._toolbar1.styleSheet()
    Theme.set_theme("light")


def test_ribbon_icons_available(qapp):
    from beeoffice.plugins.ribbon_icons import make_icon
    for name in ("save", "print", "export", "undo", "redo", "play", "table",
                 "image", "link", "toc", "comment", "track", "search", "view",
                 "page", "formula", "data", "insert"):
        assert not make_icon(name).isNull(), name
