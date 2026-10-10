# tests/test_p2_regression/test_v502_document_has_images.py
"""
v5.0.2 回归：_document_has_images 应正确检测富文本里的图片。

背景：
  从富文本切到 Markdown 时，若文档含图片，Qt 预览无法显示，
  需要给用户提示。ModeMixin._document_has_images 负责扫描
  rich_editor 里所有 fragment，判断是否含 ImageFormat。

测试策略：
  1. 空文档 → False
  2. 纯文本 → False
  3. 插入图片后 → True
  4. 插入图片后删除 → False（边界：验证不是缓存）
"""
import pytest


def _make_image(tmp_path):
    """造一张测试图片。"""
    try:
        from PySide6.QtGui import QImage, QColor
    except ImportError:
        pytest.skip("PySide6 不可用")
    p = tmp_path / "img.png"
    img = QImage(50, 50, QImage.Format_RGB32)
    img.fill(QColor("red"))
    img.save(str(p))
    return p


def test_empty_document_has_no_images(beewrite_editor):
    """v5.0.2：空文档应返回 False。"""
    beewrite_editor._switch_mode("rich_text")
    beewrite_editor.rich_editor.clear()
    assert beewrite_editor._document_has_images() is False


def test_text_only_document_has_no_images(beewrite_editor):
    """v5.0.2：纯文本文档应返回 False。"""
    beewrite_editor._switch_mode("rich_text")
    beewrite_editor.rich_editor.setPlainText("只有文字，没有图片。")
    assert beewrite_editor._document_has_images() is False


def test_document_with_image_returns_true(beewrite_editor, tmp_path):
    """v5.0.2：插入图片后应返回 True。"""
    beewrite_editor._switch_mode("rich_text")
    img_path = _make_image(tmp_path)
    beewrite_editor.rich_editor._insert_image_by_path(str(img_path))
    assert beewrite_editor._document_has_images() is True, (
        "v5.0.2：含图片的文档应被正确识别"
    )


def test_cleared_document_returns_false(beewrite_editor, tmp_path):
    """v5.0.2：清空后再判断应返回 False（非缓存）。"""
    beewrite_editor._switch_mode("rich_text")
    img_path = _make_image(tmp_path)
    beewrite_editor.rich_editor._insert_image_by_path(str(img_path))
    assert beewrite_editor._document_has_images() is True

    beewrite_editor.rich_editor.clear()
    assert beewrite_editor._document_has_images() is False, (
        "v5.0.2：清空后应立即返回 False，不能是缓存"
    )