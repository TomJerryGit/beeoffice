# beeoffice/plugins/beewrite_paged_canvas.py
"""M3.1 只读分页画布：真实页数、页间间距、页眉页脚。

使用同一份 QTextDocument 的克隆按 A4 页大小分页绘制；
点击页面通过 position_clicked 交给主编辑区定位。
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from beeoffice.theme import Theme
from beeoffice.plugins.beewrite_page_view import (
    PaperPageView,
    build_page_document,
)


class PagedCanvas(QWidget):
    position_clicked = Signal(int)

    def __init__(self, settings_provider, header_provider, parent=None):
        super().__init__(parent)
        self._settings_provider = settings_provider
        self._header_provider = header_provider
        self._source = None
        self._settings = {}
        self._header = ""
        self._footer = ""
        self._page_number = {}
        self._view = None

        _t = Theme.tokens()
        self._label = QLabel("共 0 页")
        self._label.setStyleSheet(
            f"QLabel{{color:{_t['muted']};font-size:12px;padding:2px 8px;}}"
        )
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setStyleSheet(
            f"QScrollArea{{background:{_t['surface_alt']};border:none;}}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._label)
        layout.addWidget(self._scroll, 1)

    def refresh_from(self, document, settings=None, header="", footer="",
                     page_number=None):
        """用当前文档克隆重建分页画布。"""
        try:
            self._settings = dict(settings if settings is not None
                                  else (self._settings_provider() or {}))
            if header or footer or page_number is not None:
                self._header = header
                self._footer = footer
                self._page_number = dict(page_number or {})
            else:
                self._header, self._footer, self._page_number = (
                    self._header_provider()
                )
            self._source = document
            if document is None:
                return
            clone = build_page_document(document)
            old = self._scroll.takeWidget()
            if old is not None:
                old.deleteLater()
            self._view = PaperPageView(
                clone, self._settings,
                header_text=self._header,
                footer_text=self._footer,
                page_number_config=self._page_number,
            )
            self._view.position_clicked.connect(self.position_clicked)
            self._scroll.setWidget(self._view)
            self._label.setText(f"共 {self._view.pages} 页")
        except Exception:
            pass

    def page_count(self) -> int:
        return self._view.pages if self._view is not None else 0
