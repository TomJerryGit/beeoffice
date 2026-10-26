# tests/fidelity/test_theme_phase2_2026_10_26.py
"""阶段 2 主题系统：浅色/深色 + 强调色、全局应用、持久化、Ribbon 跟随。"""

def test_theme_tokens_light_dark(qapp):
    from beeoffice.theme import Theme

    Theme.set_theme("light")
    light = Theme.get_stylesheet()
    assert Theme.is_dark() is False
    assert "#F5F5F5" in light or "#FAFAFA" in light

    Theme.set_theme("dark")
    dark = Theme.get_stylesheet()
    assert Theme.is_dark() is True
    assert "#1E1E1E" in dark and "#2D2D2D" in dark
    Theme.set_theme("light")


def test_app_persists_theme_and_accent(app):
    app._set_theme("dark")
    assert app.settings.theme == "dark"
    assert "dark" or True  # 由 Theme 单例断言
    from beeoffice.theme import Theme
    assert Theme.is_dark() is True

    app._set_accent("ocean")
    assert app.settings.accent_color == "ocean"
    assert Theme.get_accent_color("primary").upper() == "#2196F3"

    app._set_theme("light")
    app._set_accent("amber")
    assert app.settings.theme == "light"
    assert app.settings.accent_color == "amber"


def test_view_menu_has_theme_and_accent(app):
    texts = []
    for action in app.menuBar().actions():
        menu = action.menu()
        if menu is not None:
            texts.extend(a.text() for a in menu.actions())
    assert "🎨 主题" in texts
    assert "🎨 强调色" in texts


def test_ribbon_follows_dark_theme(qtbot):
    from beeoffice.theme import Theme
    from beeoffice.plugins.beesheet import BeeSheetView

    Theme.set_theme("dark")
    view = BeeSheetView()
    qtbot.addWidget(view)
    css = view._ribbon._tabs.styleSheet()
    assert "#2D2D2D" in css or "#333" in css
    Theme.set_theme("light")
