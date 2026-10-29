"""S2 蜜演母版设置。"""
from types import SimpleNamespace

from beeoffice.plugins.beeshow_master_dialog import BeeShowMasterDialog, build_master_css


def test_build_master_css():
    css = build_master_css("Microsoft YaHei", 28, "#FF8800", "页脚")
    assert "Microsoft YaHei" in css
    assert "28px" in css
    assert "#FF8800" in css
    assert "页脚" in css


def test_dialog_apply(qtbot):
    calls = []
    class Combo:
        def setCurrentText(self, text):
            calls.append(text)
    view = SimpleNamespace(
        _current_theme="", _theme_combo=Combo(), _current_slide=0,
        _show_layout_picker=lambda: None,
        _set_status=lambda *a: None,
        _show_slide=lambda i: None,
    )
    dlg = BeeShowMasterDialog(view)
    qtbot.addWidget(dlg)
    dlg.footer_edit.setText("测试页脚")
    dlg._apply()
    assert "测试页脚" in view._master_css
