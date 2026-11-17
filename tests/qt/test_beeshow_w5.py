"""Wave5 W5：PPT 形状/幻灯片大小/参考线。"""
from PySide6.QtWidgets import QInputDialog
from beeoffice.plugins.beeshow import BeeShowView


def make_show(qtbot):
    s = BeeShowView()
    qtbot.addWidget(s)
    s.show()
    return s


def test_insert_textbox_and_art(qtbot):
    s = make_show(qtbot)
    s._insert_html_block('<div>测试文本框</div>', "文本框")
    assert "测试文本框" in s._editor.toPlainText()
    s._insert_html_block('<div style="font-size:40px;">艺术字</div>', "艺术字")
    assert "艺术字" in s._editor.toPlainText()


def test_slide_size_and_guides(qtbot, monkeypatch):
    s = make_show(qtbot)
    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(lambda *a, **k: ("4:3", True)))
    s._set_slide_size_dialog()
    assert s._slide_size == "4:3"
    assert "4/3" in s._slide_size_css
    s._toggle_guides()
    assert s._guides_on is True
    assert "background-size" in s._guides_css
    s._toggle_guides()
    assert s._guides_on is False
