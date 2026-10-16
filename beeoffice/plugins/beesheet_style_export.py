# beeoffice/plugins/beesheet_style_export.py
"""
把**视图侧的格式**写进已经生成的 xlsx（openpyxl 后处理）。

## 这一步补的是什么（审计报告 §2.9）
蜜算的格式体系全在视图内存里：
`_cell_formats`（加粗/斜体/下划线/对齐/数字格式）、`_merged_cells`（合并）、
`_cell_comments`（批注）、`_conditional_formats`（数据条/色阶）。
而数据落盘只有"值 + 公式"两条路 —— 上面这些在导出链上**零引用**，
于是：用户自己加的加粗、颜色、对齐、数字格式、合并、批注、条件格式
**保存后全部消失**（模块自述"本刀不解决"）。

## 为什么用"写盘后后处理"而不是改两个写入器
蜜算有**两条**写盘路径（`beesheet_workbook.write_workbook` 更新源工作簿、
`df.to_excel` 新建），如果分别改，两边行为一定会漂移。
这里统一：**写完再打开一次，把样式贴上去** —— 两条路径共用同一段逻辑，
而且可以用 openpyxl 读回来做**往返断言**（本模块的测试就是这么做的）。

## 坐标约定（最容易错的地方，单独写清楚）
视图的 `(row, col)` 是**0 起**，而写出的工作表里 **第 1 行是表头**、
数据从第 2 行开始、列从 A 开始。所以：

    视图 (r, c)  →  工作表 cell(row=r+2, column=c+1)

本模块把这条换算**只放在一个函数里**（`view_to_cell`），避免各处各写一遍。
"""
import logging
from pathlib import Path
from typing import Any, Dict, Optional

#: 视图里的"数字格式"分类 → Excel 的数字格式串
#: （与 `beesheet_model._format_display_value` 的显示规则保持一致：
#:  用户看到什么，写出去就尽量是什么）
NUMBER_FORMAT_CODES = {
    "常规": "General",
    "数值": "#,##0",
    "货币": "¥#,##0",
    "千分位": "#,##0",
    "日期": "yyyy-mm-dd",
    "百分比": "0%",
    "文本": "@",
}

#: 视图里的对齐方式 → openpyxl 的 horizontal
ALIGN_MAP = {
    "left": "left",
    "center": "center",
    "right": "right",
}


def view_to_cell(row: int, col: int):
    """
    视图坐标 → 工作表坐标（**0 起**转 openpyxl 的 1 起，并跳过表头行）。

    唯一的换算点：视图 (0,0) 是第一条数据 → 工作表 (第 2 行, A 列)。
    """
    return int(row) + 2, int(col) + 1


def number_format_code(num_type: str, decimals: int = 2,
                       thousands: bool = False) -> str:
    """
    把视图的"分类 + 小数位数（+千分位）"翻成 Excel 格式串。

    与 `beesheet_model._format_display_value` 的显示规则对齐：
    用户界面上看到的是 `1,234.50` / `¥1,234.50` / `50.00%`，
    写进文件就应当是等价的 Excel 格式，而不是另一个样子。
    """
    kind = str(num_type)
    if kind in ("常规", "文本"):
        return NUMBER_FORMAT_CODES[kind]
    if kind == "日期":
        return NUMBER_FORMAT_CODES["日期"]

    decimals = max(0, int(decimals or 0))
    zeros = ("." + "0" * decimals) if decimals else ""

    if kind == "货币":
        return ("¥#,##0" if thousands else "¥0") + zeros
    if kind in ("数值", "千分位"):
        return ("#,##0" if (thousands or kind == "千分位") else "0") + zeros
    if kind == "百分比":
        return "0" + zeros + "%"
    return "General"


