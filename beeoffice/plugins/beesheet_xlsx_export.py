"""XLSX 导出保真：保留打印设置、条件格式、列宽、合并单元格。"""
from __future__ import annotations

import pandas as pd


def export_xlsx_preserving_styles(src: str, df: pd.DataFrame, out: str) -> bool:
    """把 df 写回已有 xlsx，尽量保留工作表级设置。"""
    from openpyxl import load_workbook
    from openpyxl.cell.cell import MergedCell

    wb = load_workbook(src)
    ws = wb.active
    merged_ranges = [str(r) for r in ws.merged_cells.ranges]
    for rng in merged_ranges:
        ws.unmerge_cells(rng)
    # 清空旧值但保留单元格样式/条件格式/合并信息
    for row in ws.iter_rows():
        for cell in row:
            if isinstance(cell, MergedCell):
                continue
            cell.value = None
    for c, col in enumerate(df.columns, 1):
        ws.cell(row=1, column=c, value=str(col))
    for r, row in enumerate(df.itertuples(index=False), 2):
        for c, value in enumerate(row, 1):
            if pd.isna(value):
                value = None
            ws.cell(row=r, column=c, value=value)
    for rng in merged_ranges:
        ws.merge_cells(rng)
    # 保留 print_area / print_title / page setup 等由 openpyxl 原样保存
    wb.save(out)
    return True


def export_new_xlsx(df, out: str) -> bool:
    """全新表格导出：写入基础表头样式、边框、列宽、冻结和打印区域。"""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    border = Border(
        left=Side(style="thin", color="D0D0D0"),
        right=Side(style="thin", color="D0D0D0"),
        top=Side(style="thin", color="D0D0D0"),
        bottom=Side(style="thin", color="D0D0D0"),
    )
    header_fill = PatternFill("solid", fgColor="FFF3E0")
    for c, col in enumerate(df.columns, 1):
        cell = ws.cell(row=1, column=c, value=str(col))
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="center")
    for r, row in enumerate(df.itertuples(index=False), 2):
        for c, value in enumerate(row, 1):
            if pd.isna(value):
                value = None
            cell = ws.cell(row=r, column=c, value=value)
            cell.border = border
    for c, col in enumerate(df.columns, 1):
        values = [str(col)] + [str(v) for v in df.iloc[:, c - 1].tolist() if not pd.isna(v)]
        width = min(40, max(8, max(len(v) for v in values) + 2))
        ws.column_dimensions[get_column_letter(c)].width = width
    ws.freeze_panes = "A2"
    if len(df.columns):
        ws.print_area = f"A1:{get_column_letter(len(df.columns))}{max(1, len(df) + 1)}"
    ws.page_setup.orientation = "landscape"
    wb.save(out)
    return True
