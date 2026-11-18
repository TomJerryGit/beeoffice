#!/usr/bin/env python3
"""生成代表性语料样本并登记到 tests/corpus/manifest.json。

注意：这些是“代表性/合成样本”，不是真实客户文档；
真实样本仍须人工采集与脱敏。
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests" / "corpus"
RAW = CORPUS / "raw"


def seed_word_basic(path: Path):
    from docx import Document
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm
    d = Document()
    sec = d.sections[0]
    sec.top_margin = Cm(2.0)
    sec.header.paragraphs[0].text = "XX 公司内部文件"
    sec.footer.paragraphs[0].text = "机密"
    d.add_heading("年度工作报告", level=1)
    d.add_paragraph("本报告用于代表性语料回归。")
    d.add_heading("一、数据", level=2)
    t = d.add_table(rows=3, cols=3)
    for r, row in enumerate([["指标", "目标", "完成"], ["收入", "1000", "950"], ["利润", "100", "88"]]):
        for c, v in enumerate(row):
            t.cell(r, c).text = v
    # 插入 TOC 域，验证复杂 OOXML 结构
    p = d.add_paragraph()
    run = p.add_run()
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), 'TOC \\o "1-3" \\h \\z \\u')
    run._r.addnext(fld)
    d.save(path)


def seed_word_long(path: Path):
    from docx import Document
    d = Document()
    for i in range(20):
        d.add_heading(f"第 {i + 1} 章", level=1)
        d.add_paragraph("这是用于 20 页性能与结构回归的正文内容。" * 8)
        if i < 19:
            d.add_page_break()
    d.save(path)


def seed_excel(path: Path):
    from openpyxl import Workbook
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.append(["月份", "收入", "成本", "利润"])
    for i, row in enumerate([["一月", 100, 60, "=B2-C2"], ["二月", 120, 70, "=B3-C3"], ["三月", 90, 50, "=B4-C4"]], 2):
        ws.append(row)
    ws["A1"].font = Font(bold=True)
    ws["A1"].fill = PatternFill("solid", fgColor="FFE0B2")
    ws.print_area = "A1:D4"
    ws.freeze_panes = "A2"
    ws.conditional_formatting.add("B2:C4", CellIsRule(operator="greaterThan", formula=["100"], fill=PatternFill("solid", fgColor="E8F5E9")))
    wb.save(path)


def seed_ppt(path: Path):
    from pptx import Presentation
    from pptx.util import Inches
    prs = Presentation()
    for i in range(5):
        slide = prs.slides.add_slide(prs.slide_layouts[5])
        slide.shapes.title.text = f"汇报第 {i + 1} 页"
        box = slide.shapes.add_textbox(Inches(1), Inches(1.5), Inches(6), Inches(2))
        box.text = "要点 A\n要点 B\n要点 C"
    # 一页原生表格
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.shapes.add_table(2, 2, Inches(1), Inches(1), Inches(5), Inches(2))
    prs.save(path)


def seed_pdf(path: Path):
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(path))
    for i in range(3):
        c.drawString(40, 780, f"代表性 PDF 第 {i + 1} 页")
        c.drawString(40, 750, "仅用于回归测试")
        c.showPage()
    c.save()


def update_manifest(entries):
    path = CORPUS / "manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    by_id = {s["id"]: s for s in data.get("samples", [])}
    for sid, rel in entries.items():
        if sid in by_id:
            by_id[sid]["path"] = rel
            by_id[sid]["status"] = "synthetic-ready"
            by_id[sid].setdefault("tags", []).append("synthetic")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / "word-001-complex.docx"; seed_word_basic(path)
    path = RAW / "word-005-long.docx"; seed_word_long(path)
    path = RAW / "excel-001-formula.xlsx"; seed_excel(path)
    path = RAW / "ppt-001-shapes.pptx"; seed_ppt(path)
    path = RAW / "pdf-001-basic.pdf"; seed_pdf(path)
    update_manifest({
        "word-001": "raw/word-001-complex.docx",
        "word-005": "raw/word-005-long.docx",
        "excel-001": "raw/excel-001-formula.xlsx",
        "ppt-001": "raw/ppt-001-shapes.pptx",
        "pdf-001": "raw/pdf-001-basic.pdf",
    })
    print("corpus seed done:", RAW)


if __name__ == "__main__":
    main()