def _apply_cell_formats(ws, formats: Dict[Any, Dict[str, Any]]) -> int:
    """加粗/斜体/下划线/对齐/数字格式。"""
    import copy

    from openpyxl.styles import Alignment, Font

    applied = 0
    for key, fmt in (formats or {}).items():
        try:
            row, col = key
        except (TypeError, ValueError):
            continue
        if not isinstance(fmt, dict) or not fmt:
            continue
        cell = ws.cell(*view_to_cell(row, col))
        try:
            font_kwargs = {}
            if fmt.get("bold"):
                font_kwargs["bold"] = True
            if fmt.get("italic"):
                font_kwargs["italic"] = True
            if fmt.get("underline"):
                font_kwargs["underline"] = "single"
            if font_kwargs:
                # 用 copy 再改属性：直接 `Font(**kwargs)` 会把字号/字体名等
                # 已有属性一起覆盖掉（那是"修一个坏一个"）。
                font = copy.copy(cell.font)
                font.bold = font_kwargs.get("bold", font.bold)
                font.italic = font_kwargs.get("italic", font.italic)
                if "underline" in font_kwargs:
                    font.underline = font_kwargs["underline"]
                cell.font = font

            align = ALIGN_MAP.get(str(fmt.get("align", "")).lower())
            if align:
                cell.alignment = Alignment(horizontal=align)

            num_type = fmt.get("number_format")
            if num_type:
                code = number_format_code(
                    num_type, fmt.get("decimals", 2),
                    bool(fmt.get("thousands", False)),
                )
                if code:
                    cell.number_format = code
            applied += 1
        except Exception as e:  # noqa: BLE001 - 单格失败不该毁掉整次保存
            logging.debug(f"[蜜算] 写单元格格式失败 {key}: {e}")
    return applied


def _has_data_besides_anchor(ws, r1: int, c1: int,
                             n_rows: int, n_cols: int) -> bool:
    """
    合并区里**除左上角之外**是否还有内容？

    ⚠️ 为什么必须有这个检查（实测踩到）：openpyxl 的 `merge_cells` 会**清掉**
    合并区内非左上角单元格的值。视图侧的合并语义是"首格保留、其余置空"，
    所以正常流程下不冲突；但**导入的合并区**或状态不同步时，
    下方真数据会被这次"写格式"静默吃掉 —— 那是用户最不能接受的损失。
    所以：**只要还有数据就跳过合并**（数据优先于外观），并计入 skipped。
    """
    for dr in range(int(n_rows)):
        for dc in range(int(n_cols)):
            if dr == 0 and dc == 0:
                continue
            value = ws.cell(*view_to_cell(int(r1) + dr, int(c1) + dc)).value
            if value is not None and str(value).strip() != "":
                return True
    return False


def _apply_merges(ws, merges: Dict[Any, Any]) -> tuple:
    """
    合并区域。视图存的是 `{(r1,c1): (n_rows, n_cols)}`。

    :return: (已应用, 因"有数据"而跳过)
    """
    applied = 0
    skipped_for_data = 0
    for key, span in (merges or {}).items():
        try:
            r1, c1 = key
            n_rows, n_cols = span
        except (TypeError, ValueError):
            continue
        try:
            if int(n_rows) <= 1 and int(n_cols) <= 1:
                continue
            if _has_data_besides_anchor(ws, r1, c1, n_rows, n_cols):
                skipped_for_data += 1
                logging.warning(
                    f"[蜜算] 合并区 ({r1},{c1}) 内还有数据，**跳过合并**以免丢数据"
                )
                continue
            start = view_to_cell(r1, c1)
            end = view_to_cell(int(r1) + int(n_rows) - 1,
                               int(c1) + int(n_cols) - 1)
            ws.merge_cells(
                start_row=start[0], start_column=start[1],
                end_row=end[0], end_column=end[1],
            )
            applied += 1
        except Exception as e:  # noqa: BLE001
            logging.debug(f"[蜜算] 合并单元格失败 {key}: {e}")
    return applied, skipped_for_data


def _apply_comments(ws, comments: Dict[Any, Any]) -> int:
    """批注（openpyxl 的 Comment）。"""
    from openpyxl.comments import Comment

    applied = 0
    for key, text in (comments or {}).items():
        try:
            row, col = key
        except (TypeError, ValueError):
            continue
        if not str(text or "").strip():
            continue
        try:
            cell = ws.cell(*view_to_cell(row, col))
            cell.comment = Comment(str(text), "BeeOffice")
            applied += 1
        except Exception as e:  # noqa: BLE001
            logging.debug(f"[蜜算] 写批注失败 {key}: {e}")
    return applied


