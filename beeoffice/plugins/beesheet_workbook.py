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
    #: 读入时表格的范围 (行数, 列数)，**不含表头**。
    #: 用途：写回时只清理"原本属于表格、现在已不在表格里"的格子，
    #: 避免把表格**之外**的内容（备注、第二个表格）一并清掉。
    original_shape: Tuple[int, int] = (0, 0)

    def formula_count(self) -> int:
        return len(self.formulas)


@dataclass
class WorkbookData:
    """一个完整工作簿，保序。"""

    sheets: List[SheetData] = field(default_factory=list)
    #: 首张表名（蜜算当前只编辑一张，其余原样保留待写回）
    active: str = ""
    #: 源文件路径。有它才能"打开源工作簿只更新值"，
    #: 从而保留合并区域/条件格式/数据验证/冻结窗格/图表/数字格式。
    source: Optional[str] = None

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

#: 超过该大小的 xlsx 改用 calamine（Rust）读值；小文件保持 openpyxl 路径不变，
#: 避免类型/日期解析细节变化影响既有保真测试。
#: 实测 30 万行 × 13 列（25.4 MB）：openpyxl 读取 2.7–5 分钟，
#: calamine 约 12–25 秒（v5.0.17 大表支持）。
_CALAMINE_MIN_BYTES = 8 * 1024 * 1024
#: 文件不大但**声明**行数超过该值时也走 calamine（稀疏大表；见 _declared_row_count）
_CALAMINE_MIN_ROWS = 50_000


def _calamine_available() -> bool:
    """python-calamine 是否可用（可选依赖；缺失时自动回退 openpyxl）。"""
    try:
        import python_calamine  # noqa: F401

        return True
    except ImportError:
        return False


def _declared_row_count(path: Path) -> int:
    """从 xlsx 的 `<dimension ref="A1:M200001">` 快速读出声明行数。

    有些大表是**稀疏**的（磁盘才 2.3 MB，但声明 20 万行、塞满空样式行），
    只看文件大小会误判成"小文件"而走 openpyxl（实测 10.4 s，calamine 1.4 s）。
    只读每个 worksheet XML 开头 4 KB（dimension 在文档最前面），毫秒级。
    """
    try:
        import zipfile

        import re as _re

        with zipfile.ZipFile(path) as archive:
            names = [
                n for n in archive.namelist()
                if _re.match(r"xl/worksheets/sheet\d+\.xml$", n)
            ]
            best = 0
            for name in names[:8]:
                head = archive.read(name)[:4096]
                match = _re.search(
                    rb'<dimension[^>]*ref="([^"]+)"', head
                )
                if not match:
                    continue
                ref = match.group(1).decode("ascii", "ignore")
                # ref 可能是 "A1"（单格）或 "A1:M200001"（区域）→ 取右下角行号
                last = ref.rsplit(":", 1)[-1]
                row_match = _re.match(r"[A-Za-z]+(\d+)", last)
                if row_match:
                    best = max(best, int(row_match.group(1)))
            return best
    except Exception:  # noqa: BLE001 - 探测失败就退回按大小判断
        return 0


def _use_calamine(path: Path) -> bool:
    """是否对该文件走 calamine 快速读值路径（OOXML 且"大"文件）。"""
    try:
        if str(path).lower().endswith(".xls"):
            return False
        if not _calamine_available():
            return False
        if Path(path).stat().st_size >= _CALAMINE_MIN_BYTES:
            return True
        # 稀疏大表：磁盘不大但声明行数很多，同样走 calamine
        return _declared_row_count(path) >= _CALAMINE_MIN_ROWS
    except OSError:
        return False


#: 行数限制不超过该值时（两阶段载入的阶段 1），宁可走 openpyxl 的**按行读取**：
#: 实测 25 万行文件只读前 500 行，openpyxl 1.1 s、calamine 13.7 s —— calamine
#: 会先解析整个文件，反而不适合"先显示前几百行"的场景。
_CALAMINE_MAX_SKIP_ROWS = 5000


def _read_values_frames(path: Path, engine: str, max_rows: Optional[int]):
    """读全部工作表的值；大 xlsx 优先 calamine，失败或无依赖时回退原引擎。

    `max_rows` 很小（两阶段载入的阶段 1）时保持 openpyxl 按行读取，
    避免 calamine "先解析整份文件"导致首屏反而更慢。
    """
    preview = (
        max_rows is not None and max_rows <= _CALAMINE_MAX_SKIP_ROWS
    )
    if engine == "openpyxl" and not preview and _use_calamine(path):
        try:
            return pd.read_excel(
                path, sheet_name=None, engine="calamine", nrows=max_rows
            )
        except (ImportError, ValueError, TypeError, AttributeError,
                NotImplementedError, RuntimeError) as e:
            logging.warning(f"calamine 读取失败，回退 openpyxl（{path.name}）: {e}")
    return pd.read_excel(
        path, sheet_name=None, engine=engine, nrows=max_rows
    )


