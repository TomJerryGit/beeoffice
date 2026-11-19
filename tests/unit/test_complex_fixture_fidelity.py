"""复杂夹具覆盖：Word 表格/页眉/域，Excel 图表/条件格式/打印区域。"""
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm
from openpyxl import Workbook, load_workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import PatternFill
import pandas as pd
from beeoffice.plugins.bee_export import read_docx_header_footer, read_docx_page_settings
from beeoffice.plugins.beesheet_xlsx_export import export_xlsx_preserving_styles, read_xlsx_formulas
from beeoffice.plugins.beewrite import BeeWriteEditor


def test_word_complex_fixture_roundtrip(qtbot, tmp_path):
    src = tmp_path / "complex.docx"
    d = Document()
    sec = d.sections[0]
    sec.header.paragraphs[0].text = "页眉"
    sec.footer.paragraphs[0].text = "页脚"
    pgb = OxmlElement("w:pgBorders")
    for side in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{side}"); el.set(qn("w:val"), "single"); el.set(qn("w:sz"), "8"); el.set(qn("w:space"), "24"); el.set(qn("w:color"), "1E88E5"); pgb.append(el)
    sec._sectPr.append(pgb)
    d.add_heading("复杂报告", level=1)
    t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text = "指标"; t.cell(0, 1).text = "本期"
    # TOC 域
    from docx.oxml import OxmlElement as OE
    para = d.add_paragraph(); run = para.add_run(); fld = OE("w:fldSimple"); fld.set(qn("w:instr"), 'TOC \\o "1-3" \\h'); run._r.addnext(fld)
    d.save(src)
    meta = read_docx_header_footer(src)
    e = BeeWriteEditor(); qtbot.addWidget(e); e.show(); e._edit_mode = "rich_text"
    from beeoffice.plugins.bee_export import import_from_docx
    e.set_content(import_from_docx(str(src))); e._switch_mode("rich_text")
    e._page_settings.update(read_docx_page_settings(src))
    e._header_text = meta["header"]; e._footer_text = meta["footer"]
    out = tmp_path / "out.docx"; assert e._write_docx(str(out))
    d2 = Document(str(out))
    assert d2.tables and d2.tables[0].cell(0, 0).text == "指标"
    assert d2.sections[0].header.paragraphs[0].text == "页眉"
    assert d2.sections[0].footer.paragraphs[0].text == "页脚"
    assert d2.sections[0]._sectPr.find(qn("w:pgBorders")) is not None
    # 已知缺口：TOC 域导入尚未还原；本测试先覆盖表格/页眉/页脚/边框。
    xml = d2.element.body.xml
    assert "tbl" in xml


def test_excel_complex_fixture_roundtrip(tmp_path):
    src = tmp_path / "complex.xlsx"
    wb = Workbook(); ws = wb.active
    ws.append(["月份", "收入", "成本"])
    ws.append(["一月", 10, 6])
    ws.append(["二月", 20, 8])
    ws["D2"] = "=B2-C2"; ws["D3"] = "=B3-C3"
    ws.print_area = "A1:D3"; ws.freeze_panes = "A2"
    ws.conditional_formatting.add("B2:C3", CellIsRule(operator="greaterThan", formula=["10"], fill=PatternFill("solid", fgColor="E8F5E9")))
    chart = BarChart(); chart.add_data(Reference(ws, min_col=2, min_row=1, max_row=3), titles_from_data=True)
    ws.add_chart(chart, "F2")
    wb.save(src)
    df = pd.read_excel(src)
    out = tmp_path / "out.xlsx"
    assert export_xlsx_preserving_styles(str(src), df, str(out), read_xlsx_formulas(str(src)))
    wb2 = load_workbook(out, data_only=False); ws2 = wb2.active
    assert "$A$1:$D$3" in str(ws2.print_area)
    assert ws2.freeze_panes == "A2"
    assert len(list(ws2.conditional_formatting)) == 1
    assert len(ws2._charts) == 1
    assert ws2["D2"].value == "=B2-C2"


def test_word_toc_import_export(qtbot, tmp_path):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from beeoffice.plugins.bee_export import import_from_docx, TOC_MARKER
    src = tmp_path / "toc.docx"
    d = Document(); d.add_heading("标题", level=1)
    p = d.add_paragraph(); run = p.add_run()
    fld = OxmlElement("w:fldSimple"); fld.set(qn("w:instr"), 'TOC \\o "1-3" \\h')
    run._r.addnext(fld); d.save(src)
    md = import_from_docx(str(src))
    assert TOC_MARKER in md
    e = BeeWriteEditor(); qtbot.addWidget(e); e.show(); e._edit_mode = "rich_text"
    e.set_content(md); e._switch_mode("rich_text"); e._apply_imported_toc_markers()
    out = tmp_path / "toc-out.docx"; assert e._write_docx(str(out))
    assert "TOC" in Document(str(out)).element.body.xml