def _apply_conditional(ws, conditional: Dict[Any, Any], row_count: int) -> int:
    """
    条件格式（数据条 / 色阶）。

    视图按**列**记录（`{col: {"type": "data_bars"|..., "min":.., "max":..}}`），
    所以这里作用到该列的**数据区**（第 2 行到第 row_count+1 行）。
    """
    from openpyxl.formatting.rule import ColorScaleRule, DataBarRule

    applied = 0
    for col, spec in (conditional or {}).items():
        try:
            col = int(col)
        except (TypeError, ValueError):
            continue
        if not isinstance(spec, dict) or row_count <= 0:
            continue
        try:
            start = view_to_cell(0, col)
            end = view_to_cell(row_count - 1, col)
            cell_range = (
                f"{ws.cell(*start).coordinate}:{ws.cell(*end).coordinate}"
            )
            kind = str(spec.get("type", ""))
            if kind == "data_bars":
                rule = DataBarRule(
                    start_type="num", start_value=spec.get("min", 0),
                    end_type="num", end_value=spec.get("max", 1),
                    color="638EC6",
                )
            elif kind in ("color_scale", "color_scales"):
                rule = ColorScaleRule(
                    start_type="min", start_color="F8696B",
                    mid_type="percentile", mid_value=50, mid_color="FFEB84",
                    end_type="max", end_color="63BE7B",
                )
            else:
                continue
            ws.conditional_formatting.add(cell_range, rule)
            applied += 1
        except Exception as e:  # noqa: BLE001
            logging.debug(f"[蜜算] 条件格式失败 列{col}: {e}")
    return applied


def _parse_number_format(code: str):
    """
    Excel 数字格式串 → 视图的 `(分类, 小数位数, 千分位)`。

    与 `number_format_code()` 是**互逆**的（不认识的格式返回 None → 跳过，
    绝不猜：猜错会让用户看到一个自己没设过的格式）。
    """
    if not code:
        return None
    code = str(code).strip()
    if code in ("General", "general"):
        return None
    if code == "@":
        return ("文本", 2, False)
    if code.lower().startswith("yyyy") or code.lower().startswith("yy"):
        return ("日期", 2, False)

    import re

    percent = code.endswith("%")
    body = code[:-1] if percent else code
    currency = "¥" in body or "$" in body or "€" in body
    body = body.replace("¥", "").replace("$", "").replace("€", "")
    thousands = "," in body
    body = body.replace(",", "")
    # ⚠️ 必须把 `#` 占位符也剥掉：正向函数产出的是 `¥#,##0.00`
    # （`#,##0` 里有**三个** `#`），只去逗号会剩下 `###0.00`，
    # 正则匹配不上 → 读回时货币/千分位格式**静默丢失**。
    # 这个 bug 是"往返属性测试"抓到的（单测只测了正向，没测反向）。
    body = body.replace("#", "")
    match = re.fullmatch(r"0(?:\.(0+))?", body)
    if not match:
        return None
    decimals = len(match.group(1) or "")

    if percent:
        kind = "百分比"
    elif currency:
        kind = "货币"
    else:
        kind = "数值"
    return (kind, decimals, thousands)