def pick_excel_engine(path) -> str:
    """
    按扩展名选 pandas 的 Excel 读取引擎。

    ⚠️ 这条修的是一个"**假装支持**"（审计报告 §2.10）：
    打开对话框与 `SHEET_EXTENSIONS` 都列了 `.xls`，但读路径**写死**
    `engine='openpyxl'` —— 而 openpyxl **只认 `.xlsx`**（二进制 BIFF 的 `.xls`
    会直接报错）；`requirements.txt` 里声明了 `xlrd` 却**全仓无人调用**。
    结果：用户按提示选一个 `.xls`，必然拿到"导入失败"。

    `xlrd` 只支持 `.xls`（2.x 起不再支持 `.xlsx`），正好与本函数互补。
    没有 xlrd 时给**明确可操作**的错误，而不是让 pandas 抛一句难懂的话。

    :return: "xlrd" 或 "openpyxl"
    """
    if not str(path).lower().endswith(".xls"):
        return "openpyxl"
    try:
        import xlrd  # noqa: F401

        return "xlrd"
    except ImportError:
        raise RuntimeError(
            "读取旧版 .xls 需要 xlrd：pip install xlrd（.xlsx 不需要它）"
        )


def read_workbook(path, max_rows: Optional[int] = None) -> WorkbookData:
    """
    读**全部**工作表与每格公式。

    :param path: .xlsx / .xlsm / .xls 路径
    :param max_rows: 每张表最多读多少行（None = 不限）
    :return: WorkbookData
    """
    path = Path(path)
    if not HAS_OPENPYXL:
        raise RuntimeError("需要 openpyxl 才能读写 xlsx")
    # 引擎按扩展名选（.xls → xlrd），见 pick_excel_engine()
    engine = pick_excel_engine(path)

    # 值：pandas 读全部工作表（pandas>=2.0 返回 dict，保序）。
    # 大 xlsx（>=8 MB）优先走 calamine，避免 openpyxl 逐格解析数分钟。
    frames: Dict[str, pd.DataFrame] = _read_values_frames(
        path, engine, max_rows
    )

    # 公式只对 OOXML 有效：`_read_formulas` 依赖 zip+XML，
    # 二进制 BIFF 的 .xls 走不通（读不到公式不算错误，静默给空即可）。
    formulas_by_sheet = {} if engine != "openpyxl" else _read_formulas(path)

    sheets: List[SheetData] = []
    for name, df in frames.items():
        sheets.append(
            SheetData(
                name=str(name),
                df=df,
                formulas=formulas_by_sheet.get(str(name), {}),
                original_shape=(len(df), len(df.columns)),
            )
        )

    active = sheets[0].name if sheets else ""
    return WorkbookData(
        sheets=sheets, active=active, source=str(path.resolve())
    )


def _sheets_possibly_having_formulas(path: Path) -> Dict[str, bool]:
    """
    字节级预检：每张工作表的 XML 里**是否存在** `<f`（公式元素）。

    为什么需要（P0-B 实测）
    -----------------------
    `_read_formulas()` 用 openpyxl 逐格遍历来找公式，在 5000×50（25 万格）上要
    **2634.9 ms**。但绝大多数数值型表格**一个公式都没有**（基准文件实测 0 个）。

    于是先做一次"存在性"检查：把 worksheet XML 当字节读进来找 `<f`，
    实测 **29.9 ms**（比逐格扫描快约 90 倍）；找不到就**整张表跳过**，
    公式字典留空 —— 写回路径据此按"普通值"处理，本来也确实没有公式要保。

    只判"有没有"，**不解析公式内容**：真正的解析仍交给 openpyxl，
    这样可以完整保留共享公式（shared formula）等复杂情形的既有正确性。

    映射方式：解析 `xl/workbook.xml` 的 `<sheet name r:id>` 与
    `xl/_rels/workbook.xml.rels`，**按关系精确映射到部件路径**，
    不靠"sheet1.xml 就是第一张表"这种顺序假设。

    :return: {表名: 是否可能含公式}；**解析失败时返回空 dict**，
        调用方应据此退回"全表扫描"（宁可慢，不能漏公式）。
    """
    import zipfile

    ns_main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    ns_rel = ("http://schemas.openxmlformats.org/officeDocument/2006/"
              "relationships")

    try:
        from lxml import etree

        with zipfile.ZipFile(path) as archive:
            workbook_xml = etree.fromstring(archive.read("xl/workbook.xml"))
            rels_xml = etree.fromstring(
                archive.read("xl/_rels/workbook.xml.rels")
            )
            rid_to_target = {
                rel.get("Id"): rel.get("Target") for rel in rels_xml
            }

            result: Dict[str, bool] = {}
            for sheet in workbook_xml.iter(f"{{{ns_main}}}sheet"):
                name = sheet.get("name")
                rid = sheet.get(f"{{{ns_rel}}}id")
                target = rid_to_target.get(rid) or ""
                if not name or not target:
                    continue
                # Target 可能是 "worksheets/sheet1.xml" 或 "/xl/worksheets/..."
                if target.startswith("/"):
                    part = target.lstrip("/")
                else:
                    part = "xl/" + target.lstrip("/")
                try:
                    data = archive.read(part)
                except KeyError:
                    continue
                result[name] = b"<f" in data
            return result
    except Exception as e:  # noqa: BLE001 - 预检失败不影响正确性，全表扫描兜底
        logging.debug(f"公式存在性预检失败，将全表扫描: {e}")
        return {}


