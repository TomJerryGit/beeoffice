"""Word 原生文本框导出/导入。"""
from zipfile import ZipFile
from beeoffice.plugins.bee_export import import_from_docx
from beeoffice.plugins.beewrite import BeeWriteEditor
from beeoffice.plugins.beewrite_textbox import insert_textbox


def test_textbox_native_export_and_import(qtbot, tmp_path):
    e = BeeWriteEditor(); qtbot.addWidget(e); e.show(); e._edit_mode = "rich_text"
    e.rich_editor.setPlainText("正文前")
    insert_textbox(e.rich_editor, {
        "bg_color": "#FFF3E0", "border_color": "#E67E22",
        "padding": 8, "width": 300,
    })
    out = tmp_path / "textbox.docx"
    assert e._write_docx(str(out))
    with ZipFile(out) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    assert "wps:txbx" in xml
    assert "txbxContent" in xml
    md = import_from_docx(str(out))
    assert "在此输入文本框内容" in md


def test_floating_textbox_anchor(qtbot, tmp_path):
    e = BeeWriteEditor(); qtbot.addWidget(e); e.show(); e._edit_mode = "rich_text"
    e.rich_editor.setPlainText("正文")
    insert_textbox(e.rich_editor, {
        "bg_color": "#FFF3E0", "border_color": "#E67E22",
        "padding": 8, "width": __import__("PySide6.QtGui", fromlist=["QTextLength"]).QTextLength(
            __import__("PySide6.QtGui", fromlist=["QTextLength"]).QTextLength.FixedLength, 240
        ),
        "height": 100, "float_mode": "左浮动", "x": 30, "y": 40,
    })
    out = tmp_path / "float.docx"
    assert e._write_docx(str(out))
    with ZipFile(out) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    assert "wp:anchor" in xml
    assert "positionH" in xml
    assert "posOffset" in xml
