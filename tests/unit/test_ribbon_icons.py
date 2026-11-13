"""自定义 SVG 图标集测试。"""
from beeoffice.ribbon_icons import _ICONS, ribbon_icon


def test_all_icons_render(qapp):
    assert len(_ICONS) >= 25
    for name in _ICONS:
        icon = ribbon_icon(name)
        assert not icon.isNull(), name
        pixmap = icon.pixmap(24, 24)
        assert pixmap.hasAlphaChannel(), name


def test_unknown_icon_empty(qapp):
    assert ribbon_icon("not-a-real-icon").isNull()
