"""BeeSheet 页面/打印 Mixin。

提供 P0 打印闭环：
  - 页面设置（页边距/方向/纸张/缩放）
  - 打印预览
  - 设置/取消打印区域
  - 生成可打印 HTML

不依赖系统打印机即可构建文档；预览使用 QPrintPreviewDialog。
"""
from __future__ import annotations

import html

import pandas as pd
from PySide6.QtCore import QMarginsF, Qt
from PySide6.QtGui import QPageLayout, QPageSize, QTextDocument
from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QLineEdit, QSpinBox, QVBoxLayout,
)

from beeoffice.theme import Theme


def _t():
    return Theme.tokens()


class PrintMixin:
    """BeeSheet 页面/打印功能。"""

    def _init_print_settings(self):
        self._print_settings = {
            "top": 10.0,
            "bottom": 10.0,
            "left": 10.0,
            "right": 10.0,
            "orientation": "portrait",
            "paper": "A4",
            "scale": 100,
            "gridlines": True,
            "title": True,
            "header": "",
            "footer": "第 {page} 页",
            "area": None,  # (r0, c0, r1, c1)
        }

    def _ensure_print_settings(self):
        if not hasattr(self, "_print_settings"):
            self._init_print_settings()

    # ==================== 打印文档 ====================
    def _print_dataframe(self):
        """返回当前打印区域对应的 DataFrame。"""
        df = getattr(self.model, "df", None)
        if df is None:
            return pd.DataFrame()
        area = getattr(self, "_print_settings", {}).get("area")
        if not area:
            return df
        r0, c0, r1, c1 = area
        rows = list(range(r0, min(r1 + 1, len(df))))
        cols = list(range(c0, min(c1 + 1, len(df.columns))))
        if not rows or not cols:
            return pd.DataFrame()
        sub = df.iloc[rows, cols]
        return sub

    def _build_print_html(self) -> str:
        """生成打印用 HTML（不依赖打印机，便于测试）。"""
        self._ensure_print_settings()
        df = self._print_dataframe()
        settings = self._print_settings
        grid = "1" if settings.get("gridlines", True) else "0"
        parts = [
            "<html><head><meta charset='utf-8'>",
            "<style>",
            "body{font-family:'Microsoft YaHei',Arial,sans-serif;font-size:12px;}",
            "table{border-collapse:collapse;width:100%;}",
            f"td,th{{border:{grid}px solid #999;padding:4px;}}",
            "th{background:#EEE;font-weight:bold;}",
            "</style></head><body>",
        ]
        if settings.get("header"):
            parts.append(
                f"<div style='font-size:11px;color:#555;'>"
                f"{html.escape(settings['header'])}</div>"
            )
        if settings.get("title", True):
            parts.append("<h3>BeeSheet 表格</h3>")
        if df.empty:
            parts.append("<p>（无数据）</p></body></html>")
            return "".join(parts)
        parts.append("<table>")
        parts.append("<tr>")
        for col in df.columns:
            parts.append(f"<th>{html.escape(str(col))}</th>")
        parts.append("</tr>")
        for _, row in df.iterrows():
            parts.append("<tr>")
            for value in row:
                text = "" if pd.isna(value) else str(value)
                parts.append(f"<td>{html.escape(text)}</td>")
            parts.append("</tr>")
        parts.append("</table>")
        if settings.get("footer"):
            parts.append(
                f"<div style='font-size:11px;color:#555;text-align:center;'>"
                f"{html.escape(settings['footer'].replace('{page}', '1'))}"
                f"</div>"
            )
        parts.append("</body></html>")
        return "".join(parts)

    def _make_printer(self) -> QPrinter:
        self._ensure_print_settings()
        s = self._print_settings
        printer = QPrinter(QPrinter.HighResolution)
        paper_map = {
            "A4": QPageSize.A4,
            "A3": QPageSize.A3,
            "Letter": QPageSize.Letter,
        }
        page_size = QPageSize(paper_map.get(s.get("paper", "A4"), QPageSize.A4))
        orientation = (
            QPageLayout.Landscape
            if s.get("orientation") == "landscape"
            else QPageLayout.Portrait
        )
        layout = QPageLayout(
            page_size,
            orientation,
            QMarginsF(s["left"], s["top"], s["right"], s["bottom"]),
            QPageLayout.Millimeter,
        )
        printer.setPageLayout(layout)
        return printer

    def _render_print_document(self, printer):
        doc = QTextDocument()
        doc.setHtml(self._build_print_html())
        doc.print_(printer)

    def _show_print_preview(self):
        self._ensure_print_settings()
        printer = self._make_printer()
        dlg = QPrintPreviewDialog(printer, self)
        dlg.paintRequested.connect(self._render_print_document)
        dlg.exec()

    # ==================== 页面设置 ====================
    def _show_page_setup(self):
        self._ensure_print_settings()
        s = self._print_settings
        dlg = QDialog(self)
        dlg.setWindowTitle("页面设置")
        form = QFormLayout(dlg)

        spins = {}
        for key, label in (
            ("top", "上边距 (mm)"), ("bottom", "下边距 (mm)"),
            ("left", "左边距 (mm)"), ("right", "右边距 (mm)"),
        ):
            spin = QDoubleSpinBox()
            spin.setRange(0, 100)
            spin.setValue(float(s.get(key, 10)))
            form.addRow(label, spin)
            spins[key] = spin

        orient = QComboBox()
        orient.addItem("纵向", "portrait")
        orient.addItem("横向", "landscape")
        orient.setCurrentIndex(
            1 if s.get("orientation") == "landscape" else 0
        )
        form.addRow("纸张方向", orient)

        paper = QComboBox()
        paper.addItems(["A4", "A3", "Letter"])
        paper.setCurrentText(s.get("paper", "A4"))
        form.addRow("纸张大小", paper)

        scale = QSpinBox()
        scale.setRange(50, 200)
        scale.setSuffix(" %")
        scale.setValue(int(s.get("scale", 100)))
        form.addRow("打印缩放", scale)

        header_edit = QLineEdit(str(s.get("header", "")))
        header_edit.setPlaceholderText("页眉文字")
        form.addRow("页眉", header_edit)
        footer_edit = QLineEdit(str(s.get("footer", "")))
        footer_edit.setPlaceholderText("页脚文字，可用 {page}")
        form.addRow("页脚", footer_edit)

        grid = QCheckBox("打印网格线")
        grid.setChecked(bool(s.get("gridlines", True)))
        form.addRow(grid)
        title = QCheckBox("打印标题")
        title.setChecked(bool(s.get("title", True)))
        form.addRow(title)

        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, dlg
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        if dlg.exec() != QDialog.Accepted:
            return
        for key, spin in spins.items():
            s[key] = spin.value()
        s["orientation"] = orient.currentData()
        s["paper"] = paper.currentText()
        s["scale"] = scale.value()
        s["header"] = header_edit.text()
        s["footer"] = footer_edit.text()
        s["gridlines"] = grid.isChecked()
        s["title"] = title.isChecked()
        self._set_status("页面设置已更新", 2000)

    # ==================== 打印区域 ====================
    def _set_print_area(self):
        indexes = self.table_view.selectionModel().selectedIndexes()
        if not indexes:
            self._set_status("请先选择打印区域", 2000)
            return
        rows = [i.row() for i in indexes]
        cols = [i.column() for i in indexes]
        self._ensure_print_settings()
        self._print_settings["area"] = (
            min(rows), min(cols), max(rows), max(cols)
        )
        self._set_status("打印区域已设置", 2000)

    def _clear_print_area(self):
        self._ensure_print_settings()
        self._print_settings["area"] = None
        self._set_status("打印区域已取消", 2000)


    def _set_sheet_background(self):
        from PySide6.QtGui import QColor
        from PySide6.QtWidgets import QColorDialog
        color = QColorDialog.getColor(QColor("#FFF8E1"), self, "页面背景色")
        if not color.isValid():
            return
        self.table_view.setStyleSheet(
            f"QTableView{{background-color:{color.name()};}}"
        )
        self._sheet_background = color.name()
        self._set_status(f"已设置背景色 {color.name()}", 2000)

    def _set_sheet_watermark(self):
        from PySide6.QtWidgets import QInputDialog, QLabel
        text, ok = QInputDialog.getText(self, "页面水印", "水印文字：")
        if not ok or not text.strip():
            return
        old = getattr(self, "_watermark_label", None)
        if old is not None:
            old.deleteLater()
        label = QLabel(text.strip(), self.table_view.viewport())
        label.setStyleSheet(
            "QLabel{color:rgba(120,120,120,90);font-size:28px;"
            "font-weight:bold;background:transparent;}"
        )
        label.adjustSize()
        vp = self.table_view.viewport()
        label.move(max(0, (vp.width() - label.width()) // 2),
                   max(0, (vp.height() - label.height()) // 2))
        label.show()
        self._watermark_label = label
        self._set_status("已设置页面水印", 2000)
