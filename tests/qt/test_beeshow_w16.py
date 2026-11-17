"""Wave 4 W16：BeeShow 放映入口与 20 页 PPTX 往返。"""
from unittest.mock import patch

from pptx import Presentation

from beeoffice.plugins.beeshow import BeeShowView


def make_show(qtbot, slides=20):
    s = BeeShowView()
    qtbot.addWidget(s)
    s.show()
    s._editor.setPlainText("\n---\n".join(f"# 第 {i} 页" for i in range(1, slides + 1)))
    s._update_preview()
    return s


def test_play_from_current_exists(qtbot):
    s = make_show(qtbot, 3)
    assert hasattr(s, "_start_from_current")


def test_20_slide_pptx_roundtrip(qtbot, tmp_path):
    s = make_show(qtbot, 20)
    out = tmp_path / "twenty.pptx"
    with patch(
        "beeoffice.plugins.beeshow_export_mixin.QFileDialog.getSaveFileName",
        return_value=(str(out), "PowerPoint (*.pptx)"),
    ), patch(
        "beeoffice.plugins.beeshow_export_mixin.QMessageBox.information",
        return_value=None,
    ), patch(
        "beeoffice.plugins.beeshow_export_mixin.QMessageBox.warning",
        return_value=None,
    ):
        s._export_pptx()
    assert out.exists()
    assert len(Presentation(str(out)).slides) == 20


def test_pptx_transition_retention(qtbot, tmp_path):
    from pptx import Presentation
    from pptx.oxml.ns import qn
    s = make_show(qtbot, 2)
    s._slide_animations = [{"transition": "fade"}, {"transition": "push"}]
    out = tmp_path / "transitions.pptx"
    from unittest.mock import patch
    with patch(
        "beeoffice.plugins.beeshow_export_mixin.QFileDialog.getSaveFileName",
        return_value=(str(out), "PowerPoint (*.pptx)"),
    ), patch(
        "beeoffice.plugins.beeshow_export_mixin.QMessageBox.information",
        return_value=None,
    ), patch(
        "beeoffice.plugins.beeshow_export_mixin.QMessageBox.warning",
        return_value=None,
    ):
        s._export_pptx()
    prs = Presentation(str(out))
    tags = [slide._element.find(qn("p:transition")) is not None for slide in prs.slides]
    assert tags == [True, True]


def test_pptx_element_animation_retention(qtbot, tmp_path):
    from pptx import Presentation
    from pptx.oxml.ns import qn
    s = make_show(qtbot, 2)
    s._slide_animations = [
        {"transition": "fade", "entries": [{"selector": "h1", "effect": "fade_in", "duration": 500}]},
        {"transition": "push", "entries": [{"selector": "p", "effect": "slide_in", "duration": 400}]},
    ]
    out = tmp_path / "animations.pptx"
    from unittest.mock import patch
    with patch(
        "beeoffice.plugins.beeshow_export_mixin.QFileDialog.getSaveFileName",
        return_value=(str(out), "PowerPoint (*.pptx)"),
    ), patch(
        "beeoffice.plugins.beeshow_export_mixin.QMessageBox.information",
        return_value=None,
    ), patch(
        "beeoffice.plugins.beeshow_export_mixin.QMessageBox.warning",
        return_value=None,
    ):
        s._export_pptx()
    prs = Presentation(str(out))
    for slide in prs.slides:
        timing = slide._element.find(qn("p:timing"))
        assert timing is not None
        assert timing.find(".//" + qn("p:animEffect")) is not None


def test_pptx_exit_emphasis_retention(qtbot, tmp_path):
    from pptx import Presentation
    from pptx.oxml.ns import qn
    s = make_show(qtbot, 1)
    s._slide_animations = [{
        "transition": "fade",
        "entries": [
            {"selector": "h1", "effect": "fade_in", "duration": 300},
            {"selector": "h1", "effect": "fade_out", "duration": 300},
            {"selector": "p", "effect": "grow", "duration": 300},
        ],
    }]
    out = tmp_path / "exit-emph.pptx"
    from unittest.mock import patch
    with patch(
        "beeoffice.plugins.beeshow_export_mixin.QFileDialog.getSaveFileName",
        return_value=(str(out), "PowerPoint (*.pptx)"),
    ), patch(
        "beeoffice.plugins.beeshow_export_mixin.QMessageBox.information",
        return_value=None,
    ), patch(
        "beeoffice.plugins.beeshow_export_mixin.QMessageBox.warning",
        return_value=None,
    ):
        s._export_pptx()
    slide = Presentation(str(out)).slides[0]
    xml = slide._element.xml
    assert 'presetClass="exit"' in xml
    assert 'presetClass="emph"' in xml
    assert "animScale" in xml
