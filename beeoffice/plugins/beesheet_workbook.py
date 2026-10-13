# beeoffice/plugins/beesheet_workbook.py
"""
蜜算的工作簿读写（保真度阶段 A 第一刀）

问题（见 docs/fidelity.md）
--------------------------
蜜算的模型是**单个 DataFrame**，导入用
    pd.read_excel(path, engine='openpyxl', nrows=200001)
导出用
    df.to_excel(path, index=False)

于是实测丢失 8/9 项特征：

  - **多工作表只剩第一张**（`read_excel` 默认只读首个 sheet）—— 第二张表直接消失
  - **公式全丢**（`f` 元素 → 0）：公式不是 DataFrame 能承载的东西
  - 合并区域、条件格式、数据验证、冻结窗格、图表同样无处存身

本模块先解决**前两项**（收益最大、最容易被用户判定"不能用"）：
把"工作簿"作为一个显式对象承载**全部工作表**与**每格公式**，
读写都走 openpyxl，不再把 DataFrame 当作整个文档。

**本刀不解决**：合并区域、条件格式、数据验证、冻结窗格、图表
（这些是后续切片；`SheetData` 预留了 `extras` 位置但暂未实现）。

公式坐标约定（容易错，故在此写明并测试）
--------------------------------------
openpyxl 的坐标是 **1 起**；DataFrame 的位置是 **0 起**，且 pandas 默认把
工作表**第 1 行当表头**。因此：

    工作表 (R, C)  [R>=2]  →  df 位置 (R-2, C-1)
    工作表 (1, C)          →  表头，不参与公式映射

`read_workbook()` 负责换算，调用方只面对 df 坐标。
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

try:
    from openpyxl import Workbook, load_workbook

    HAS_OPENPYXL = True
except ImportError:  # pragma: no cover
    HAS_OPENPYXL = False


@dataclass
class SheetData:
    """一张工作表：值（DataFrame）+ 公式（df 坐标 → 公式字符串）。"""

    name: str
    df: pd.DataFrame
    #: {(df 行, df 列): "=B2*C2"}，均为 0 起
    formulas: Dict[Tuple[int, int], str] = field(default_factory=dict)

    def formula_count(self) -> int:
        return len(self.formulas)


@dataclass
class WorkbookData:
    """一个完整工作簿，保序。"""

    sheets: List[SheetData] = field(default_factory=list)
    #: 首张表名（蜜算当前只编辑一张，其余原样保留待写回）
    active: str = ""

    @property
    def sheet_names(self) -> List[str]:
        return [s.name for s in self.sheets]

    @property
    def formula_count(self) -> int:
        return sum(s.formula_count() for s in self.sheets)

    def get(self, name: str) -> Optional[SheetData]:
        for s in self.sheets:
            if s.name == name:
                return s
        return None


# ==================== 读 ====================

def read_workbook(path, max_rows: Optional[int] = None) -> WorkbookData:
    """
    读**全部**工作表与每格公式。

    :param path: .xlsx 路径
    :param max_rows: 每张表最多读多少行（None = 不限）
    :return: WorkbookData
    """
    path = Path(path)
    if not HAS_OPENPYXL:
        raise RuntimeError("需要 openpyxl 才能读写 xlsx")

    # 值：pandas 读全部工作表（pandas>=2.0 返回 dict，保序）
    frames: Dict[str, pd.DataFrame] = pd.read_excel(
        path, sheet_name=None, engine="openpyxl", nrows=max_rows
    )

    formulas_by_sheet = _read_formulas(path)

    sheets: List[SheetData] = []
    for name, df in frames.items():
        sheets.append(
            SheetData(
                name=str(name),
                df=df,
                formulas=formulas_by_sheet.get(str(name), {}),
            )
        )

    active = sheets[0].name if sheets else ""
    return WorkbookData(sheets=sheets, active=active)


def _read_formulas(path: Path) -> Dict[str, Dict[Tuple[int, int], str]]:
    """
    用 openpyxl 扫出每张表的公式（保持公式字符串，不求值）。

    :return: {表名: {(df 行, df 列): 公式}}
    """
    result: Dict[str, Dict[Tuple[int, int], str]] = {}
    try:
        wb = load_workbook(path, data_only=False, read_only=True)
    except Exception as e:  # noqa: BLE001 - 读不到公式不应让导入整体失败
        logging.warning(f"读取公式失败（将按无公式处理）: {e}")
        return result

    try:
        for name in wb.sheetnames:
            ws = wb[name]
            cells: Dict[Tuple[int, int], str] = {}
            for row in ws.iter_rows():
                for cell in row:
                    value = cell.value
                    if isinstance(value, str) and value.startswith("="):
                        # 工作表 1 起 → df 0 起；第 1 行是表头，跳过
                        if cell.row >= 2:
                            cells[(cell.row - 2, cell.column - 1)] = value
            if cells:
                result[str(name)] = cells
    finally:
        try:
            wb.close()
        except Exception:
            pass

    return result


# ==================== 写 ====================

def _cell_value(value):
    """把 pandas/numpy 的值转成 openpyxl 可写的值。"""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def write_workbook(workbook: WorkbookData, path) -> None:
    """
    把全部工作表与公式写回 .xlsx。

    公式单元格写**公式字符串**（如 `=B2*C2`），Excel 打开时会自行计算；
    这样公式本身得以保留（原实现写的是 pandas 的**计算值**，公式消失）。
    """
    if not HAS_OPENPYXL:
        raise RuntimeError("需要 openpyxl 才能读写 xlsx")

    wb = Workbook()
    wb.remove(wb.active)          # 去掉默认空表，避免多出一张

    for sheet in workbook.sheets:
        ws = wb.create_sheet(title=_safe_title(sheet.name))

        columns = list(sheet.df.columns)
        for col_idx, col_name in enumerate(columns, start=1):
            ws.cell(row=1, column=col_idx, value=str(col_name))

        for df_row, (_, row) in enumerate(sheet.df.iterrows()):
            sheet_row = df_row + 2
            values = row.tolist()
            for col_idx in range(len(columns)):
                value = values[col_idx] if col_idx < len(values) else None
                formula = sheet.formulas.get((df_row, col_idx))
                if formula:
                    ws.cell(row=sheet_row, column=col_idx + 1, value=formula)
                else:
                    ws.cell(
                        row=sheet_row, column=col_idx + 1,
                        value=_cell_value(value),
                    )

    wb.save(str(path))


def _safe_title(name: str) -> str:
    """Excel 工作表名限制：≤31 字符，且不能含 : \\ / ? * [ ]"""
    title = str(name)
    for ch in ':\\/?*[]':
        title = title.replace(ch, "_")
    return title[:31] or "Sheet"


# ==================== 便利函数 ====================

def sync_active_sheet(workbook: WorkbookData, name: str,
                      df: pd.DataFrame) -> WorkbookData:
    """
    用编辑后的 DataFrame 更新工作簿里对应工作表（保留其公式）。

    蜜算当前只编辑一张表，导出前需要把模型里的最新内容写回工作簿对象。
    """
    sheet = workbook.get(name)
    if sheet is None:
        workbook.sheets.append(SheetData(name=name, df=df))
    else:
        sheet.df = df
    return workbook
