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


def test_per_section_header_images(qtbot, tmp_path):
    from docx.enum.section import WD_SECTION
    from docx.shared import Inches
    from beeoffice.plugins.bee_export import read_docx_header_footer_images_by_section
    img1 = tmp_path / "a.png"; Image.new("RGB", (20, 10), "#E67E22").save(img1)
    img2 = tmp_path / "b.png"; Image.new("RGB", (20, 10), "#1E88E5").save(img2)
    src = tmp_path / "two.docx"
    d = Document()
    d.sections[0].header.paragraphs[0].add_run().add_picture(str(img1), width=Inches(0.3))
    s2 = d.add_section(WD_SECTION.NEW_PAGE)
    s2.header.is_linked_to_previous = False
    s2.header.paragraphs[0].add_run().add_picture(str(img2), width=Inches(0.3))
    d.add_paragraph("正文")
    d.save(src)
    by_section = read_docx_header_footer_images_by_section(str(src), str(tmp_path / "media"))
    assert len(by_section) == 2
    assert by_section[0] and by_section[1]

    e = BeeWriteEditor(); qtbot.addWidget(e); e.show(); e._edit_mode = "rich_text"
    e.rich_editor.setPlainText("第一节")
    e._insert_section_break()
    e.rich_editor.textCursor().movePosition(e.rich_editor.textCursor().MoveOperation.End)
    e.rich_editor.textCursor().insertText("第二节")
    e._section_page_settings = [
        {"header_images": [str(img1)], "header": "", "paper": "A4", "columns": 1},
        {"header_images": [str(img2)], "header": "", "paper": "A4", "columns": 1},
    ]
    e._header_images = [str(img1)]
    out = tmp_path / "out.docx"
    assert e._write_docx(str(out))
    d2 = Document(str(out))
    assert any("graphic" in r._r.xml for p in d2.sections[0].header.paragraphs for r in p.runs)
    assert any("graphic" in r._r.xml for p in d2.sections[1].header.paragraphs for r in p.runs)
