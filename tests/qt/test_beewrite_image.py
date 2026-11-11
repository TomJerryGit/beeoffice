"""Beewrite 图片编辑器 GUI 覆盖率补测。"""
import pytest
from PIL import Image
from PySide6.QtWidgets import QFileDialog, QMessageBox

from beeoffice.plugins.beewrite_image import HAS_PIL, ImageEditorDialog


pytestmark = pytest.mark.skipif(not HAS_PIL, reason="需要 Pillow")


@pytest.fixture
def image_file(tmp_path):
    p = tmp_path / "src.png"
    Image.new("RGB", (120, 80), "red").save(p)
    return p


@pytest.fixture
def dlg(qtbot, image_file, monkeypatch):
    d = ImageEditorDialog(str(image_file))
    qtbot.addWidget(d)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    return d


def test_editor_controls(dlg):
    assert dlg._original_image is not None
    dlg._on_scale_changed("50%")
    assert dlg._width_spin.value() == 60
    dlg._on_scale_changed("原始大小")
    dlg._on_size_changed()
    dlg._set_rotation(90)
    assert dlg._rotation == 90
    dlg._flip_h_check.setChecked(True)
    dlg._flip_v_check.setChecked(True)
    dlg._on_flip_changed()
    assert dlg._flip_h and dlg._flip_v
    dlg._grayscale_check.setChecked(True)
    dlg._invert_check.setChecked(True)
    dlg._on_filter_changed()
    assert dlg._grayscale and dlg._invert
    dlg._on_brightness_changed(120)
    assert dlg._brightness == 1.2
    dlg._on_blur_changed(2)
    assert dlg._blur == 2
    assert dlg._process_image() is not None


def test_editor_reset(dlg):
    dlg._set_rotation(90)
    dlg._grayscale_check.setChecked(True)
    dlg._on_filter_changed()
    dlg._reset()
    assert dlg._rotation == 0
    assert dlg._grayscale is False
    assert dlg._width_spin.value() == 120


def test_editor_save(dlg, tmp_path, monkeypatch):
    out = tmp_path / "out.png"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), ""))
    dlg._save_as_file()
    assert out.exists()
    assert dlg.get_result_path() == str(out)


def test_editor_insert(dlg, monkeypatch):
    calls = []
    monkeypatch.setattr(dlg, "accept", lambda: calls.append("accepted"))
    dlg._insert_to_document()
    assert calls == ["accepted"]
    assert dlg.get_result_path()


def test_editor_no_image(qtbot, monkeypatch):
    calls = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: calls.append(a))
    d = ImageEditorDialog()
    qtbot.addWidget(d)
    d._save_as_file()
    d._insert_to_document()
    assert calls


def test_editor_no_original_branches(qtbot):
    from PySide6.QtWidgets import QMessageBox
    d = ImageEditorDialog()
    qtbot.addWidget(d)
    d._on_scale_changed("50%")
    d._on_size_changed()
    assert d._process_image() is None
    d._refresh_preview()
    assert d.get_result_path() is None


def test_editor_load_rgba_and_invalid(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from beeoffice.plugins import beewrite_image as m
    calls = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: calls.append(a))
    rg = tmp_path / "rgba.png"
    Image.new("RGBA", (10, 10), (255, 0, 0, 128)).save(rg)
    d = ImageEditorDialog(str(rg))
    qtbot.addWidget(d)
    assert d._original_image.mode == "RGB"
    d._load_image(str(tmp_path / "missing.png"))
    assert calls


def test_editor_open_image_dialog(qtbot, image_file, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    d = ImageEditorDialog()
    qtbot.addWidget(d)
    d._open_image()  # 取消
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(image_file), ""))
    d._open_image()
    assert d._original_image is not None


def test_editor_save_and_insert_errors(dlg, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    calls = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(tmp_path / "bad.png"), ""))
    class Bad:
        def save(self, *a, **k): raise OSError("save")
    dlg._process_image = lambda: Bad()
    dlg._save_as_file()
    dlg._insert_to_document()
    assert calls


def test_no_pillow_branch(qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    import beeoffice.plugins.beewrite_image as m
    calls = []
    monkeypatch.setattr(m, "HAS_PIL", False)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: calls.append(a))
    d = m.ImageEditorDialog()
    qtbot.addWidget(d)
    assert calls


def test_save_cancel(dlg, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    dlg._save_as_file()
    assert dlg.get_result_path() is None
