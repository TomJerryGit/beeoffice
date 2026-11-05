# beeoffice/plugins/beewrite_page_overlay.py
"""M2.5 编辑区页面预览层：页边距参考线、页边界、页眉/页脚/页码预览。

不改变编辑/排版数据；仅绘制参考层，保持编辑区可编辑。
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

A4_CM = (21.0, 29.7)
DPI = 96


def _cm_to_px(cm: float) -> float:
    return cm / 2.54 * DPI


class PageLayoutOverlay(QWidget):
    """覆盖在编辑器 viewport 上的页面参考层（鼠标穿透）。"""

    def __init__(self, editor, settings_provider, header_provider, parent=None):
        super().__init__(parent or editor.viewport())
        self._editor = editor
        self._settings_provider = settings_provider
        self._header_provider = header_provider
        self._enabled = False
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.resize(editor.viewport().size())
        editor.viewport().installEventFilter(self)
        try:
            editor.verticalScrollBar().valueChanged.connect(self.update)
        except Exception:
            pass
        self.hide()

    # ------------------------------------------------------------------
    def set_enabled(self, enabled: bool):
        self._enabled = bool(enabled)
        if self._enabled:
            self.show()
            self.raise_()
            self.update()
        else:
            self.hide()

    def is_enabled(self) -> bool:
        return self._enabled

    def _page_number_text(self, index: int, total: int, config: dict) -> str:
        fmt = (config or {}).get("format", "第 1 页 / 共 N 页")
        start = int((config or {}).get("start", 1))
        return (fmt.replace("1", str(start + index), 1)
                .replace("N", str(total)))

    # ------------------------------------------------------------------
    def eventFilter(self, obj, event):
        if obj is self._editor.viewport() and event.type() == QEvent.Resize:
            self.resize(obj.size())
            self.update()
        return False

    def paintEvent(self, event):  # noqa: N802
        if not self._enabled:
            return
        try:
            settings = dict(self._settings_provider() or {})
            header = self._header_provider()[0] if self._header_provider else ""
            footer = self._header_provider()[1] if self._header_provider else ""
            page_cfg = self._header_provider()[2] if self._header_provider else {}
        except Exception:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        viewport_w = max(1, self.width())
        viewport_h = max(1, self.height())

        a4_w = _cm_to_px(A4_CM[0])
        scale = viewport_w / a4_w
        page_w = a4_w * scale
        page_h = _cm_to_px(A4_CM[1]) * scale
        left = max(0.0, (viewport_w - page_w) / 2.0)
        margin_l = _cm_to_px(settings.get("margin_left", 3.17)) * scale
        margin_r = _cm_to_px(settings.get("margin_right", 3.17)) * scale
        margin_t = _cm_to_px(settings.get("margin_top", 2.54)) * scale
        margin_b = _cm_to_px(settings.get("margin_bottom", 2.54)) * scale

        scroll = self._editor.verticalScrollBar().value()
        first = max(0, int(scroll // max(1.0, page_h)))
        total_pages = max(1, int(self._editor.document().pageCount()))

        for index in range(first, first + 3):
            y = index * page_h - scroll
            if y > viewport_h or y + page_h < 0:
                continue
            # 页面边界
            painter.setPen(QPen(QColor(120, 120, 120, 120), 1, Qt.DashLine))
            painter.drawLine(0, int(y), viewport_w, int(y))
            # 左右页边距参考线
            painter.setPen(QPen(QColor(120, 120, 120, 90), 1, Qt.DashLine))
            painter.drawLine(int(left + margin_l), int(y), int(left + margin_l), int(y + page_h))
            painter.drawLine(int(left + page_w - margin_r), int(y),
                             int(left + page_w - margin_r), int(y + page_h))
            # 上下页边距参考线
            painter.drawLine(int(left), int(y + margin_t),
                             int(left + page_w), int(y + margin_t))
            painter.drawLine(int(left), int(y + page_h - margin_b),
                             int(left + page_w), int(y + page_h - margin_b))

            # 页码角标
            painter.setPen(QColor(150, 150, 150))
            painter.drawText(
                QRectF(left + page_w - 36, y + page_h - 18, 30, 14),
                Qt.AlignRight | Qt.AlignVCenter, f"{index + 1}/{total_pages}",
            )
        painter.end()