def _read_formulas(path: Path) -> Dict[str, Dict[Tuple[int, int], str]]:
    """
    用 openpyxl 扫出每张表的公式（保持公式字符串，不求值）。

    P0-B：先用 `_sheets_possibly_having_formulas()` 做字节级预检，
    **只对"确实含 `<f`"的表做逐格扫描**（5000×50 上这一步要 2.6 秒，
    而实测绝大多数数值表格一个公式都没有）。

    :return: {表名: {(df 行, df 列): 公式}}
    """
    result: Dict[str, Dict[Tuple[int, int], str]] = {}
    presence = _sheets_possibly_having_formulas(path)
    # 预检明确"所有表都没有公式"时，连 openpyxl 工作簿都不必加载：
    # 大表实测加载骨架要 10+ 秒，而绝大多数数值表一个公式都没有。
    if presence and not any(presence.values()):
        logging.debug("[_read_formulas] 全部工作表预检无公式，跳过 openpyxl 扫描")
        return result

    try:
        wb = load_workbook(path, data_only=False, read_only=True)
    except Exception as e:  # noqa: BLE001 - 读不到公式不应让导入整体失败
        logging.warning(f"读取公式失败（将按无公式处理）: {e}")
        return result

    try:
        for name in wb.sheetnames:
            # 预检明确说"没有公式" → 整张表跳过（这是本刀的性能收益所在）。
            # 预检失败时 presence 为空 dict，`.get()` 返回 None ≠ False，
            # 于是仍会扫描 —— 宁可慢，不能漏公式。
            if presence.get(str(name)) is False:
                logging.debug(f"[_read_formulas] {name} 预检无公式，跳过扫描")
                continue

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


def write_workbook(workbook: WorkbookData, path, *,
                   preserve_structure: bool = True) -> str:
    """
    把工作簿写回 .xlsx。

    **优先"打开源工作簿，只更新单元格值"**（`preserve_structure=True` 且有源文件）：
    这样合并区域、条件格式、数据验证、冻结窗格、图表、数字格式等**非数据属性**
    全部天然保留 —— 它们是 openpyxl 不碰的东西，因为我们只改 `.value`。

    没有源文件时（CSV 导入、新建表格、数据透视结果等）退回"新建工作簿"。

    :return: "updated"（在原结构上更新）或 "created"（新建）
    """
    if not HAS_OPENPYXL:
        raise RuntimeError("需要 openpyxl 才能读写 xlsx")

    source = workbook.source
    if preserve_structure and source and Path(source).is_file():
        try:
            _update_existing(workbook, path)
            return "updated"
        except Exception as e:  # noqa: BLE001 - 不能因为保结构失败就不导出
            logging.warning(
                f"在原结构上更新失败，退回新建工作簿: {e}"
            )

    _write_new(workbook, path)
    return "created"


def _update_existing(workbook: WorkbookData, path) -> None:
    """
    打开源工作簿，逐表更新单元格值后另存为 `path`。

    关键点：
      - `load_workbook()` 默认 `data_only=False`，因此**公式字符串被保留**；
        若用 data_only=True 加载，保存时公式会被缓存值取代而丢失。
      - 公式格写回公式字符串，不写值。
      - 只清理"原表格范围内、现已不属于表格"的格子，**不碰表格外的内容**。
    """
    wb = load_workbook(workbook.source)      # 默认 data_only=False

    for sheet in workbook.sheets:
        title = _safe_title(sheet.name)
        if title in wb.sheetnames:
            ws = wb[title]
        else:
            ws = wb.create_sheet(title=title)
        _update_sheet_values(ws, sheet)

    wb.save(str(path))


