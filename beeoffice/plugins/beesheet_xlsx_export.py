"""XLSX 导出保真：保留打印设置、条件格式、列宽、合并单元格。"""
from __future__ import annotations

import pandas as pd


def export_xlsx_preserving_styles(src: str, df: pd.DataFrame, out: str) -> bool:
    """把 df 写回已有 xlsx，尽量保留工作表级设置。"""
    from openpyxl import load_workbook

    wb = load_workbook(src)
    ws = wb.active
    # 清空旧值但保留单元格样式/条件格式/合并信息
    for row in ws.iter_rows():
        for cell in row:
            cell.value = None
    for c, col in enumerate(df.columns, 1):
        ws.cell(row=1, column=c, value=str(col))
    for r, row in enumerate(df.itertuples(index=False), 2):
        for c, value in enumerate(row, 1):
            if pd.isna(value):
                value = None
            ws.cell(row=r, column=c, value=value)
    # 保留 print_area / print_title / page setup 等由 openpyxl 原样保存
    wb.save(out)
    return True
