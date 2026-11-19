"""Word 合并单元格/嵌套表格导入。"""
from docx import Document
from beeoffice.plugins.bee_export import import_from_docx


def test_merged_cell_not_duplicated(tmp_path):
    p = tmp_path / "merge.docx"
    d = Document(); t = d.add_table(2, 2)
    t.cell(0, 0).text = "合并"
    t.cell(0, 0).merge(t.cell(0, 1))
    t.cell(1, 0).text = "A"; t.cell(1, 1).text = "B"
    d.save(p)
    md = import_from_docx(str(p))
    assert md.count("合并") == 1


def test_nested_table_content_imported(tmp_path):
    p = tmp_path / "nested.docx"
    d = Document(); t = d.add_table(1, 1)
    t.cell(0, 0).text = "外层"
    nested = t.cell(0, 0).add_table(1, 2)
    nested.cell(0, 0).text = "内1"; nested.cell(0, 1).text = "内2"
    d.save(p)
    md = import_from_docx(str(p))
    assert "外层" in md
    assert "内1" in md and "内2" in md


def test_qtext_merge_export(qtbot, tmp_path):
    from PySide6.QtWidgets import QTextEdit
    from beeoffice.plugins.beewrite import BeeWriteEditor
    e = BeeWriteEditor(); qtbot.addWidget(e); e.show(); e._edit_mode = "rich_text"
    cursor = e.rich_editor.textCursor()
    table = cursor.insertTable(2, 2)
    table.cellAt(0, 0).firstCursorPosition().insertText("合并")
    table.mergeCells(0, 0, 1, 2)
    out = tmp_path / "merged-out.docx"
    assert e._write_docx(str(out))
    d = Document(str(out))
    assert len(d.tables) == 1
    # 合并后 docx 的行列仍存在，但底层 tc 应减少
    tc_count = len(d.tables[0]._tbl.tr_lst[0].tc_lst)
    assert tc_count <= 1
