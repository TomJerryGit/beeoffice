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
    从 xlsx **读回**视图侧格式（格式/合并/批注/表格样式/数据验证）。

    ## 为什么必须有这一半
    只写不读等于"存了却看不到"：用户给单元格设了货币格式、保存、重开 →
    文件里格式是对的，但界面显示朴素 —— 看起来就像保存坏了。
    所以保存与打开必须成对。

    ## 已知未读回的项（如实说明）
    **条件格式**不读回（规则类型多、各家的表达方式不一，反向映射容易出错；
    读不回来也不会丢——写盘只**新增**规则、从不删除）。
    需要时按列重新应用一次即可。

    :return: {"formats":…, "merges":…, "comments":…,
              "table_style":…, "validations":…}（没有的部分不出现在结果里）
    """
    empty: Dict[str, Dict[Any, Any]] = {
        "formats": {}, "merges": {}, "comments": {}, "comment_authors": {},
        "table_style": {}, "validations": {}, "named_ranges": {},
    }
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

    result = {"formats": {}, "merges": {}, "comments": {},
              "comment_authors": {}, "named_ranges": {}}
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

        # ---------- 批注（文本 + **作者**）----------
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
                    author = str(cell.comment.author or "").strip()
                    if author:
                        result["comment_authors"][(r, c)] = author

        # ---------- 冻结窗格 ----------
        if ws.freeze_panes:
            result["freeze_panes"] = str(ws.freeze_panes)

        # ---------- 命名区域 ----------
        # 文件里是 `'数据'!$B$2:$B$4`，视图里存的是能直接填进定位框的
        # `B2:B4` 形式（`beesheet._show_go_to` 会把它塞进输入框再解析），
        # 所以这里去掉表名前缀与 `$`。
        try:
            for name in list(workbook.defined_names):
                defined = workbook.defined_names[name]
                attr_text = str(getattr(defined, "attr_text", "") or "").strip()
                if not attr_text or attr_text.startswith("#"):
                    continue
                ref = attr_text.split("!", 1)[-1].replace("$", "")
                # 文件行号 → 视图行号（应用里第 1 行 = 第一条数据）
                ref = _shift_a1_rows(ref, -1)
                if ref:
                    result["named_ranges"][str(name)] = ref
        except Exception as e:  # noqa: BLE001
            logging.debug(f"[蜜算] 读取命名区域失败: {e}")

        # ---------- 表格样式（从填充色反推预设）----------
        # 视图的样式就是"表头色 + 斑马纹色 + 是否斑马纹"，所以能等价重建：
        # 取第一条数据行的填充当作 header_bg、隔行填充当作 stripe_bg。
        # （预设的**名字**不在文件里，也无需还原：模型只用这三个键。）
        table_style = _read_table_style(ws)
        if table_style:
            result["table_style"] = table_style

        # ---------- 数据验证（下拉列表）----------
        validations = _read_data_validations(ws)
        if validations:
            result["validations"] = validations
    except Exception as e:  # noqa: BLE001
        logging.warning(f"[蜜算] 读取样式时出错（已尽量读到的部分）: {e}")
    finally:
        try:
            workbook.close()
        except Exception:  # noqa: BLE001
            pass
    return result


def _qt_color_to_hex(color, *, blend_over_white: bool = False) -> Optional[str]:
    """
    Qt 颜色 → `RRGGBB`（Excel 的填充没有 alpha）。

    ⚠️ 取舍写清楚：视图里的预设色带 alpha（例如表头 220、斑马纹 150），
    而 Excel 的填充是**实色**。直接丢掉 alpha 会让导出的颜色比屏幕上**更深**，
    所以斑马纹这类半透明色按 alpha **与白底混合**，让导出更接近肉眼所见；
    表头色（alpha 220）同样按混合处理，保持一致。

    取不到颜色时返回 None（调用方跳过，不猜）。
    """
    if color is None:
        return None
    try:
        alpha = color.alpha() if hasattr(color, "alpha") else 255
        rgb = (color.red(), color.green(), color.blue())
    except Exception:  # noqa: BLE001
        return None
    if blend_over_white and alpha < 255:
        ratio = max(0.0, min(1.0, alpha / 255.0))
        rgb = tuple(int(round(c * ratio + 255 * (1 - ratio))) for c in rgb)
    return "%02X%02X%02X" % rgb


def _apply_table_style(ws, style, row_count: int, col_count: int) -> int:
    """
    表格整体样式（预设）→ 表头行/斑马纹填充。

    :return: 应用的单元格数

    ⚠️ **重要且反直觉的一点（实测发现，如实标注）**：
    视图的 `_table_style_ref` 在 `beesheet_model.data()` 里是
    `if r == 0: return header_bg` —— 而模型**没有表头行**
    （`rowCount() == _loaded_df` 行数，`r` 直接索引数据），
    所以那个"表头色"实际涂在**第一条数据行**上，不是列名表头。
    本函数**照实复刻屏幕上的样子**（第一条数据行 + 隔行斑马纹），
    不擅自改渲染行为 —— 这样"导出的文件 == 用户看到的表"。
    该 off-by-one 已作为发现记录在审计报告里，等确认后再统一修。
    """
    applied = 0
    if not style:
        return applied
    from openpyxl.styles import PatternFill

    header_hex = _qt_color_to_hex(style.get("header_bg"), blend_over_white=True)
    stripe_hex = _qt_color_to_hex(style.get("stripe_bg"), blend_over_white=True)
    stripe = bool(style.get("stripe"))

    rows = max(0, int(row_count))
    cols = max(0, int(col_count))
    if rows and header_hex:
        fill = PatternFill(fill_type="solid", start_color=header_hex,
                           end_color=header_hex)
        for c in range(cols):
            ws.cell(*view_to_cell(0, c)).fill = fill
            applied += 1
    if rows and stripe and stripe_hex:
        fill = PatternFill(fill_type="solid", start_color=stripe_hex,
                           end_color=stripe_hex)
        for r in range(1, rows):
            if r % 2 == 1:                      # 与模型的 (r % 2 == 1) 一致
                for c in range(cols):
                    ws.cell(*view_to_cell(r, c)).fill = fill
                    applied += 1
    return applied


def _apply_data_validations(ws, validations: Dict[Any, Any]) -> int:
    """
    下拉列表验证（视图 `{(row, col): [选项…]}` → openpyxl 的 list 验证）。

    按**单元格**逐个写：视图就是按单元格记的（delegate 在编辑该格时弹下拉），
    所以不能合并成一个大范围（合并会改变语义：让不该有下拉的格子也有下拉）。
    """
    applied = 0
    if not validations:
        return applied
    from openpyxl.worksheet.datavalidation import DataValidation

    for key, options in (validations or {}).items():
        try:
            row, col = key
        except (TypeError, ValueError):
            continue
        if not isinstance(options, (list, tuple)):
            continue
        cleaned = [str(o).strip() for o in options if str(o).strip()]
        if not cleaned:
            continue
        # 选项里含逗号会破坏 formula1 的引号语法 → 跳过并记录（不写出坏验证）
        if any("," in o for o in cleaned):
            logging.warning(
                f"[蜜算] 单元格({row},{col}) 的下拉选项含逗号，"
                "Excel 列表语法无法表达，已跳过该验证"
            )
            continue
        try:
            validation = DataValidation(
                type="list",
                formula1='"' + ",".join(cleaned) + '"',
                allow_blank=True,
                showDropDown=False,      # False = **显示**下拉箭头（Excel 的反向语义）
            )
            ws.add_data_validation(validation)
            cell = ws.cell(*view_to_cell(row, col))
            validation.add(cell)
            applied += 1
        except Exception as e:  # noqa: BLE001
            logging.debug(f"[蜜算] 写数据验证失败 {key}: {e}")
    return applied


def _fill_rgb(cell) -> Optional[str]:
    """取单元格的实色填充（`RRGGBB`）；没有填充返回 None。"""
    try:
        fill = cell.fill
        if fill is None or fill.fill_type != "solid":
            return None
        color = fill.start_color
        value = getattr(color, "rgb", None)
        if not value or not isinstance(value, str):
            return None
        # openpyxl 给的是 ARGB（如 '00FFB300'）；透明或自动填充要排除
        if value in ("00000000",):
            return None
        return value[-6:]
    except Exception:  # noqa: BLE001
        return None


def _read_table_style(ws) -> Dict[str, Any]:
    """
    从填充色反推"表格样式"（视图只需要 `header_bg`/`stripe_bg`/`stripe`）。

    预设的**名字**不在文件里，也不需要：`beesheet_model` 只按这三个键渲染，
    所以等价重建即可（用户看到的样式完全一致）。
    返回的 QColor 对象供模型直接用（Qt 缺失时返回空 dict，不影响打开文件）。
    """
    header_hex = _fill_rgb(ws.cell(*view_to_cell(0, 0)))
    stripe_hex = _fill_rgb(ws.cell(*view_to_cell(1, 0))) if ws.max_row >= 3 else None
    if not header_hex and not stripe_hex:
        return {}
    try:
        from PySide6.QtGui import QColor
    except ImportError:
        return {}

    result: Dict[str, Any] = {
        "header_bg": QColor(f"#{header_hex}") if header_hex else None,
        "stripe_bg": QColor(f"#{stripe_hex}") if stripe_hex else None,
        "stripe": bool(stripe_hex),
    }
    # 只有斑马纹、没有表头色也要如实反映
    if not header_hex and stripe_hex:
        result["header_bg"] = None
    return result


def _read_data_validations(ws) -> Dict[Any, Any]:
    """
    读回下拉列表验证 → 视图的 `{(row, col): [选项…]}`。

    只认 **list** 类型（本应用就这一种）；其它类型（整数/小数区间等）
    跳过并记日志 —— 不假装读回来了。
    """
    result: Dict[Any, Any] = {}
    try:
        validations = list(getattr(ws.data_validations, "dataValidation", []) or [])
    except Exception:  # noqa: BLE001
        return result

    for validation in validations:
        try:
            if str(getattr(validation, "type", "")).lower() != "list":
                logging.info(
                    f"[蜜算] 跳过非列表型数据验证（type={getattr(validation, 'type', '')}）"
                )
                continue
            formula = str(getattr(validation, "formula1", "") or "").strip()
            if formula.startswith('"') and formula.endswith('"'):
                options = [o.strip() for o in formula[1:-1].split(",")]
            else:
                options = [o.strip() for o in formula.split(",")]
            options = [o for o in options if o]
            if not options:
                continue
            for area in str(validation.sqref).split():
                # ⚠️ `ws['A2']` 返回的是 **Cell**（不是元组），直接 for 会抛
                # `'Cell' object is not iterable` —— 我第一版就是这么写的，
                # 异常被下面的 except 吞成 debug 日志，表现为"验证写进去了却读不回"。
                # 所以必须先归一化再迭代。
                area_cells = ws[area]
                rows = area_cells if isinstance(area_cells, tuple) else (area_cells,)
                for row in rows:
                    cells = row if isinstance(row, tuple) else (row,)
                    for cell in cells:
                        r, c = cell.row - 2, cell.column - 1
                        if r < 0 or c < 0:
                            continue
                        result[(r, c)] = list(options)
        except Exception as e:  # noqa: BLE001
            logging.debug(f"[蜜算] 读取数据验证失败: {e}")
    return result


def _apply_comments(ws, comments: Dict[Any, Any],
                    authors: Optional[Dict[Any, Any]] = None,
                    default_author: str = "") -> int:
    """
    批注（openpyxl 的 Comment），**保留作者**。

    ⚠️ 这里修的是我在第四批引入的一个回归：那时作者**硬编码成 "BeeOffice"**，
    于是"导入一份带批注的表格 → 保存"会把原作者（比如"张三"）**覆盖掉**。
    现在：
      · 视图有该格的作者记录 → 用它；
      · 没有记录但**文件里已有同内容批注** → **原样不动**（保住原作者）；
      · 只有确实是新批注才用默认作者（调用方传 `user_name`）。
    """
    from openpyxl.comments import Comment

    applied = 0
    authors = authors or {}
    for key, text in (comments or {}).items():
        try:
            row, col = key
        except (TypeError, ValueError):
            continue
        if not str(text or "").strip():
            continue
        try:
            cell = ws.cell(*view_to_cell(row, col))
            existing = cell.comment
            if existing is not None and str(existing.text or "") == str(text):
                # 内容没变 → 不要碰，免得把原作者改成默认作者
                continue
            author = str(authors.get(key) or default_author or "").strip()
            if not author:
                author = "BeeOffice"
            cell.comment = Comment(str(text), author)
            applied += 1
        except Exception as e:  # noqa: BLE001
            logging.debug(f"[蜜算] 写批注失败 {key}: {e}")
    return applied


def _shift_a1_rows(ref: str, delta: int) -> str:
    """
    把 A1 风格引用里的**行号**整体偏移（用于"视图行号 ↔ 文件行号"换算）。

    ⚠️ 为什么必须换：应用里 `_named_ranges` 存的是 **A1 风格、行号 = 视图行 + 1**
    （见 `beesheet_data_mixin` 的"从当前选区填充"：`f"{列名}{r1+1}"`），
    而**文件第 1 行是表头**、数据从第 2 行开始 →
    同一块数据在两边相差 1 行。不换算的话，保存后的命名区域会**指错行**。
    """
    import re

    def _bump(match):
        return f"{match.group(1)}{int(match.group(2)) + delta}"

    return re.sub(r"([A-Za-z]{1,3})(\d+)", _bump, str(ref or ""))


def _apply_defined_names(workbook, named_ranges: Dict[str, str]) -> int:
    """
    命名区域 → 工作簿的 defined names。

    视图的 `_named_ranges` 是 `{名称: 引用串}`（如 `{"销量": "B2:B10"}`），
    定位对话框就靠它。原先既不读也不写 → 用户定义的名称**保存后消失**，
    而文件里已有的名称在定位对话框里**也看不到**。

    引用串要带上工作表名（Excel 的 defined name 必须是 `表名!$B$2:$B$10`）——
    调用方传纯单元格引用时这里补上当前表名。
    """
    applied = 0
    if not named_ranges:
        return applied
    try:
        from openpyxl.workbook.defined_name import DefinedName
    except ImportError:
        return applied

    sheet_name = workbook.sheetnames[0] if workbook.sheetnames else ""
    for name, ref in (named_ranges or {}).items():
        name = str(name).strip()
        ref = str(ref or "").strip()
        if not name or not ref:
            continue
        try:
            # 视图 A1 引用（行号 = 视图行+1）→ 文件引用（数据从第 2 行开始）
            attr_text = _shift_a1_rows(ref, +1)
            if "!" not in attr_text:
                quoted = sheet_name.replace("'", "''")
                attr_text = f"'{quoted}'!{attr_text}"
            try:
                workbook.defined_names.add(DefinedName(name, attr_text=attr_text))
            except AttributeError:            # openpyxl 3.1 的字典式 API
                workbook.defined_names[name] = DefinedName(
                    name, attr_text=attr_text
                )
            applied += 1
        except Exception as e:  # noqa: BLE001
            logging.debug(f"[蜜算] 写命名区域失败 {name}: {e}")
    return applied


def _apply_freeze_panes(ws, freeze: Optional[str]) -> bool:
    """
    冻结窗格（如 `"A2"` = 冻结首行）。

    ⚠️ 说明清楚范围：蜜算**界面上的冻结功能目前是禁用的**
    （`beesheet.py` 注明"避免表头丢失 bug"），所以这里做的是
    **状态保留**：文件里原本有的冻结窗格，在应用保存后仍然保持；
    用户在 Excel 里设的、或用应用打开过的文件都受益。
    实测：工作簿路径本来就保留它（openpyxl 只改 `.value`），
    但 `df.to_excel` 的新建路径会丢 —— 所以写这一手是必要的兜底。
    """
    if not freeze:
        return False
    try:
        ws.freeze_panes = str(freeze)
        return True
    except Exception as e:  # noqa: BLE001
        logging.debug(f"[蜜算] 写冻结窗格失败 {freeze}: {e}")
        return False


#: 视图图表类型 → openpyxl 图表类
_CHART_CLASSES = {
    "bar": "BarChart",
    "line": "LineChart",
    "pie": "PieChart",
    "area": "AreaChart",
    "scatter": "ScatterChart",
    "radar": "RadarChart",
}


def _apply_charts(ws, charts, fresh_file: bool = False) -> int:
    """
    把**应用内生成的图表**写成原生 Excel 图表。

    ## 为什么需要（审计里的"图表"缺口）
    蜜算的图表功能是 **matplotlib 预览**（弹窗 + 另存 PNG），
    **从来没有进过 xlsx** —— 用户在应用里"生成图表"，工作簿里其实什么都没有。
    这里把生成时的规格（类型 + 数据区域）写成 openpyxl 的原生图表，
    保存后就真在文件里了（Excel/WPS 打开能看到、能继续编辑）。

    ## 重复与丢失的取舍（踩过坑，写清楚）
    蜜算有**两条**写盘路径，对图表的处理完全不同：
      · **工作簿路径**（有源文件）：每次保存都从**源文件**重开，
        上一次写进去的图表**天然还在** → 只写还没写过的规格，
        否则保存两次就有两张图；
      · **`df.to_excel` 路径**（CSV 导入/新建/透视）：每次都**重建文件** →
        之前写的图表全没了，所以**必须把全部规格再写一遍**。
    所以这里用 `fresh_file` 区分，并用规格上的 `written` 标记记录是否写过。
    （我第一版是"写成功就清空规格"，结果 `df.to_excel` 路径第二次保存
    图表**直接消失** —— 比重复更糟，被测试当场抓到。）

    ## 已知边界
    openpyxl **读不回**图表，所以规格只存在于本次会话；已写进文件的图表
    由"源工作簿保留"机制继续存在。
    """
    applied = 0
    if not charts:
        return applied
    try:
        from openpyxl.chart import (
            AreaChart, BarChart, LineChart, PieChart, RadarChart,
            Reference, ScatterChart,
        )
    except ImportError:
        return applied

    classes = {
        "bar": BarChart, "line": LineChart, "pie": PieChart,
        "area": AreaChart, "scatter": ScatterChart, "radar": RadarChart,
    }

    for spec in charts or []:
        if not isinstance(spec, dict):
            continue
        # 工作簿路径下，已经写过的规格不要再写（源文件里已经有了）
        if not fresh_file and spec.get("written"):
            continue
        kind = str(spec.get("type", "")).lower()
        cls = classes.get(kind)
        if cls is None:
            logging.info(f"[蜜算] 暂不支持把图表类型 {kind} 写入 Excel，已跳过")
            continue
        try:
            rows = spec.get("rows") or (0, 0)
            cols = spec.get("cols") or (0, 0)
            r1, r2 = int(rows[0]), int(rows[1])
            c1, c2 = int(cols[0]), int(cols[1])
            data = Reference(
                ws,
                min_col=view_to_cell(0, c1)[1],
                max_col=view_to_cell(0, c2)[1],
                min_row=view_to_cell(r1, 0)[0],
                max_row=view_to_cell(r2, 0)[0],
            )
            chart = cls()
            chart.title = str(spec.get("title") or "蜜蜂图表")
            chart.add_data(data, titles_from_data=True)
            if kind != "pie" and c2 > c1:
                # 第一列当分类轴（与应用内的取法一致：labels 取 cols[0]）
                cats = Reference(
                    ws,
                    min_col=view_to_cell(0, c1)[1],
                    min_row=view_to_cell(r1, 0)[0],
                    max_row=view_to_cell(r2, 0)[0],
                )
                chart.set_categories(cats)
            anchor = spec.get("anchor")
            if not anchor:
                anchor = ws.cell(*view_to_cell(r1, c2 + 1)).coordinate
            ws.add_chart(chart, str(anchor))
            spec["written"] = True          # 记下来，供工作簿路径去重
            applied += 1
        except Exception as e:  # noqa: BLE001
            logging.warning(f"[蜜算] 写图表失败（已跳过）: {e}")
    return applied


def apply_view_styles(path, sheet_name: Optional[str] = None, *,
                      formats=None, merges=None, comments=None,
                      conditional=None, table_style=None,
                      validations=None, comment_authors=None,
                      default_comment_author: str = "",
                      named_ranges=None, freeze_panes=None,
                      charts=None, charts_fresh_file: bool = False,
                      row_count: int = 0,
                      col_count: int = 0) -> Dict[str, int]:
    """
    把视图侧格式写进已存在的 xlsx（就地更新）。

    :param path: 已写好的 xlsx
    :param sheet_name: 目标工作表（None = 第一张）
    :param row_count: 数据行数（条件格式/表格样式需要知道作用范围）
    :param col_count: 列数（表格样式需要）
    :return: 各类计数（**如实**：失败不抛异常，只记 debug 并继续）
    """
    result = {"formats": 0, "merges": 0, "merges_skipped": 0,
              "comments": 0, "conditional": 0, "table_style": 0,
              "validations": 0, "named_ranges": 0, "freeze": 0, "charts": 0}
    if not any((formats, merges, comments, conditional, table_style,
                validations, named_ranges, freeze_panes, charts)):
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
        result["comments"] = _apply_comments(
            ws, comments, comment_authors, default_comment_author
        )
        result["conditional"] = _apply_conditional(ws, conditional, row_count)
        result["table_style"] = _apply_table_style(
            ws, table_style, row_count or ws.max_row - 1, col_count or ws.max_column
        )
        result["validations"] = _apply_data_validations(ws, validations)
        result["named_ranges"] = _apply_defined_names(workbook, named_ranges)
        result["freeze"] = 1 if _apply_freeze_panes(ws, freeze_panes) else 0
        result["charts"] = _apply_charts(ws, charts, charts_fresh_file)
        workbook.save(str(target))
    except Exception as e:  # noqa: BLE001
        logging.warning(f"[蜜算] 写入格式失败（文件仍是有效数据）：{e}")
    finally:
        try:
            workbook.close()
        except Exception:  # noqa: BLE001
            pass
    return result
