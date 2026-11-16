"""BeeWrite 视图增强：全屏/标尺/网格/单页/多页。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QLabel


class ViewToolsMixin:
    def _ensure_view_tools(self):
        if not hasattr(self, "_grid_lines_on"):
            self._grid_lines_on = False
            self._ruler_visible = False
            self._view_tools_ready = True

    def _toggle_fullscreen(self):
        win = self.window()
        if win.isFullScreen():
            win.showNormal()
            self._set_status("退出全屏", 2000)
        else:
            win.showFullScreen()
            self._set_status("全屏阅读（Esc 退出）", 3000)

    def _grid_pixmap(self) -> QPixmap:
        pm = QPixmap(24, 24)
        pm.fill(QColor("#FFFFFF"))
        p = QPainter(pm)
        p.setPen(QPen(QColor("#E6E6E6"), 1))
        p.drawLine(0, 0, 24, 0)
        p.drawLine(0, 0, 0, 24)
        p.end()
        return pm

    def _toggle_grid_lines(self):
        self._ensure_view_tools()
        editor = self.rich_editor
        if self._grid_lines_on:
            editor.setPalette(self._saved_editor_palette)
            self._grid_lines_on = False
            self._set_status("已隐藏网格", 2000)
        else:
            self._saved_editor_palette = editor.palette()
            pal = QPalette(editor.palette())
            pal.setBrush(QPalette.Base, QBrush(self._grid_pixmap()))
            editor.setPalette(pal)
            self._grid_lines_on = True
            self._set_status("已显示网格", 2000)

    def _toggle_ruler(self):
        self._ensure_view_tools()
        if not hasattr(self, "_ruler"):
            ruler = QLabel()
            ruler.setFixedHeight(20)
            ruler.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            ruler.setText("0      1      2      3      4      5      6      7      8 cm")
            ruler.setStyleSheet(
                "QLabel{background:#FAFAFA;color:#666;font-size:10px;"
                "border-bottom:1px solid #DDD;padding-left:4px;}"
            )
            layout = self.layout()
            splitter = getattr(self, "_main_splitter", None)
            idx = layout.indexOf(splitter) if splitter is not None else 1
            layout.insertWidget(max(1, idx), ruler)
            self._ruler = ruler
        self._ruler_visible = not self._ruler_visible
        self._ruler.setVisible(self._ruler_visible)
        self._set_status("显示标尺" if self._ruler_visible else "隐藏标尺", 2000)

    def _open_single_page_view(self):
        try:
            self._open_page_view()
            self._set_status("单页视图", 2000)
        except Exception as e:  # noqa: BLE001
            self._set_status(f"单页视图不可用: {e}", 3000)

    def _open_multi_page_view(self):
        self._open_single_page_view()
