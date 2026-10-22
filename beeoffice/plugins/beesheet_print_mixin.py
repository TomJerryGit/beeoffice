# beeoffice/plugins/beesheet_print_mixin.py
"""
蜜算的**打印 / 打印预览**（P1-B ★★★）。

为什么要有它
------------
实机清点发现：打印只实现在**蜜写**（工具栏 + Ctrl+P + `QPrintPreviewDialog`），
**蜜算 0 处、蜜演 0 处** —— 表格打印是办公刚需，此前完全没有入口。

表格不能照搬蜜写那条"`QTextDocument.print_()`"的简单路径（表格不是文本文档），
必须自己用 `QPainter` 分页绘制。因此本模块实现：

  · **分页**：按页面可用高度算每页行数，超出自动 `newPage()`
  · **重复标题行**：每页都重画数据区第一行（跨页时最实用的一项）
  · **缩放适应页宽**：列宽按比例压到页宽内（列很多时不至于被截掉）
  · **网格线** + **行号/列标**（A、B、C…）
  · **页脚**：文件名 + 工作表名 + `第 X / Y 页`
  · 横向页：列很多时自动切横向

**可测性设计**：把"取数"（`_collect_print_data`）与"绘制"（`_render_sheet_to`）
分开。绘制通过 `QPrinter` 的 **PDF 输出**跑，测试用 PyMuPDF 读回页面数与文字，
就能断言"分页对不对""标题行是否每页都有"—— 不需要真实打印机，也不需要肉眼看。
"""
import logging
import math

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPageLayout, QPageSize, QPainter, QPen

#: 打印时的尺寸参数（毫米）—— 表格排版用固定高度，保证跨页行数可预期
ROW_HEIGHT_MM = 6.0
HEADER_HEIGHT_MM = 7.5
MARGIN_MM = 12.0
MIN_COL_WIDTH_MM = 12.0
#: 单张表打印的行数上限（避免几十万行直接送去打印）
MAX_PRINT_ROWS = 5000

#: R8：缩放模式（对齐 WPS"缩放到一页/适应 N 页"）
FIT_NONE = "none"          # 不缩放：超宽按列横向分页
FIT_WIDTH = "width"        # 适应 1 页宽（默认，保持既有行为）
FIT_HEIGHT = "height"      # 适应 1 页高
FIT_PAGE = "page"          # 缩放到 1 页（宽高都塞进一页）

#: 缩放到这个比例以下就在页脚提醒"可能难以阅读"（WPS 也会提示）
TINY_SCALE_WARN = 0.35

#: 界面上的中文标签（顺序即下拉框顺序）
FIT_LABELS = [
    (FIT_PAGE, "缩放到 1 页（整表塞进一页）"),
    (FIT_WIDTH, "适应 1 页宽（默认）"),
    (FIT_HEIGHT, "适应 1 页高"),
    (FIT_NONE, "不缩放（超宽自动分页）"),
]


