# beeoffice/plugins/beewrite_page_frame.py
"""M2.6 编辑区页面框架：真实左右页边距缩进 + 页眉/页脚避让条。

说明：
  - 页眉/页脚放在编辑器外部的固定条，避免覆盖正文；
  - 左右页边距通过布局边距真实缩进编辑区；
  - 仍不是逐页分页布局，页间分页仍由参考层近似。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from beeoffice.theme import Theme

DPI = 96


def _cm_to_px(cm: float) -> int:
    return int(cm / 2.54 * DPI)


class PageEditorFrame(QWidget):
    def __init__(self, editor, settings_provider, header_provider, parent=None):
        super().__init__(parent)
        self._editor = editor
        self._settings_provider = settings_provider
        self._header_provider = header_provider
        self._preview_enabled = False

        self._header_label = QLabel("")
        self._header_label.setAlignment(Qt.AlignCenter)
        self._header_label.setWordWrap(True)
        self._header_label.hide()

        self._footer_label = QLabel("")
        self._footer_label.setAlignment(Qt.AlignCenter)
        self._footer_label.setWordWrap(True)
        self._footer_label.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._header_label)
        layout.addWidget(editor, 1)
        layout.addWidget(self._footer_label)
        self._layout = layout

        self._timer = QTimer(self)
        self._timer.setInterval(700)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self._apply_style()

    def set_preview_enabled(self, enabled: bool):
        self._preview_enabled = bool(enabled)
        self._header_label.setVisible(bool(enabled and self._header_label.text()))
        self._footer_label.setVisible(
            bool(enabled and self._footer_label.text())
        )
        self.refresh()

    def refresh(self):
        try:
            settings = dict(self._settings_provider() or {})
            header, footer, page_cfg = self._header_provider()
        except Exception:
            return
        if not self._preview_enabled:
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._header_label.hide()
            self._footer_label.hide()
            return

        left = _cm_to_px(settings.get("margin_left", 3.17))
        right = _cm_to_px(settings.get("margin_right", 3.17))
        avail = max(200, self.width())
        if left + right > avail * 0.7:
            scale = avail * 0.7 / max(1, left + right)
            left, right = int(left * scale), int(right * scale)
        self._layout.setContentsMargins(left, 4, right, 4)

        self._header_label.setText(header or "")
        self._header_label.setVisible(bool(header))

        total_pages = max(1, self._editor.document().pageCount())
        if page_cfg and page_cfg.get("enabled", True):
            fmt = page_cfg.get("format", "第 1 页 / 共 N 页")
            start = int(page_cfg.get("start", 1))
            page_text = (fmt.replace("1", str(start), 1)
                         .replace("N", str(total_pages)))
            footer_text = f"{footer}    {page_text}" if footer else page_text
        else:
            footer_text = footer or ""
        self._footer_label.setText(footer_text)
        self._footer_label.setVisible(bool(footer_text))
        self._apply_style()

    def _apply_style(self):
        try:
            high = Theme.is_high_contrast()
            tokens = Theme.tokens()
        except Exception:
            high, tokens = False, {"muted": "#666", "surface_alt": "#FAFAFA"}
        color = "#FFFFFF" if high else tokens.get("muted", "#666")
        bg = "#000000" if high else tokens.get("surface_alt", "#FAFAFA")
        for label in (self._header_label, self._footer_label):
            label.setStyleSheet(
                f"QLabel{{color:{color};background:{bg};font-size:11px;"
                "padding:2px 8px;}"
            )
