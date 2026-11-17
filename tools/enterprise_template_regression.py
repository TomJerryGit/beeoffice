"""企业模板代表性回归：外部模板 → BeeOffice 导出 → WPS 打开验证。"""
from __future__ import annotations

import pathlib
import sys
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT.parent / "analysis" / "enterprise-templates"
OUT.mkdir(parents=True, exist_ok=True)


def word_template():
    from docx import Document
    from docx.shared import Pt

    src = OUT / "enterprise-word-template.docx"
    d = Document()
    sec = d.sections[0]
    sec.header.paragraphs[0].text = "XX 公司内部文件"
    sec.footer.paragraphs[0].text = "机密 · 禁止外传"
    d.add_heading("XX 公司 2026 年度工作报告", level=1)
    d.add_paragraph("一、总体情况")
    t = d.add_table(rows=3, cols=3)
    for r, row in enumerate([["指标", "目标", "完成"], ["收入", "1000", "950"], ["利润", "100", "88"]]):
        for c, val in enumerate(row):
            t.cell(r, c).text = val
    d.add_page_break()
    d.add_heading("二、重点工作", level=1)
    d.add_paragraph("完成企业模板兼容性回归。")
    d.save(src)

    from beeoffice.plugins.bee_export import import_from_docx, read_docx_header_footer
    from beeoffice.plugins.beewrite import BeeWriteEditor
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    md = import_from_docx(str(src))
    meta = read_docx_header_footer(str(src))
    e = BeeWriteEditor()
    e._edit_mode = "rich_text"
    e.set_content(md)
    e._switch_mode("rich_text")
    e._header_text = meta.get("header", "")
    e._footer_text = meta.get("footer", "")
    out = OUT / "enterprise-word-output.docx"
    assert e._write_docx(str(out))
    e.close()
    return out


def excel_template():
    from openpyxl import Workbook
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    from beeoffice.plugins.beesheet import BeeSheetView

    src = OUT / "enterprise-excel-template.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "季度报表"
    ws.merge_cells("A1:D1")
    ws["A1"] = "XX 公司 2026 年季度经营报表"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A1"].alignment = Alignment(horizontal="center")
    for c, v in enumerate(["项目", "Q1", "Q2", "合计"], 1):
        ws.cell(row=2, column=c, value=v).font = Font(bold=True)
        ws.cell(row=2, column=c).fill = PatternFill("solid", fgColor="FFE0B2")
    for r, row in enumerate([["收入", 100, 120, "=B3+C3"], ["成本", 60, 70, "=B4+C4"]], 3):
        for c, v in enumerate(row, 1):
            ws.cell(row=r, column=c, value=v)
    ws.print_area = "A1:D4"
    ws.freeze_panes = "A3"
    ws.page_setup.orientation = "landscape"
    ws.conditional_formatting.add(
        "B3:C4",
        CellIsRule(operator="greaterThan", formula=["100"],
                   fill=PatternFill("solid", fgColor="E8F5E9")),
    )
    for c in range(1, 5):
        ws.column_dimensions[get_column_letter(c)].width = 16
    wb.save(src)

    app = QApplication.instance() or QApplication([])
    sheet = BeeSheetView()
    df = sheet._read_sheet_file(str(src))
    sheet._apply_imported_dataframe(df, str(src))
    out = OUT / "enterprise-excel-output.xlsx"
    with patch.object(QFileDialog, "getSaveFileName", return_value=(str(out), "Excel (*.xlsx)")), \
         patch.object(QMessageBox, "information", return_value=None):
        sheet._export_xlsx()
    sheet.close()
    return out


def ppt_template():
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    from beeoffice.plugins.beeshow import BeeShowView

    src = OUT / "enterprise-ppt-template.pptx"
    prs = Presentation()
    prs.slide_width = Inches(10)
    prs.slide_height = Inches(7.5)
    for i in range(6):
        slide = prs.slides.add_slide(prs.slide_layouts[5])
        slide.shapes.title.text = f"XX 公司汇报 - 第 {i + 1} 部分"
        box = slide.shapes.add_textbox(Inches(1), Inches(1.8), Inches(7), Inches(3))
        box.text = "经营情况\n• 收入\n• 利润\n• 重点工作"
        fill = slide.background.fill
        fill.solid()
        fill.fore_color.rgb = RGBColor(0xF5, 0xF7, 0xFA)
    prs.save(src)

    app = QApplication.instance() or QApplication([])
    view = BeeShowView()
    assert view.open_pptx(str(src))
    view._slide_animations = [
        {"transition": "fade", "entries": [
            {"selector": "h1", "effect": "fade_in", "duration": 500},
        ]}
        for _ in range(len(view._slides_html))
    ]
    out = OUT / "enterprise-ppt-output.pptx"
    with patch.object(QFileDialog, "getSaveFileName", return_value=(str(out), "PowerPoint (*.pptx)")), \
         patch.object(QMessageBox, "information", return_value=None), \
         patch.object(QMessageBox, "warning", return_value=None):
        view._export_pptx()
    view.close()
    return out


def pdf_template():
    from reportlab.pdfgen import canvas
    from pypdf import PdfReader
    from beeoffice.pdf_tools import burn_annotations, add_watermark

    src = OUT / "enterprise-pdf-template.pdf"
    c = canvas.Canvas(str(src))
    for i in range(12):
        c.drawString(40, 780, f"XX 公司内部资料 - 第 {i + 1} 页")
        c.drawString(40, 750, "仅供内部培训使用")
        c.showPage()
    c.save()
    wm = OUT / "enterprise-pdf-watermarked.pdf"
    add_watermark(src, wm, "内部资料")
    out = OUT / "enterprise-pdf-output.pdf"
    anns = [
        {"page": i, "rect": [40, 730, 300, 760], "type": "highlight",
         "text": "", "color": [1, 0.8, 0], "width": 2}
        for i in range(12)
    ]
    burn_annotations(wm, out, anns)
    assert len(PdfReader(str(out)).pages) == 12
    return out


def main():
    for fn in (word_template, excel_template, ppt_template, pdf_template):
        p = fn()
        print(f"{p.name}: {p.stat().st_size} bytes")


if __name__ == "__main__":
    main()
