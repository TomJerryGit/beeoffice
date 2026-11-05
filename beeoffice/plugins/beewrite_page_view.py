# beeoffice/plugins/beewrite_page_view.py
"""蜜写纸张页面视图：只读分页预览（A4 + 页边距 + 页码 + 缩放）。

第一阶段为只读页面视图；编辑仍在连续富文本/Markdown 视图中完成。
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, QSizeF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QTextDocument
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from beeoffice.i18n import tr

A4_CM = (21.0, 29.7)
DPI = 96


def _cm_to_px(cm: float) -> float:
    return cm / 2.54 * DPI


def build_page_document(rich_document=None, markdown_text: str = "") -> QTextDocument:
    """从富文本克隆或 Markdown 文本构建分页文档。"""
    if rich_document is not None:
        doc = rich_document.clone()
    else:
        doc = QTextDocument()
        font = QFont("Microsoft YaHei")
        font.setPointSize(11)
        doc.setDefaultFont(font)
        doc.setMarkdown(markdown_text or "")
    doc.setDocumentMargin(0)
    return doc


class PaperPageView(QWidget):
    """把 QTextDocument 按页绘制为纸张。"""

    def __init__(self, document: QTextDocument, page_settings: dict, parent=None):
        super().__init__(parent)
        self._doc = document
        self._settings = dict(page_settings or {})
        self._zoom = 1.0
        self._gap = 22
        self._recalc()

    def _recalc(self):
        margins = self._settings
        self._content_w = max(
            120.0,
            _cm_to_px(A4_CM[0] - margins.get("margin_left", 3.17)
                      - margins.get("margin_right", 3.17)),
        )
        self._content_h = max(
            120.0,
            _cm_to_px(A4_CM[1] - margins.get("margin_top", 2.54)
                      - margins.get("margin_bottom", 2.54)),
        )
        self._page_w = _cm_to_px(A4_CM[0])
        self._page_h = _cm_to_px(A4_CM[1])
        self._doc.setPageSize(QSizeF(self._content_w, self._content_h))
        self._pages = max(1, self._doc.pageCount())
        self._scale = self._zoom
        width = int((self._page_w + self._gap * 2) * self._scale)
        height = int((self._pages * self._page_h + (self._pages + 1) * self._gap) * self._scale)
        self.setMinimumSize(QSize(width, height))
        self.resize(width, height)
        self.update()

    @property
    def pages(self) -> int:
        return self._pages

    def set_zoom(self, zoom: float):
        self._zoom = max(0.5, min(2.0, zoom))
        self._recalc()

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#E9E9E9"))
        painter.scale(self._scale, self._scale)

        margin_l = _cm_to_px(self._settings.get("margin_left", 3.17))
        margin_t = _cm_to_px(self._settings.get("margin_top", 2.54))
        page_font = QFont("Microsoft YaHei")
        page_font.setPointSize(8)
        painter.setFont(page_font)

        for i in range(self._pages):
            y = self._gap + i * (self._page_h + self._gap)
            page_rect = QRectF(self._gap, y, self._page_w, self._page_h)
            painter.fillRect(page_rect.adjusted(3, 3, 3, 3), QColor(0, 0, 0, 30))
            painter.fillRect(page_rect, QColor("#FFFFFF"))

            # 内容区（页边距内）
            content_rect = QRectF(
                self._gap + margin_l,
                y + margin_t,
                self._content_w,
                self._content_h,
            )
            painter.save()
            painter.setClipRect(content_rect)
            painter.translate(content_rect.topLeft())
            painter.translate(0, -i * self._content_h)
            self._doc.drawContents(
                painter,
                QRectF(0, i * self._content_h, self._content_w, self._content_h),
            )
            painter.restore()

            # 页边距辅助线
            painter.setPen(QColor(0, 0, 0, 18))
            painter.drawRect(content_rect)

            # 页码
            painter.setPen(QColor("#888888"))
            footer = QRectF(
                self._gap,
                y + self._page_h - _cm_to_px(1.2),
                self._page_w,
                _cm_to_px(0.8),
            )
            painter.drawText(footer, Qt.AlignHCenter | Qt.AlignVCenter,
                             f"- {i + 1} -")

        painter.end()


class PageViewDialog(QDialog):
    """纸张页面视图对话框。"""

    def __init__(self, document: QTextDocument, page_settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("beewrite.page_view.title", "📄 页面视图"))
        self.resize(980, 760)
        self._zoom = 100

        toolbar = QHBoxLayout()
        self._page_label = QLabel("")
        toolbar.addWidget(self._page_label)
        toolbar.addStretch()
        toolbar.addWidget(QLabel(tr("beewrite.zoom", "缩放")))
        minus = QPushButton("−")
        minus.setFixedWidth(28)
        minus.clicked.connect(lambda: self._set_zoom(self._zoom - 10))
        toolbar.addWidget(minus)
        self._zoom_label = QLabel("100%")
        self._zoom_label.setMinimumWidth(48)
        self._zoom_label.setAlignment(Qt.AlignCenter)
        toolbar.addWidget(self._zoom_label)
        plus = QPushButton("+")
        plus.setFixedWidth(28)
        plus.clicked.connect(lambda: self._set_zoom(self._zoom + 10))
        toolbar.addWidget(plus)
        refresh = QPushButton(tr("beewrite.page_view.refresh", "刷新"))
        refresh.clicked.connect(self.refresh_document)
        toolbar.addWidget(refresh)
        close = QPushButton(tr("beewrite.page_view.close", "关闭"))
        close.clicked.connect(self.reject)
        toolbar.addWidget(close)

        self._source = document
        self._settings = dict(page_settings or {})
        self._view = PaperPageView(build_page_document(document), self._settings)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setWidget(self._view)
        self._scroll.setAlignment(Qt.AlignHCenter | Qt.AlignTop)

        layout = QVBoxLayout(self)
        layout.addLayout(toolbar)
        layout.addWidget(self._scroll, 1)
        self._update_label()

    def _update_label(self):
        self._page_label.setText(
            tr("beewrite.page_view.count", "共 {pages} 页").format(
                pages=self._view.pages)
        )
        self._zoom_label.setText(f"{self._zoom}%")

    def _set_zoom(self, percent: int):
        self._zoom = max(50, min(200, percent))
        self._view.set_zoom(self._zoom / 100.0)
        self._update_label()

    def refresh_document(self):
        self._view = PaperPageView(build_page_document(self._source), self._settings)
        self._scroll.setWidget(self._view)
        self._view.set_zoom(self._zoom / 100.0)
        self._update_label()
