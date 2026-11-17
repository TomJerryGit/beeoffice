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
