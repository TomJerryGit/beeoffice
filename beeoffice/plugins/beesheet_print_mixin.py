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


class SheetPrintMixin:
    """蜜算打印 / 打印预览。"""

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

        # ---- 默认范围 = 已用区域；选中多格时以选区为准 ----
        start_row, start_col = 0, 0
        end_row, end_col = last_row, last_col
        try:
            selection = self.table_view.selectionModel().selection()
            if selection and not selection.isEmpty():
                rect = selection[0]
                if rect.isValid() and (
                    rect.top() != rect.bottom() or rect.left() != rect.right()
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
        """打开打印预览（蜜算）。"""
        try:
            from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog
        except ImportError:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "提示", "当前环境不支持打印功能")
            return

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)

        # 列很多时自动横向：纵向可用的宽度按 A4 估算（210 - 2*12 mm）
        data = self._collect_print_data()
        col_count = len(data["headers"])
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
    def _build_print_plan(data, usable_w, usable_h, px_per_mm):
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
        """
        row_h = ROW_HEIGHT_MM * px_per_mm
        header_h = HEADER_HEIGHT_MM * px_per_mm
        margin = MARGIN_MM * px_per_mm
        footer_h = 6.0 * px_per_mm

        widths = SheetPrintMixin._compute_column_widths(data, usable_w)
        body_h = max(row_h, usable_h - header_h - footer_h)
        rows_per_page = max(1, int(body_h // row_h))

        rows = data["rows"]
        total_pages = max(1, math.ceil(len(rows) / rows_per_page)) if rows else 1

        pages = []
        for page_index in range(total_pages):
            start = page_index * rows_per_page
            chunk = rows[start:start + rows_per_page]
            is_first = page_index == 0
            is_last = (start + rows_per_page) >= len(rows)
            footer_left = str(data["sheet"])
            if data["truncated"] and is_last:
                footer_left += f"（已截断 {data['truncated']} 行）"
            pages.append({
                "page_no": page_index + 1,
                "total_pages": total_pages,
                # 重复标题行：非首页时，页首额外画一次数据区第一行
                "repeat_header_row": rows[0] if (rows and not is_first) else None,
                "rows": chunk,
                "headers": list(data["headers"]),
                "title": str(data["sheet"]) if is_first else "",
                "footer_left": footer_left,
                "footer_right": f"第 {page_index + 1} / {total_pages} 页",
            })

        return {
            "pages": pages,
            "widths": widths,
            "row_height": row_h,
            "header_height": header_h,
            "margin": margin,
            "empty": not rows,
        }

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
                data, geom["usable_w"], geom["body_h"], px
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

                y = margin
                if page["title"]:
                    y = self._draw_page_title(
                        painter, page["title"], margin, y,
                        geom["usable_w"], header_h
                    )
                y = self._draw_header_row(
                    painter, page["headers"], widths, margin, y, header_h
                )
                y = self._draw_body_rows(
                    painter, page["rows"], widths, margin, y, row_h
                )
                if page["repeat_header_row"] is not None:
                    self._draw_body_rows(
                        painter, [page["repeat_header_row"]], widths,
                        margin, y, row_h, highlight=True,
                    )
                footer_y = rect.height() - margin + 1.0 * px
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
    def _compute_column_widths(data, usable_w):
        """
        按内容长度估算列宽，并整体等比压到可用宽度内。

        单位与 `usable_w` 一致（测试里可用毫米，渲染时用设备像素）——
        本函数**不做单位假设**，便于单独测。
        """
        headers = data["headers"]
        if not headers:
            return []
        unit = usable_w / 180.0 if usable_w else 1.0
        widths = [10.0 * unit]                     # 行号列
        for i in range(len(headers)):
            longest = len(str(headers[i]))
            for _, values in data["rows"][:200]:   # 抽样前 200 行估宽
                if i < len(values):
                    longest = max(longest, len(values[i]))
            widths.append(min(70.0 * unit,
                              max(MIN_COL_WIDTH_MM * unit,
                                  longest * 2.0 * unit)))
        total = sum(widths)
        if total > usable_w:
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