def read_view_styles(path, sheet_name: Optional[str] = None
                     ) -> Dict[str, Dict[Any, Any]]:
    """
    从 xlsx **读回**视图侧格式（格式/合并/批注）。

    ## 为什么必须有这一半
    只写不读等于"存了却看不到"：用户给单元格设了货币格式、保存、重开 →
    文件里格式是对的，但界面显示朴素 —— 看起来就像保存坏了。
    所以保存与打开必须成对。

    ## 已知未读回的项（如实说明）
    **条件格式**不读回（规则类型多、各家的表达方式不一，反向映射容易出错；
    读不回来也不会丢——写盘只**新增**规则、从不删除）。
    需要时按列重新应用一次即可。

    :return: {"formats": {(r,c): {...}}, "merges": {(r1,c1): (n_rows,n_cols)},
              "comments": {(r,c): 文本}}
    """
    empty = {"formats": {}, "merges": {}, "comments": {}}
    try:
        from openpyxl import load_workbook
    except ImportError:
        return empty

    target = Path(path)
    if not target.is_file():
        return empty
    try:
        workbook = load_workbook(str(target))
    except Exception as e:  # noqa: BLE001
        logging.debug(f"[蜜算] 读取样式失败（按无样式处理）: {e}")
        return empty

    result = {"formats": {}, "merges": {}, "comments": {}}
    try:
        ws = (workbook[sheet_name]
              if sheet_name and sheet_name in workbook.sheetnames
              else workbook[workbook.sheetnames[0]])

        # ---------- 单元格格式 ----------
        for row in ws.iter_rows():
            for cell in row:
                r, c = cell.row - 2, cell.column - 1
                if r < 0 or c < 0:
                    continue                       # 表头行没有对应位置
                fmt = {}
                font = cell.font
                if font is not None:
                    if font.bold:
                        fmt["bold"] = True
                    if font.italic:
                        fmt["italic"] = True
                    if font.underline:
                        fmt["underline"] = True
                alignment = cell.alignment
                if alignment is not None and alignment.horizontal in (
                    "left", "center", "right"
                ):
                    fmt["align"] = alignment.horizontal
                parsed = _parse_number_format(cell.number_format)
                if parsed:
                    fmt["number_format"], fmt["decimals"], fmt["thousands"] = parsed
                if fmt:
                    result["formats"][(r, c)] = fmt

        # ---------- 合并 ----------
        for merged_range in ws.merged_cells.ranges:
            r1 = merged_range.min_row - 2
            c1 = merged_range.min_col - 1
            if r1 < 0 or c1 < 0:
                continue                           # 表头里的合并没有对应位置
            result["merges"][(r1, c1)] = (
                merged_range.max_row - merged_range.min_row + 1,
                merged_range.max_col - merged_range.min_col + 1,
            )

        # ---------- 批注 ----------
        for row in ws.iter_rows():
            for cell in row:
                if cell.comment is None:
                    continue
                r, c = cell.row - 2, cell.column - 1
                if r < 0 or c < 0:
                    continue
                text = str(cell.comment.text or "").strip()
                if text:
                    result["comments"][(r, c)] = text
    except Exception as e:  # noqa: BLE001
        logging.warning(f"[蜜算] 读取样式时出错（已尽量读到的部分）: {e}")
    finally:
        try:
            workbook.close()
        except Exception:  # noqa: BLE001
            pass
    return result


def apply_view_styles(path, sheet_name: Optional[str] = None, *,
                      formats=None, merges=None, comments=None,
                      conditional=None, row_count: int = 0) -> Dict[str, int]:
    """
    把视图侧格式写进已存在的 xlsx（就地更新）。

    :param path: 已写好的 xlsx
    :param sheet_name: 目标工作表（None = 第一张）
    :param row_count: 数据行数（条件格式需要知道作用范围）
    :return: 各类计数（**如实**：失败不抛异常，只记 debug 并继续）
    """
    result = {"formats": 0, "merges": 0, "merges_skipped": 0,
              "comments": 0, "conditional": 0}
    if not any((formats, merges, comments, conditional)):
        return result
    try:
        from openpyxl import load_workbook
    except ImportError:
        logging.warning("[蜜算] 没有 openpyxl，跳过格式写入")
        return result

    target = Path(path)
    if not target.is_file():
        logging.debug(f"[蜜算] 文件不存在，跳过格式写入: {target}")
        return result

    try:
        workbook = load_workbook(str(target))
    except Exception as e:  # noqa: BLE001
        logging.warning(f"[蜜算] 打开工作簿写格式失败（已跳过）: {e}")
        return result

    try:
        ws = (workbook[sheet_name] if sheet_name and sheet_name in workbook.sheetnames
              else workbook[workbook.sheetnames[0]])
        result["formats"] = _apply_cell_formats(ws, formats)
        result["merges"], result["merges_skipped"] = _apply_merges(ws, merges)
        result["comments"] = _apply_comments(ws, comments)
        result["conditional"] = _apply_conditional(ws, conditional, row_count)
        workbook.save(str(target))
    except Exception as e:  # noqa: BLE001
        logging.warning(f"[蜜算] 写入格式失败（文件仍是有效数据）：{e}")
    finally:
        try:
            workbook.close()
        except Exception:  # noqa: BLE001
            pass
    return result