class SheetPrintMixin:
    """蜜算打印 / 打印预览。"""

    # ==================================================================
    # 打印区域（4.5，2026-10-22）
    # ==================================================================
    def _used_area_bounds(self):
        """返回已用区域 `(start_row, end_row, start_col, end_col)`（视图 0 基、end 不含）。"""
        model = getattr(self, "model", None)
        df = getattr(model, "_full_df", None) if model is not None else None
        if df is None and model is not None:
            df = getattr(model, "df", None)
        if df is None or getattr(df, "empty", True):
            return None
        try:
            import numpy as np
            import pandas as _pd

            probe = df.replace("", _pd.NA)
            mask = probe.notna().to_numpy()
            rows_any = mask.any(axis=1)
            cols_any = mask.any(axis=0)
            if not rows_any.any() or not cols_any.any():
                return None
            last_row = int(np.nonzero(rows_any)[0].max()) + 1
            last_col = int(np.nonzero(cols_any)[0].max()) + 1
            return (0, last_row, 0, last_col)
        except Exception:  # noqa: BLE001
            return (0, len(df), 0, len(df.columns))

    def _set_print_area(self, rect=None):
        """
        设置打印区域：`rect=(start_row, end_row, start_col, end_col)` 视图坐标，
        end 不含；不传时用当前选区，选区无效时用已用区域。
        """
        if rect is None:
            try:
                selection = self.table_view.selectionModel().selection()
                if selection and not selection.isEmpty():
                    r = selection[0]
                    rect = (r.top(), r.bottom() + 1, r.left(), r.right() + 1)
            except Exception:  # noqa: BLE001
                rect = None
        if rect is None:
            rect = self._used_area_bounds()
        if not rect:
            self._set_status("没有可设置的打印区域", 3000)
            return False
        start_row, end_row, start_col, end_col = (int(v) for v in rect)
        if end_row <= start_row or end_col <= start_col:
            self._set_status("打印区域为空", 3000)
            return False
        self._print_area = (start_row, end_row, start_col, end_col)
        self._set_status(
            f"📐 已设置打印区域：第 {start_row + 1}–{end_row} 行 × "
            f"{end_col - start_col} 列（保存后随文件保留）", 5000
        )
        try:
            self.contentChanged.emit()
        except Exception:  # noqa: BLE001
            pass
        return True

    def _set_print_area_from_selection(self):
        return self._set_print_area()

    def _clear_print_area(self):
        self._print_area = None
        self._set_status("已取消打印区域", 3000)
        try:
            self.contentChanged.emit()
        except Exception:  # noqa: BLE001
            pass

    # ==================================================================
    # 取数（不依赖 Qt 绘制，便于测试）
    # ==================================================================
    def _collect_print_data(self):
        """
        取出要打印的矩形区域。

        规则：
          · 选中了多个单元格 → 只打印选中区域（用户预期如此）
          · 否则打印**有数据的范围**（注意：模型会把数据补齐到默认行数，
            所以**不能**直接拿 `len(df)` 当已用区域，否则会打印几百行空白 —— 实测踩过）
          · 行数超过 `MAX_PRINT_ROWS` 时截断（页脚会注明）

        :return: {"headers": [列标...], "rows": [(行号, [值...]), ...],
                  "sheet": 工作表名, "truncated": int, "total_rows": int}
        """
        model = getattr(self, "model", None)
        sheet_name = getattr(self, "current_sheet_name", "") or "工作表"
        empty = {"headers": [], "rows": [], "sheet": sheet_name,
                 "truncated": 0, "total_rows": 0}
        if model is None:
            return empty

        # **用 _full_df 取范围**：`model.df` 只含"已加载分块"，
        # 大文件时会漏；`_full_df` 才是完整数据（含为编辑区补的空行）。
        df = getattr(model, "_full_df", None)
        if df is None:
            df = getattr(model, "df", None)
        if df is None or getattr(df, "empty", True):
            return empty

        from beeoffice.plugins.beesheet_utils import col_index_to_name

        total_rows_all, total_cols_all = len(df), len(df.columns)

        # ---- 已用区域：去掉补齐用的空行/空列（**向量化**，避免逐格 Python 循环）----
        last_row = 0          # 1 起，0 表示没有内容
        last_col = 0
        try:
            import numpy as np
            import pandas as _pd

            # 空串也算"空"（模型里空单元格常是 ""）
            probe = df.replace("", _pd.NA)
            mask = probe.notna().to_numpy()
            rows_any = mask.any(axis=1)
            cols_any = mask.any(axis=0)
            if rows_any.any():
                last_row = int(np.nonzero(rows_any)[0].max()) + 1
            if cols_any.any():
                last_col = int(np.nonzero(cols_any)[0].max()) + 1
        except Exception as e:  # noqa: BLE001
            logging.debug(f"[print] 计算已用区域失败，改用整块: {e}")
            last_row, last_col = total_rows_all, total_cols_all
        if last_row == 0 or last_col == 0:
            return empty

        # ---- 范围：显式打印区域 > 选中多格 > 已用区域 ----
        start_row, start_col = 0, 0
        end_row, end_col = last_row, last_col
        area = getattr(self, "_print_area", None)
        if area:
            try:
                a_row, a_end_row, a_col, a_end_col = (int(v) for v in area)
                start_row = max(0, min(a_row, last_row))
                end_row = max(start_row + 1, min(a_end_row, last_row))
                start_col = max(0, min(a_col, last_col))
                end_col = max(start_col + 1, min(a_end_col, last_col))
            except Exception as e:  # noqa: BLE001
                logging.debug(f"[print] 打印区域无效，改用已用区域: {e}")
        else:
            try:
                selection = self.table_view.selectionModel().selection()
                if selection and not selection.isEmpty():
                    rect = selection[0]
                    if rect.isValid() and (
                        rect.top() != rect.bottom()
                        or rect.left() != rect.right()
                    ):
                        start_row = max(0, rect.top())
                        end_row = min(last_row, rect.bottom() + 1)
                        start_col = max(0, rect.left())
                        end_col = min(last_col, rect.right() + 1)
            except Exception as e:  # noqa: BLE001 - 取不到选区就按已用区域
                logging.debug(f"[print] 读取选区失败，按已用区域打印: {e}")

        total_rows = max(0, end_row - start_row)
        truncated = 0
        if total_rows > MAX_PRINT_ROWS:
            truncated = total_rows - MAX_PRINT_ROWS
            end_row = start_row + MAX_PRINT_ROWS

        headers = [col_index_to_name(c) for c in range(start_col, end_col)]

        rows = []
        for r in range(start_row, end_row):
            values_out = []
            for c in range(start_col, end_col):
                try:
                    value = model._value_at(r, c)
                except Exception:  # noqa: BLE001
                    value = None
                values_out.append("" if value is None else str(value))
            rows.append((r + 1, values_out))     # 行号 1 起（与表格一致）

        return {
            "headers": headers,
            "rows": rows,
            "sheet": str(sheet_name),
            "truncated": truncated,
            "total_rows": total_rows,
        }

    # ==================================================================
    # 预览入口
    # ==================================================================
    def _print_preview(self):
        """打开打印预览（蜜算）。R8：先选**缩放模式**（对齐 WPS）。"""
        try:
            from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog
        except ImportError:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "提示", "当前环境不支持打印功能")
            return

        from PySide6.QtWidgets import (
            QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
            QVBoxLayout,
        )

        # 列很多时自动横向：纵向可用的宽度按 A4 估算（210 - 2*12 mm）
        data = self._collect_print_data()
        col_count = len(data["headers"])

        # ---- 打印设置（缩放模式）----
        dialog = QDialog(self)
        dialog.setWindowTitle("🖨️ 打印设置（蜜算）")
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        combo = QComboBox(dialog)
        for key, label in FIT_LABELS:
            combo.addItem(label, key)
        current = getattr(self, "_print_fit", FIT_WIDTH)
        for index in range(combo.count()):
            if combo.itemData(index) == current:
                combo.setCurrentIndex(index)
                break
        form.addRow("缩放：", combo)
        total_rows = len(data["rows"])
        form.addRow(QLabel(
            f"将打印 {total_rows} 行 × {col_count} 列"
            f"（超过 {MAX_PRINT_ROWS} 行会截断）"
        ))
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._print_fit = combo.currentData()

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        if col_count > 7:
            printer.setPageOrientation(QPageLayout.Orientation.Landscape)
        else:
            printer.setPageOrientation(QPageLayout.Orientation.Portrait)
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))

        preview = QPrintPreviewDialog(printer, self)
        preview.setWindowTitle("🖨️ 打印预览（蜜算）")
        preview.resize(1000, 760)
        preview.paintRequested.connect(self._render_sheet_to)
        preview.exec()

    # ==================================================================
    # 绘制
    # ==================================================================
    # ==================================================================
    # 排版计划（**纯数据，可测**）
    # ==================================================================
    @staticmethod
    def _build_print_plan(data, usable_w, usable_h, px_per_mm,
                          fit=FIT_WIDTH, custom_scale=None):
        """
        生成**排版计划**：每页画什么、在哪里 —— 全是数据，不做任何绘制。

        为什么要把"计划"独立出来（重要）
        --------------------------------
        原计划用"渲染成 PDF 再提取文字"来验证打印。实测发现**本环境 Qt 一个
        字体都没有**（`QFontDatabase.families()` 返回 **0**，`PySide6/lib/fonts`
        不存在）→ PDF 与栅格输出**都画不出字**（连蜜写原有的
        `QTextDocument.print_()` 也一样），文字提取恒为空。

        于是改为：**排版决策放在这里用纯数据表达**（分页、重复标题行、页脚
        文字、截断说明、列宽、对齐），测试直接断言这些数据，**完全不依赖字体**；
        绘制层只负责把计划画出来。渲染与计划的一致性用
        "**PDF 实际页数 == 计划页数**"这个与字体无关的不变量来锁。

        R8 新增的**缩放模式**（WPS 官方教程主推的"缩放到一页"）：
          · `FIT_NONE`   不缩放：列宽用自然宽度；**超宽就按列横向分页**
          · `FIT_WIDTH`  适应 1 页宽（默认，保持既有行为）：整体等比缩小到页宽内
          · `FIT_HEIGHT` 适应 1 页高：缩小到页高内（列宽不动）
          · `FIT_PAGE`   缩放到 1 页：宽高都塞进一页
          · `custom_scale` 自定义百分比（0.1–1.0 之外的会被夹住）

        **等比缩放 ≠ 压列宽**：早期实现是把列宽挤到页宽内，文字会被挤坏；
        现在缩放的是**整体比例**（列宽与行高一起按 `scale` 缩），
        这才是"缩放到一页"的真正含义。
        """
        row_h = ROW_HEIGHT_MM * px_per_mm
        header_h = HEADER_HEIGHT_MM * px_per_mm
        margin = MARGIN_MM * px_per_mm
        footer_h = 6.0 * px_per_mm

        natural = SheetPrintMixin._natural_column_widths(data, usable_w)
        # ⚠️ 第一个宽度是**行号列**（伪列，不在 headers 里）。列带索引必须只按
        # **表头**算，否则 band_end 会与 len(headers) 差 1：
        # 越界判断失效（截断说明不出现在最后一页）、横向带的列也会切错。
        # 这个 off-by-one 是被既有测试 `..._truncation_on_last_page` 抓到的。
        rownum_w = natural[0] if natural else 0.0
        natural_headers = natural[1:]
        rows = data["rows"]
        # ⚠️ **第一页还要画标题**（工作表名），高度 ≈ 表头高度。
        # 必须把它算进"内容总高"——否则 ① 缩放会按偏小的高度算 →
        # 首页仍放不下（"缩放到 1 页"失效，被 fit 测试抓到）；
        # ② 排版的每页行数偏多 → Qt 的 PDF 引擎**多开一页**
        # （导出 200 行的表："计划 5 页、实际 6 页"，被
        # `tests/fidelity/test_p0_pdf_export.py` 的页数不变量抓到）。
        title_h = header_h if str(data.get("sheet") or "") else 0.0
        content_h = header_h + footer_h + title_h + max(1, len(rows)) * row_h

        scale, bands = SheetPrintMixin._plan_scale_and_bands(
            natural_headers, usable_w, usable_h, content_h, fit,
            custom_scale, rownum_w=rownum_w,
        )

        eff_row_h = row_h * scale
        eff_header_h = header_h * scale

        body_h = max(eff_row_h, usable_h - eff_header_h - footer_h * scale)
        # 首页要额外留出标题的高度（缩放后）
        body_h = max(eff_row_h, body_h - title_h * scale)
        # ⚠️ 浮点边界：`int(58.9/0.4909) == 119` 会让"刚好一行塞满"的表
        # 多出一页（120 行的表被拆成 2 页，测试抓到）。加个极小容差再取整。
        rows_per_page = max(1, int(body_h / eff_row_h + 1e-9))
        row_pages = (max(1, math.ceil(len(rows) / rows_per_page))
                     if rows else 1)

        pages = []
        page_no = 0
        header_count = len(data["headers"])
        for band_start, band_end in bands:
            band_headers = natural_headers[band_start:band_end]
            # 每一带都要带**行号列**（横向分页后每页都有行号）
            band_widths = [rownum_w] + [w * scale for w in band_headers]
            bands_count = len(bands)
            # 缩放在整表上算过；这里再兜一次"单带仍超宽"
            band_widths = SheetPrintMixin._fit_single_band(
                band_widths, usable_w
            )
            for row_index in range(row_pages):
                page_no += 1
                start = row_index * rows_per_page
                chunk = rows[start:start + rows_per_page]
                is_first = (row_index == 0 and band_start == 0)
                is_last = (
                    (start + rows_per_page) >= len(rows)
                    and band_end == header_count
                )
                footer_left = str(data["sheet"])
                if bands_count > 1:
                    footer_left += f"（第 {band_start + 1}-{band_end} 列）"
                if data["truncated"] and is_last:
                    footer_left += f"（已截断 {data['truncated']} 行）"
                # 缩得太小时**明确告诉用户**（而不是让他打出来才发现看不清）
                if TINY_SCALE_WARN and scale < TINY_SCALE_WARN and band_start == 0:
                    footer_left += f"（已缩放到 {scale * 100:.0f}%，可能难以阅读）"
                pages.append({
                    "page_no": page_no,
                    "total_pages": 0,            # 稍后回填
                    # 重复标题行：非首页时，页首额外画一次数据区第一行
                    "repeat_header_row": (
                        rows[0] if (rows and not is_first) else None
                    ),
                    # ⚠️ `data["rows"]` 的元素是 `(行号, [单元格...])`。
                    # 横向分页只能切**单元格那一半** —— 我第一版切了外层元组，
                    # 结果每页都带着整行数据（测试当场抓到）。
                    "rows": [
                        (row[0], list(row[1])[band_start:band_end])
                        for row in chunk
                    ],
                    "headers": list(data["headers"][band_start:band_end]),
                    # 每一带自己的列宽（横向分页后各页列不同）
                    "widths": band_widths,
                    "col_start": band_start,
                    "col_end": band_end,
                    "title": str(data["sheet"]) if is_first else "",
                    "footer_left": footer_left,
                    "footer_right": "",
                })

        for page in pages:
            page["total_pages"] = len(pages)
            page["footer_right"] = f"第 {page['page_no']} / {len(pages)} 页"

        eff_widths = [rownum_w * scale] + [w * scale for w in natural_headers]
        eff_widths = SheetPrintMixin._fit_single_band(eff_widths, usable_w)
        return {
            "pages": pages,
            "widths": eff_widths,
            "scale": scale,
            "fit": fit,
            "bands": bands,
            "tiny_scale": bool(scale < TINY_SCALE_WARN),
            "row_height": eff_row_h,
            "header_height": eff_header_h,
            "margin": margin,
            "empty": not rows,
        }

    @staticmethod
    def _plan_scale_and_bands(natural_headers, usable_w, usable_h, content_h,
                              fit, custom_scale=None, rownum_w=0.0):
        """
        决定**缩放比例**与**列带（横向分页）** —— 纯计算，便于单独断言。

        :param natural_headers: **只含表头**的自然宽度（不含行号列）
        :param rownum_w: 行号列宽度（每一带都会带上它，所以要占宽度）
        :return: (scale, [(band_start, band_end), ...]) —— 索引是**表头索引**
        """
        total_w = (rownum_w + sum(natural_headers)) or 1.0
        if fit == FIT_NONE:
            # 不缩放：能放下就一页宽；放不下就**按列横向分页**
            if total_w <= usable_w:
                return 1.0, [(0, len(natural_headers))]
            # 每一带都要容下行号列
            available = max(1.0, usable_w - rownum_w)
            return 1.0, SheetPrintMixin._split_column_bands(
                natural_headers, available
            )

        if custom_scale is not None:
            try:
                value = float(custom_scale)
            except (TypeError, ValueError):
                value = 1.0
            # **用户手动填的百分比**要夹在合理范围（别缩成看不见）
            return max(0.05, min(1.0, value)), [(0, len(natural_headers))]

        by_width = usable_w / total_w if total_w > usable_w else 1.0
        by_height = usable_h / content_h if content_h > usable_h else 1.0
        if fit == FIT_WIDTH:
            scale = by_width
        elif fit == FIT_HEIGHT:
            scale = by_height
        else:                                   # FIT_PAGE
            scale = min(by_width, by_height)
        # ⚠️ **自动缩放不夹下限**：用户明确要求"塞进一页"，就该塞进去。
        # 我第一版用了统一 5% 下限，结果 120 行的表选"适应 1 页高"仍是多页
        # （测试 `test_fit_height_only_limits_height` 当场抓到）。
        # 太小的时候由 `tiny_scale` 提示"可能难以阅读"（见页脚），而不是偷偷不生效。
        return max(0.0, min(1.0, scale)), [(0, len(natural_headers))]

    @staticmethod
    def _split_column_bands(natural, usable_w):
        """
        把列按**自然宽度**贪心分成若干带，每带宽度 ≤ 可用宽度。

        单列自己就超宽时**单独成带**（再由 `_fit_single_band` 压到页内）——
        否则会出现"永远放不下"的死循环。
        """
        bands = []
        start = 0
        current = 0.0
        for index, width in enumerate(natural):
            if current and current + width > usable_w:
                bands.append((start, index))
                start = index
                current = width
            else:
                current += width
        if start < len(natural):
            bands.append((start, len(natural)))
        return bands or [(0, len(natural))]

    @staticmethod
    def _fit_single_band(widths, usable_w):
        """单带内仍然超宽（例如某列特别宽）时，把它压进页内。"""
        total = sum(widths)
        if total <= usable_w or not widths:
            return widths
        factor = usable_w / total
        return [w * factor for w in widths]

    # ==================================================================
    # 导出 PDF（P0 修复：三模块统一走 Qt 打印路径）
    # ==================================================================
    def export_pdf(self, path: str) -> bool:
        """
        把当前工作表导出为 PDF —— 复用**打印**那套渲染（`_render_sheet_to`）。

        审计报告 §2.2：全局「导出 PDF」原先只认蜜写，蜜算/蜜演点它弹
        "当前文档不支持导出 PDF"；而蜜算其实**一直**能打印成 PDF。
        现在补上这个方法，全局入口就能按模块分流了。
        """
        try:
            from PySide6.QtPrintSupport import QPrinter
        except ImportError:
            return False

        data = self._collect_print_data()
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        if len(data.get("headers") or []) > 7:
            printer.setPageOrientation(QPageLayout.Orientation.Landscape)
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(path))
        try:
            self._render_sheet_to(printer)
            return True
        except Exception as e:  # noqa: BLE001
            logging.error(f"[蜜算] 导出 PDF 失败: {e}")
            return False

    # ==================================================================
    # 绘制
    # ==================================================================
    @staticmethod
    def _print_geometry(printer):
        """
        从打印设备算出排版几何（设备像素）。

        抽出来是为了**让渲染与测试用同一套几何** ——
        我第一次写测试时手填了"可用高度 260mm"，而渲染用的是真实 A4
        可用区（≈277mm），两者算出的每页行数不同 → 页数对不上，
        被"页数一致"这条不变量当场抓住。
        """
        rect = printer.pageLayout().paintRectPixels(printer.resolution())
        dpi = max(1.0, float(printer.resolution()))
        px = dpi / 25.4                        # 1 毫米 = 多少设备像素
        margin = MARGIN_MM * px
        usable_w = max(1.0, rect.width() - 2 * margin)
        usable_h = max(1.0, rect.height() - 2 * margin)
        body_h = max(1.0, usable_h - HEADER_HEIGHT_MM * px - 6.0 * px)
        return {
            "rect": rect,
            "px": px,
            "margin": margin,
            "usable_w": usable_w,
            "usable_h": usable_h,
            "body_h": body_h,
        }

    def _render_sheet_to(self, printer):
        """
        把表格画到打印设备上（可分页）。

        ⚠️ **单位必须统一为"设备像素 + 磅字号"**（实测踩过的大坑）
        -----------------------------------------------------------
        我第一版把 painter 按**毫米**缩放（×`dpi/25.4` ≈ 47），再用
        `setPointSizeF(3.0)` 设字号。但**磅是按设备 DPI 解析的** ——
        1200 dpi 下 3pt 已经是 50 像素，再乘 47 变成约 2350 像素，
        远超 7.5 毫米的行高 → 一个字都画不出来。

        正确做法：几何量全部换算成**设备像素**，字号用**真实磅值**。
        （本沙箱无字体，字形画不出来是环境问题，见 `_build_print_plan` 说明。）
        """
        data = self._collect_print_data()
        geom = self._print_geometry(printer)
        painter = QPainter(printer)
        try:
            rect = geom["rect"]
            px = geom["px"]
            margin = geom["margin"]
            plan = self._build_print_plan(
                data, geom["usable_w"], geom["body_h"], px,
                fit=getattr(self, "_print_fit", FIT_WIDTH),
            )
            painter.translate(rect.left(), rect.top())

            if plan["empty"]:
                self._draw_empty_notice(painter, margin, geom["usable_w"], px)
                return

            row_h = plan["row_height"]
            header_h = plan["header_height"]
            widths = plan["widths"]
            total_w = sum(widths)

            for page_index, page in enumerate(plan["pages"]):
                if page_index > 0:
                    if not printer.newPage():
                        break
                    # newPage 会把 painter 变换重置为 identity，需重新定位
                    painter.translate(rect.left(), rect.top())

                # R8：横向分页后**每页列不同**，列宽以本页为准
                page_widths = page.get("widths") or widths
                y = margin
                if page["title"]:
                    y = self._draw_page_title(
                        painter, page["title"], margin, y,
                        geom["usable_w"], header_h
                    )
                y = self._draw_header_row(
                    painter, page["headers"], page_widths, margin, y,
                    header_h
                )
                y = self._draw_body_rows(
                    painter, page["rows"], page_widths, margin, y, row_h
                )
                if page["repeat_header_row"] is not None:
                    self._draw_body_rows(
                        painter, [page["repeat_header_row"]], page_widths,
                        margin, y, row_h, highlight=True,
                    )
                # ⚠️ 页脚必须画在**页面内**（实测踩过）：
                # 原先是 `rect.height() - margin + 1.0 * px`，而页脚矩形本身还有
                # 4px 高度 → 整体超出可打印区约 5px → Qt 的 PDF 引擎会因此
                # **多开一页**（导出 200 行的表时"计划 5 页、实际 6 页"，
                # 被 `test_p0_pdf_export` 的页数不变量抓到）。
                # 让页脚底边正好压在下方页边距上即可。
                footer_y = rect.height() - margin - 4.0 * px
                self._draw_footer(
                    painter, page["footer_left"], page["footer_right"],
                    margin, footer_y, geom["usable_w"], px,
                )
                _ = total_w
        finally:
            painter.end()

    # ------------------------------------------------------------------
    # 绘制辅助（全部使用设备像素；字号用真实磅值）
    # ------------------------------------------------------------------
    @staticmethod
    def _natural_column_widths(data, usable_w=None):
        """
        按内容长度估算列的**自然宽度**（不做压缩）。

        ⚠️ **单位必须跟随 `usable_w`**（原实现里就有、我抽出本函数时差点弄丢的
        关键约定）：`usable_w` 在测试里可能是毫米、渲染时是设备像素
        （600dpi 下 A4 可用宽约 6450 像素）。若宽度写死成毫米，
        与像素比较会永远"放得下" → **横向分页永不触发**（测试当场抓到）。

        R8 之前这里顺带"压到页宽内"；现在压缩只作为**缩放**的一种结果出现
        （见 `_plan_scale_and_bands`），自然宽度单独算出来。
        """
        headers = data["headers"]
        if not headers:
            return []
        unit = (usable_w / 180.0) if usable_w else 1.0
        widths = [10.0 * unit]                     # 行号列
        for i in range(len(headers)):
            longest = len(str(headers[i]))
            for _, values in data["rows"][:200]:   # 抽样前 200 行估宽
                cell = values[i] if i < len(values) else ""
                longest = max(longest, len(str(cell)))
            widths.append(min(70.0 * unit,
                              max(MIN_COL_WIDTH_MM * unit,
                                  longest * 2.0 * unit)))
        return widths

    @staticmethod
    def _compute_column_widths(data, usable_w):
        """
        按内容长度估算列宽，并整体等比压到可用宽度内。

        单位与 `usable_w` 一致（测试里可用毫米，渲染时用设备像素）——
        本函数**不做单位假设**，便于单独测。

        （保留它是因为既有测试与调用方以"页宽内"为契约；
        R8 的缩放路径走 `_natural_column_widths` + `_plan_scale_and_bands`。）
        """
        widths = SheetPrintMixin._natural_column_widths(data, usable_w)
        total = sum(widths)
        if total > usable_w and widths:
            scale = usable_w / total
            widths = [w * scale for w in widths]
        return widths

    @staticmethod
    def _draw_page_title(painter, title, margin, y, usable_w, header_h):
        painter.save()
        font = QFont()
        font.setPointSizeF(11.0)                   # 真实磅值
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(QColor(33, 33, 33)))
        painter.drawText(
            QRectF(margin, y, usable_w, header_h),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            str(title),
        )
        painter.restore()
        return y + header_h

    @staticmethod
    def _draw_header_row(painter, headers, widths, margin, y, header_h):
        """画列标行（A、B、C… + 行号列的 “#”）。"""
        painter.save()
        font = QFont()
        font.setPointSizeF(9.0)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(QColor(60, 60, 60)))
        total_w = sum(widths)
        painter.fillRect(QRectF(margin, y, total_w, header_h),
                         QColor(240, 240, 240))
        x = margin
        labels = ["#"] + list(headers)
        for i, label in enumerate(labels):
            if i >= len(widths):
                break
            painter.drawText(
                QRectF(x, y, widths[i], header_h),
                Qt.AlignmentFlag.AlignCenter,
                str(label),
            )
            painter.drawLine(int(x), int(y), int(x), int(y + header_h))
            x += widths[i]
        painter.drawRect(QRectF(margin, y, total_w, header_h))
        painter.restore()
        return y + header_h

    def _draw_body_rows(self, painter, rows, widths, margin, y, row_h,
                        highlight=False):
        """画数据行；`highlight` 用于跨页重复的标题行（加底色以区分）。"""
        painter.save()
        font = QFont()
        font.setPointSizeF(9.0)
        painter.setFont(font)
        grid = QPen(QColor(200, 200, 200))
        grid.setWidth(1)
        total_w = sum(widths)

        for row_no, values in rows:
            if highlight:
                painter.fillRect(QRectF(margin, y, total_w, row_h),
                                 QColor(250, 250, 230))

            painter.setPen(QPen(QColor(33, 33, 33)))
            x = margin
            painter.drawText(
                QRectF(x, y, widths[0], row_h),
                Qt.AlignmentFlag.AlignCenter,
                str(row_no),
            )
            x += widths[0]
            for i, value in enumerate(values):
                col = i + 1
                if col >= len(widths):
                    break
                numeric = self._looks_numeric(value)
                painter.drawText(
                    QRectF(x + 2, y, max(1.0, widths[col] - 4), row_h),
                    (Qt.AlignmentFlag.AlignRight
                     if numeric else Qt.AlignmentFlag.AlignLeft)
                    | Qt.AlignmentFlag.AlignVCenter,
                    value,
                )
                x += widths[col]

            painter.setPen(grid)
            painter.drawLine(int(margin), int(y + row_h),
                             int(margin + total_w), int(y + row_h))
            for i in range(len(widths) + 1):
                x_line = margin + sum(widths[:i])
                painter.drawLine(int(x_line), int(y), int(x_line), int(y + row_h))
            y += row_h
        painter.restore()
        return y

    @staticmethod
    def _looks_numeric(text):
        """数字（含千分位/货币/百分比）右对齐。"""
        if not text:
            return False
        probe = text.replace(",", "").replace("¥", "").replace("%", "").strip()
        try:
            float(probe)
            return True
        except ValueError:
            return False

    @staticmethod
    def _draw_footer(painter, left_text, right_text, margin, y, width, px):
        painter.save()
        font = QFont()
        font.setPointSizeF(7.5)
        painter.setFont(font)
        painter.setPen(QPen(QColor(120, 120, 120)))
        painter.drawText(
            QRectF(margin, y, width * 0.6, 4.0 * px),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            str(left_text),
        )
        painter.drawText(
            QRectF(margin + width * 0.6, y, width * 0.4, 4.0 * px),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            str(right_text),
        )
        painter.restore()

    @staticmethod
    def _draw_empty_notice(painter, margin, usable_w, px):
        painter.save()
        font = QFont()
        font.setPointSizeF(11.0)
        painter.setFont(font)
        painter.setPen(QPen(QColor(120, 120, 120)))
        painter.drawText(
            QRectF(margin, margin, usable_w, 10.0 * px),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "（当前工作表没有可打印的内容）",
        )
        painter.restore()
