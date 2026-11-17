"""生成真实样本并走 BeeOffice 导出，用于 P0 回归/验收。"""
from __future__ import annotations

import pathlib
import sys
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT.parent / "analysis" / "real-docs"
OUT.mkdir(parents=True, exist_ok=True)


def word_sample():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QTextCursor, QTextBlockFormat

    app = QApplication.instance() or QApplication([])
    from beeoffice.plugins.beewrite import BeeWriteEditor
    e = BeeWriteEditor()
    e._edit_mode = "rich_text"
    e.rich_editor.setPlainText("第一章 总述\n正文见图 1[F1][E1]")
    # 标题 1
    cur = e.rich_editor.textCursor()
    cur.movePosition(QTextCursor.Start)
    cur.select(QTextCursor.BlockUnderCursor)
    bf = cur.blockFormat()
    bf.setHeadingLevel(1)
    cur.setBlockFormat(bf)
    e._captions = [{"kind": "图", "text": "系统架构"}]
    e._footnotes = ["脚注内容"]
    e._endnotes = ["尾注内容"]
    e._header_text = "内部资料"
    e._footer_text = "第 1 页"
    e._update_toc()
    path = OUT / "real-word.docx"
    assert e._write_docx(str(path))
    e.close()
    return path


def excel_sample():
    from openpyxl import Workbook
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.styles import Font, PatternFill
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

    app = QApplication.instance() or QApplication([])
    from beeoffice.plugins.beesheet import BeeSheetView
    src = OUT / "real-source.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["月份", "收入", "支出"])
    ws.append(["一月", 100, 60])
    ws.append(["二月", 200, 80])
    ws["A1"].font = Font(bold=True)
    ws["A1"].fill = PatternFill("solid", fgColor="FFE0B2")
    ws.print_area = "A1:C3"
    ws.freeze_panes = "A2"
    ws.conditional_formatting.add(
        "B2:C3", CellIsRule(operator="greaterThan", formula=["0"],
                            fill=PatternFill("solid", fgColor="E8F5E9"))
    )
    wb.save(src)
    sheet = BeeSheetView()
    df = sheet._read_sheet_file(str(src))
    sheet._apply_imported_dataframe(df, str(src))
    path = OUT / "real-excel.xlsx"
    with patch.object(QFileDialog, "getSaveFileName", return_value=(str(path), "Excel (*.xlsx)")), \
         patch.object(QMessageBox, "information", return_value=None):
        sheet._export_xlsx()
    sheet.close()
    return path


def ppt_sample():
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

    app = QApplication.instance() or QApplication([])
    from beeoffice.plugins.beeshow import BeeShowView
    s = BeeShowView()
    s.show()
    s._editor.setPlainText("\n---\n".join(
        f"# 第 {i} 页\n\n- 要点 A\n- 要点 B" for i in range(1, 9)
    ))
    s._update_preview()
    s._slide_animations = [
        {"transition": "fade", "entries": [
            {"selector": "h1", "effect": "fade_in", "duration": 500},
            {"selector": "p", "effect": "grow", "duration": 300},
        ]}
        for _ in range(len(s._slides_html))
    ]
    path = OUT / "real-ppt.pptx"
    with patch.object(QFileDialog, "getSaveFileName", return_value=(str(path), "PowerPoint (*.pptx)")), \
         patch.object(QMessageBox, "information", return_value=None), \
         patch.object(QMessageBox, "warning", return_value=None):
        s._export_pptx()
    s.close()
    return path


def pdf_sample():
    from pypdf import PdfWriter
    from beeoffice.pdf_tools import burn_annotations
    src = OUT / "real-source.pdf"
    w = PdfWriter()
    for _ in range(20):
        w.add_blank_page(width=300, height=400)
    w.write(str(src))
    anns = [
        {"page": i, "rect": [10, 10, 90, 25], "type": "highlight",
         "text": "", "color": [1, 0.8, 0], "width": 2}
        for i in range(20)
    ]
    out = OUT / "real-pdf.pdf"
    burn_annotations(src, out, anns)
    return out


def main():
    for fn in (word_sample, excel_sample, ppt_sample, pdf_sample):
        p = fn()
        print(f"{p.name}: {p.stat().st_size} bytes")


if __name__ == "__main__":
    main()