def _readonly_merged_coords(ws) -> set:
    """
    返回合并区域里**不能直接写**的坐标（即除左上角锚点以外的格子）。

    为什么必须避开：openpyxl 里合并区域内的非锚点格子是 `MergedCell`，
    给它赋值会抛 `AttributeError: 'MergedCell' object attribute 'value'
    is read-only`。

    注意这个坑曾经被"另一个坑"掩盖：早先代码用
    `ws.cell(row, col, value=None)`（空操作），恰好不会对合并格赋值，
    所以没报错；一旦改成正确的 `.value = ...` 写法就会暴露。
    """
    coords = set()
    for rng in list(ws.merged_cells.ranges):
        try:
            min_col, min_row, max_col, max_row = rng.bounds
        except Exception:  # pragma: no cover - 罕见范围对象
            continue
        for row in range(min_row, max_row + 1):
            for col in range(min_col, max_col + 1):
                if (row, col) != (min_row, min_col):
                    coords.add((row, col))
    return coords


def _update_sheet_values(ws, sheet: SheetData) -> None:
    """把 DataFrame 的值写进既有工作表的对应格子（保留其它一切）。"""
    df = sheet.df
    columns = list(df.columns)
    n_cols = len(columns)
    n_rows = len(df)
    merged = _readonly_merged_coords(ws)

    # 表头（第 1 行）
    for col_idx, col_name in enumerate(columns, start=1):
        if (1, col_idx) in merged:
            continue
        ws.cell(row=1, column=col_idx).value = str(col_name)

    # 数据（第 2 行起）
    for df_row, (_, row) in enumerate(df.iterrows()):
        sheet_row = df_row + 2
        values = row.tolist()
        for col_idx in range(n_cols):
            col = col_idx + 1
            if (sheet_row, col) in merged:
                continue              # 合并格不可写，交给锚点单元格承载
            formula = sheet.formulas.get((df_row, col_idx))
            # ⚠️ 必须用 `.value = ...` 赋值，**不能**用
            # `ws.cell(row, col, value=x)`：openpyxl 的 `cell()` 在
            # `value is None` 时**什么都不做**，于是"清空单元格"会静默失效
            # （实测：用户删掉的一行仍留在文件里）。
            cell = ws.cell(row=sheet_row, column=col)
            if formula:
                cell.value = formula
            else:
                value = values[col_idx] if col_idx < len(values) else None
                cell.value = _cell_value(value)

    _clear_stale_cells(ws, sheet, n_rows, n_cols, merged)


def _clear_stale_cells(ws, sheet: SheetData, n_rows: int, n_cols: int,
                       merged: set = frozenset()):
    """
    清掉"原本属于表格、现在不在表格里"的格子（用户删了行/列的情况）。

    只在 `original_shape` 记录的矩形内清理，并且**从不删除整行/整列** ——
    删行会让合并区域、图表引用等结构失效，风险远大于收益。

    ⚠️ 关于"表格之外的内容"：实测发现 pandas 会按**已用区域**判断表格范围，
    因此工作表下方/右方的说明文字、第二个表格都会被当作**数据行**吸收进
    DataFrame（实测：一个只写了 3 行数据的表，因为第 20 行有一句备注，
    读出来是 **19 行**）。所以"表格之外"对本模块而言并不是可辨识的概念；
    真正的保护是——只动记录下来的矩形、且不删结构。
    """
    old_rows, old_cols = sheet.original_shape
    for df_row in range(old_rows):
        sheet_row = df_row + 2
        if df_row >= n_rows:
            col_start = 0                 # 整行已不在新表格里
        else:
            col_start = n_cols            # 只有多出来的列需要清理
        for col_idx in range(col_start, old_cols):
            if (df_row, col_idx) in sheet.formulas:
                continue                  # 保留公式
            if (sheet_row, col_idx + 1) in merged:
                continue                  # 合并格不可写
            # 同上：必须用 `.value = None`；`ws.cell(..., value=None)` 是空操作
            ws.cell(row=sheet_row, column=col_idx + 1).value = None


def _write_new(workbook: WorkbookData, path) -> None:
    """新建工作簿（无源文件时的路径）。"""
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
