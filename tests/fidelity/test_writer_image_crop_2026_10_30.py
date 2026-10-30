"""Writer：图片裁剪 + 表格重复标题行。"""
from docx import Document
from PIL import Image

from beeoffice.plugins.bee_export import export_to_docx
from beeoffice.plugins.beewrite_image import ImageEditorDialog


def _dialog_with_image(status="RGB", size=(100, 50)):
    dlg = ImageEditorDialog()
    dlg._original_image = Image.new(status, size, "red")
    dlg._width_spin.setValue(size[0])
    dlg._height_spin.setValue(size[1])
    return dlg


def test_image_crop_left_right(qapp):
    dlg = _dialog_with_image()
    dlg._crop_spins["left"].setValue(10)
    dlg._crop_spins["right"].setValue(10)
    out = dlg._process_image()
    assert out.size == (80, 50)


def test_image_crop_top_bottom(qapp):
    dlg = _dialog_with_image()
    dlg._crop_spins["top"].setValue(10)
    dlg._crop_spins["bottom"].setValue(10)
    out = dlg._process_image()
    assert out.size == (100, 40)


def test_table_repeat_header_row_exported(tmp_path):
    md = "| 列A | 列B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n"
    out = tmp_path / "table.docx"
    assert export_to_docx(md, str(out)) is True
    doc = Document(str(out))
    tbl = doc.tables[0]
    xml = tbl.rows[0]._tr.xml
    assert "w:tblHeader" in xml
