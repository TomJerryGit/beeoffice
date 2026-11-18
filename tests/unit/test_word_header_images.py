"""Word 页眉页脚图片导入/导出。"""
from pathlib import Path
from docx import Document
from docx.shared import Inches
from PIL import Image
from beeoffice.plugins.bee_export import read_docx_header_footer_images
from beeoffice.plugins.beewrite import BeeWriteEditor


def test_header_image_extract_and_export(qtbot, tmp_path):
    img = tmp_path / "logo.png"
    Image.new("RGB", (40, 20), "#E67E22").save(img)
    src = tmp_path / "src.docx"
    d = Document()
    d.sections[0].header.paragraphs[0].add_run().add_picture(str(img), width=Inches(0.5))
    d.add_paragraph("正文")
    d.save(src)
    paths = read_docx_header_footer_images(str(src), str(tmp_path / "media"))
    assert paths and Path(paths[0]).is_file()
    e = BeeWriteEditor(); qtbot.addWidget(e); e.show(); e._edit_mode = "rich_text"
    e.rich_editor.setPlainText("正文")
    e._header_text = ""
    e._header_images = [str(img)]
    out = tmp_path / "out.docx"
    assert e._write_docx(str(out))
    d2 = Document(str(out))
    assert any("graphic" in r._r.xml for p in d2.sections[0].header.paragraphs for r in p.runs)
