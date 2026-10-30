"""Writer：图片环绕 UI + 富文本→Markdown 往返。"""
from PySide6.QtGui import (
    QTextCursor,
    QTextDocument,
    QTextImageFormat,
)

from beeoffice.plugins.beewrite_image import (
    IMAGE_WRAP_PROPERTY,
    ImageEditorDialog,
)
from beeoffice.plugins.beewrite_rich_editor import RichTextEditor


def test_dialog_wrap_mode(qapp):
    dlg = ImageEditorDialog()
    assert dlg.wrap_mode() == ""
    dlg._wrap_combo.setCurrentIndex(dlg._wrap_combo.findData("square"))
    assert dlg.wrap_mode() == "square"


def test_rich_image_wrap_roundtrip_markdown(qapp):
    doc = QTextDocument()
    cursor = QTextCursor(doc)
    fmt = QTextImageFormat()
    fmt.setName("pic.png")
    fmt.setProperty(IMAGE_WRAP_PROPERTY, "square")
    cursor.insertImage(fmt)
    block = doc.firstBlock()
    md = RichTextEditor._block_with_images_to_md(None, block)
    assert '<img src="pic.png" data-wrap="square">' in md


def test_markdown_html_image_wrap_exports_anchor(qapp, tmp_path):
    from docx import Document
    from PIL import Image

    from beeoffice.plugins.bee_export import export_to_docx

    Image.new("RGB", (40, 20), "blue").save(tmp_path / "pic.png")
    md = '<img src="pic.png" data-wrap="square">\n'
    out = tmp_path / "wrap.docx"
    assert export_to_docx(md, str(out), base_dir=str(tmp_path)) is True
    doc = Document(str(out))
    xml = doc.element.body.xml
    assert "wp:anchor" in xml
    assert "wp:wrapSquare" in xml
