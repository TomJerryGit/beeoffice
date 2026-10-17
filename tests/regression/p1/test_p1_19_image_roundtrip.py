# tests/test_p2_regression/test_p1_19_image_roundtrip.py
"""P1-19 回归：图片在富文本 ↔ Markdown 往返中不丢失（v5.0.2）"""
import pytest
from pathlib import Path
from PySide6.QtGui import QImage, QColor, QTextImageFormat


@pytest.fixture
def sample_image(tmp_path):
    img_path = tmp_path / "test.png"
    img = QImage(200, 100, QImage.Format_RGB32)
    img.fill(QColor("red"))
    img.save(str(img_path))
    return img_path


def test_to_markdown_contains_image(qtbot, tmp_path, sample_image):
    from beeoffice.plugins.beewrite_rich_editor import RichTextEditor
    editor = RichTextEditor()
    qtbot.addWidget(editor)
    editor.set_current_file_dir(str(tmp_path))
    c = editor.textCursor()
    fmt = QTextImageFormat()
    fmt.setName(str(sample_image))
    c.insertImage(fmt)
    md = editor.to_markdown()
    assert "![" in md
    assert str(sample_image).replace("\\", "/") in md


def test_set_markdown_restores_image(qtbot, tmp_path, sample_image):
    from beeoffice.plugins.beewrite_rich_editor import RichTextEditor
    editor = RichTextEditor()
    qtbot.addWidget(editor)
    editor.set_current_file_dir(str(tmp_path))
    md = f"# 标题\n\n![]({sample_image})\n\n正文"
    editor.set_markdown(md)
    doc = editor.document()
    block = doc.begin()
    found_img = False
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            if fragment.isValid() and fragment.charFormat().isImageFormat():
                found_img = True
                break
            it += 1
        if found_img:
            break
        block = block.next()
    assert found_img


def test_roundtrip_preserves_image(qtbot, tmp_path, sample_image):
    from beeoffice.plugins.beewrite_rich_editor import RichTextEditor
    editor = RichTextEditor()
    qtbot.addWidget(editor)
    editor.set_current_file_dir(str(tmp_path))
    c = editor.textCursor()
    fmt = QTextImageFormat()
    fmt.setName(str(sample_image))
    c.insertImage(fmt)
    md1 = editor.to_markdown()
    editor.set_markdown(md1)
    md2 = editor.to_markdown()
    assert md1 == md2


def test_image_max_width_720():
    from beeoffice.plugins.beewrite_rich_editor import _IMAGE_MAX_WIDTH
    assert _IMAGE_MAX_WIDTH == 720


def test_image_paragraph_centered(qtbot, tmp_path, sample_image):
    """v5.0.4：图片所在段落应居中"""
    from beeoffice.plugins.beewrite_rich_editor import RichTextEditor
    from PySide6.QtCore import Qt
    editor = RichTextEditor()
    qtbot.addWidget(editor)
    editor.set_current_file_dir(str(tmp_path))
    editor._insert_image_by_path(str(sample_image))
    doc = editor.document()
    block = doc.begin()
    found_center = False
    while block.isValid():
        if block.text() == "":
            bf = block.blockFormat()
            if bf.alignment() == Qt.AlignCenter:
                found_center = True
                break
        block = block.next()
    assert found_center
