"""BeeSheet 视图增强：网格线/行号列标/缩放/页面视图。"""
from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QInputDialog


class ViewToolsMixin:
    """BeeSheet 视图开关。"""

    def _ensure_view_state(self):
        if not hasattr(self, "_zoom_percent"):
            self._zoom_percent = 100
            self._page_layout_mode = False

    def _toggle_grid_lines(self):
        self.table_view.setShowGrid(not self.table_view.showGrid())
        self._set_status(
            "已显示网格线" if self.table_view.showGrid() else "已隐藏网格线",
            2000,
        )

    def _toggle_headers(self):
        h = self.table_view.horizontalHeader()
        v = self.table_view.verticalHeader()
        visible = h.isHidden()
        h.setVisible(visible)
        v.setVisible(visible)
        self._set_status("已显示行号列标" if visible else "已隐藏行号列标", 2000)

    def _show_zoom_dialog(self):
        self._ensure_view_state()
        value, ok = QInputDialog.getInt(
            self, "显示比例", "缩放百分比：", self._zoom_percent, 50, 200, 10
        )
        if ok:
            self._apply_zoom(value)

    def _apply_zoom(self, percent: int):
        self._ensure_view_state()
        self._zoom_percent = max(50, min(200, int(percent)))
        scale = self._zoom_percent / 100.0
        font = self.table_view.font()
        base = getattr(self, "_zoom_base_font_size", None)
        if base is None:
            base = font.pointSizeF() or 9.0
            self._zoom_base_font_size = base
        font.setPointSizeF(max(6.0, base * scale))
        self.table_view.setFont(font)
        self.table_view.verticalHeader().setDefaultSectionSize(
            int(24 * scale)
        )
        self._set_status(f"显示比例 {self._zoom_percent}%", 2000)

    def _show_page_break_preview(self):
        self._set_status("分页预览：使用打印预览查看分页", 3000)
        self._show_print_preview()

    def _show_page_layout(self):
        self._ensure_view_state()
        self._page_layout_mode = not self._page_layout_mode
        if self._page_layout_mode:
            self.table_view.setStyleSheet(
                "QTableView{background:#F3F3F3;}"
            )
            self._set_status("页面布局视图", 2000)
        else:
            self.table_view.setStyleSheet("")
            self._set_status("普通视图", 2000)
