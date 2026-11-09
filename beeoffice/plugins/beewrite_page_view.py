# beeoffice/plugins/beewrite_page_view.py
"""蜜写纸张页面视图：A4 分页、页边距、页眉页脚、页码、缩放、点击定位。"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, QSizeF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFont, QPainter, QTextCursor, QTextDocument, QTextTable,
)
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTextEdit,
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


def find_cross_page_objects(document: QTextDocument, content_h: float) -> list[dict]:
    """找出跨越页面边界的图片/表格对象。"""
    content_h = max(1.0, float(content_h))
    layout = document.documentLayout()
    found = []

    def _page(rect):
        return max(0, int(rect.top() // content_h)), max(0, int(rect.bottom() // content_h))

    block = document.begin()
    while block.isValid():
        try:
            has_image = False
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid() and frag.charFormat().isImageFormat():
                    has_image = True
                    break
                it += 1
            if has_image:
                rect = layout.blockBoundingRect(block)
                start, end = _page(rect)
                if start != end:
                    found.append({"type": "image", "start_page": start,
                                  "end_page": end, "text": block.text()[:40]})
        except Exception:
            pass
        block = block.next()

    try:
        frames = list(document.rootFrame().childFrames())
        for frame in frames:
            if isinstance(frame, QTextTable):
                rect = layout.frameBoundingRect(frame)
                start, end = _page(rect)
                if start != end:
                    found.append({"type": "table", "start_page": start,
                                  "end_page": end, "rows": frame.rows()})
    except Exception:
        pass
    return found


class PaperPageView(QWidget):
    """把 QTextDocument 按页绘制为纸张，并支持点击定位。"""

    position_clicked = Signal(int)
    edit_requested = Signal(int)

    def __init__(self, document: QTextDocument, page_settings: dict,
                 header_text: str = "", footer_text: str = "",
                 page_number_config: dict | None = None, parent=None):
        super().__init__(parent)
        self._doc = document
        self._settings = dict(page_settings or {})
        self._header = header_text or ""
        self._footer = footer_text or ""
        self._page_number = dict(page_number_config or {})
        self._zoom = 1.0
        self._gap = 22
        self._cursor_position = -1
        self._cursor_visible = True
        self._selection_start = -1
        self._selection_end = -1
        self._preedit_text = ""
        self._highlights = []
        self._recalc()

    def _recalc(self):
        margins = self._settings
        self._margin_l = _cm_to_px(margins.get("margin_left", 3.17))
        self._margin_t = _cm_to_px(margins.get("margin_top", 2.54))
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
        height = int((self._pages * self._page_h
                      + (self._pages + 1) * self._gap) * self._scale)
        self.setMinimumSize(QSize(width, height))
        self.resize(width, height)
        self.update()

    @property
    def pages(self) -> int:
        return self._pages

    def set_cursor_position(self, position: int):
        self._cursor_position = int(position)
        self.update()

    def set_cursor_visible(self, visible: bool):
        self._cursor_visible = bool(visible)
        self.update()

    def set_selection(self, start: int, end: int):
        self._selection_start = int(start)
        self._selection_end = int(end)
        self.update()

    def set_preedit(self, text: str):
        self._preedit_text = text or ""
        self.update()

    def set_highlights(self, ranges):
        self._highlights = list(ranges or [])
        self.update()

    def _range_rects(self, start: int, end: int) -> list[QRectF]:
        """把文档字符范围换算为页面内的矩形（用于查找高亮）。"""
        if start < 0 or end < 0 or end <= start:
            return []
        rects = []
        try:
            block = self._doc.findBlock(start)
            while block.isValid() and block.position() < end:
                layout = block.layout()
                if layout is None:
                    block = block.next()
                    continue
                block_rect = self._doc.documentLayout().blockBoundingRect(block)
                for i in range(layout.lineCount()):
                    line = layout.lineAt(i)
                    line_start = block.position() + line.textStart()
                    line_end = line_start + line.textLength()
                    a = max(start, line_start)
                    b = min(end, line_end)
                    if b <= a:
                        continue
                    x1 = line.cursorToX(a - line_start)
                    x2 = line.cursorToX(b - line_start)
                    if isinstance(x1, tuple):
                        x1 = x1[0]
                    if isinstance(x2, tuple):
                        x2 = x2[0]
                    doc_y = block_rect.top() + line.y()
                    page = int(doc_y // max(1.0, self._content_h))
                    page = max(0, min(self._pages - 1, page))
                    local_y = doc_y - page * self._content_h
                    rects.append(QRectF(
                        self._gap + self._margin_l + min(x1, x2),
                        self._gap + page * (self._page_h + self._gap)
                        + self._margin_t + local_y,
                        max(1.0, abs(x2 - x1)),
                        max(12.0, line.height()),
                    ))
                block = block.next()
        except Exception:
            return []
        return rects

    def _selection_rects(self) -> list[QRectF]:
        if self._selection_start < 0 or self._selection_end < 0:
            return []
        start = min(self._selection_start, self._selection_end)
        end = max(self._selection_start, self._selection_end)
        if end <= start:
            return []
        rects = []
        try:
            block = self._doc.findBlock(start)
            while block.isValid() and block.position() < end:
                layout = block.layout()
                if layout is None:
                    block = block.next()
                    continue
                block_rect = self._doc.documentLayout().blockBoundingRect(block)
                for i in range(layout.lineCount()):
                    line = layout.lineAt(i)
                    line_start = block.position() + line.textStart()
                    line_end = line_start + line.textLength()
                    a = max(start, line_start)
                    b = min(end, line_end)
                    if b <= a:
                        continue
                    x1 = line.cursorToX(a - line_start)
                    x2 = line.cursorToX(b - line_start)
                    if isinstance(x1, tuple):
                        x1 = x1[0]
                    if isinstance(x2, tuple):
                        x2 = x2[0]
                    doc_y = block_rect.top() + line.y()
                    page = int(doc_y // max(1.0, self._content_h))
                    page = max(0, min(self._pages - 1, page))
                    local_y = doc_y - page * self._content_h
                    rects.append(QRectF(
                        self._gap + self._margin_l + min(x1, x2),
                        self._gap + page * (self._page_h + self._gap)
                        + self._margin_t + local_y,
                        max(1.0, abs(x2 - x1)),
                        max(12.0, line.height()),
                    ))
                block = block.next()
        except Exception:
            return []
        return rects

    def _cursor_rect(self) -> QRectF | None:
        if self._cursor_position < 0:
            return None
        try:
            cursor = QTextCursor(self._doc)
            cursor.setPosition(min(self._cursor_position,
                                   max(0, self._doc.characterCount() - 1)))
            block = cursor.block()
            pos_in_block = cursor.position() - block.position()
            layout = block.layout()
            if layout is None:
                return None
            line = layout.lineForTextPosition(pos_in_block)
            if not line.isValid():
                line = layout.lineAt(max(0, layout.lineCount() - 1))
            x = line.cursorToX(pos_in_block)
            if isinstance(x, tuple):
                x = x[0]
            block_rect = self._doc.documentLayout().blockBoundingRect(block)
            doc_y = block_rect.top() + line.y()
            page = int(doc_y // max(1.0, self._content_h))
            page = max(0, min(self._pages - 1, page))
            local_y = doc_y - page * self._content_h
            return QRectF(
                self._gap + self._margin_l + float(x),
                self._gap + page * (self._page_h + self._gap)
                + self._margin_t + local_y,
                1.4, max(12.0, line.height()),
            )
        except Exception:
            return None

    def set_zoom(self, zoom: float):
        self._zoom = max(0.5, min(2.0, zoom))
        self._recalc()

    def _page_number_text(self, index: int) -> str:
        fmt = self._page_number.get("format", "- 1 -")
        start = int(self._page_number.get("start", 1))
        current = start + index
        return (fmt.replace("1", str(current), 1)
                .replace("N", str(self._pages)))

    def _draw_header_footer(self, painter, page_rect, index):
        if self._header:
            font = QFont("Microsoft YaHei")
            font.setPointSize(9)
            painter.setFont(font)
            painter.setPen(QColor("#666666"))
            rect = QRectF(page_rect.x() + self._margin_l,
                          page_rect.y() + _cm_to_px(0.7),
                          self._content_w, _cm_to_px(1.0))
            painter.drawText(rect, Qt.AlignHCenter | Qt.AlignVCenter, self._header)

        if self._footer:
            font = QFont("Microsoft YaHei")
            font.setPointSize(9)
            painter.setFont(font)
            painter.setPen(QColor("#666666"))
            rect = QRectF(page_rect.x() + self._margin_l,
                          page_rect.y() + self._page_h - _cm_to_px(1.7),
                          self._content_w, _cm_to_px(1.0))
            painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, self._footer)

        if self._page_number.get("enabled", True):
            font = QFont("Microsoft YaHei")
            font.setPointSize(int(self._page_number.get("fontsize", 9)))
            painter.setFont(font)
            painter.setPen(QColor("#888888"))
            position = self._page_number.get("position", "底部居中")
            top = "顶部" in position
            y = (page_rect.y() + _cm_to_px(0.7) if top
                 else page_rect.y() + self._page_h - _cm_to_px(1.1))
            rect = QRectF(page_rect.x() + self._margin_l, y,
                          self._content_w, _cm_to_px(1.0))
            align = Qt.AlignHCenter
            if "右" in position:
                align = Qt.AlignRight
            elif "左" in position:
                align = Qt.AlignLeft
            painter.drawText(rect, align | Qt.AlignVCenter,
                             self._page_number_text(index))

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def mousePressEvent(self, event):  # noqa: N802
        pos = self._position_at(event.position())
        if pos is not None:
            self.position_clicked.emit(pos)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        pos = self._position_at(event.position())
        if pos is not None:
            self.edit_requested.emit(pos)
        super().mouseDoubleClickEvent(event)

    def _position_at(self, point: QPointF) -> int | None:
        """把视口点击坐标映射为 QTextDocument 位置。"""
        try:
            x = point.x() / self._scale
            y = point.y() / self._scale
            index = int((y - self._gap) // (self._page_h + self._gap))
            if index < 0 or index >= self._pages:
                return None
            page_y = self._gap + index * (self._page_h + self._gap)
            in_x = x - (self._gap + self._margin_l)
            in_y = y - (page_y + self._margin_t)
            if in_x < 0 or in_y < 0 or in_x > self._content_w or in_y > self._content_h:
                return None
            layout = self._doc.documentLayout()
            return layout.hitTest(QPointF(in_x, in_y), Qt.FuzzyHit)
        except Exception:
            return None

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#E9E9E9"))
        painter.scale(self._scale, self._scale)

        for i in range(self._pages):
            y = self._gap + i * (self._page_h + self._gap)
            page_rect = QRectF(self._gap, y, self._page_w, self._page_h)
            painter.fillRect(page_rect.adjusted(3, 3, 3, 3), QColor(0, 0, 0, 30))
            painter.fillRect(page_rect, QColor("#FFFFFF"))

            content_rect = QRectF(
                self._gap + self._margin_l,
                y + self._margin_t,
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

            painter.setPen(QColor(0, 0, 0, 18))
            painter.drawRect(content_rect)
            self._draw_header_footer(painter, page_rect, i)

        painter.setBrush(QColor(255, 220, 80, 130))
        painter.setPen(Qt.NoPen)
        for start, end in self._highlights:
            for rect in self._range_rects(start, end):
                painter.drawRect(rect)
        painter.setBrush(QColor(26, 115, 232, 70))
        for rect in self._selection_rects():
            painter.drawRect(rect)
        painter.setBrush(Qt.NoBrush)

        if self._preedit_text:
            rect = self._cursor_rect()
            if rect is not None:
                font = QFont("Microsoft YaHei")
                font.setPointSize(11)
                font.setUnderline(True)
                painter.setFont(font)
                painter.setPen(QColor("#1A73E8"))
                painter.drawText(QRectF(rect.x(), rect.y() - 2, 240, rect.height() + 4),
                                 Qt.AlignLeft | Qt.AlignVCenter,
                                 self._preedit_text)

        if self._cursor_visible and self._cursor_position >= 0:
            rect = self._cursor_rect()
            if rect is not None:
                painter.fillRect(rect, QColor("#1A73E8"))
        painter.end()


class SinglePageEditorDialog(QDialog):
    """M2 原型：单个纸张页面尺寸的编辑窗口。

    说明：
      - 编辑的是整篇文档的副本，窗口尺寸限制为一页内容区；
      - 打开时滚动到指定页起始位置；
      - 确定后把编辑后的文档副本交给页面视图，再回写蜜写富文本。
    """

    def __init__(self, document: QTextDocument, page_settings: dict,
                 page_index: int = 0, parent=None, cross_objects=None):
        super().__init__(parent)
        self.setWindowTitle(tr("beewrite.page_view.edit_title", "📝 单页编辑（原型）"))
        self._doc = document
        margins = page_settings or {}
        w = _cm_to_px(A4_CM[0] - margins.get("margin_left", 3.17)
                      - margins.get("margin_right", 3.17))
        h = _cm_to_px(A4_CM[1] - margins.get("margin_top", 2.54)
                      - margins.get("margin_bottom", 2.54))
        self._edit = QTextEdit()
        self._edit.setDocument(self._doc)
        self._edit.setFixedSize(int(w), int(h))
        self._page_index = page_index
        self._edit.setStyleSheet(
            "QTextEdit{background:#FFF;color:#111;border:1px solid #CCC;}"
        )
        self._doc.setPageSize(QSizeF(w, h))
        # 选中指定页范围，编辑时优先只替换这一页
        page_count = max(1, self._doc.pageCount())
        page_index = max(0, min(page_index, page_count - 1))
        try:
            layout = self._doc.documentLayout()
            start = layout.hitTest(QPointF(0, page_index * h), Qt.FuzzyHit)
            end = layout.hitTest(
                QPointF(0, min((page_index + 1) * h, self._doc.size().height())),
                Qt.FuzzyHit,
            )
            if end <= start:
                end = self._doc.characterCount() - 1
            cursor = self._edit.textCursor()
            cursor.setPosition(max(0, start))
            cursor.setPosition(max(0, end), QTextCursor.KeepAnchor)
            self._edit.setTextCursor(cursor)
            self._edit.ensureCursorVisible()
        except Exception:
            pass

        btns = QHBoxLayout()
        btns.addStretch()
        ok = QPushButton("应用")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            f"原型：已选中第 {page_index + 1} 页范围；编辑只替换该页文本。"
        ))
        if cross_objects:
            warn = QLabel(
                f"⚠ 本页附近有 {len(cross_objects)} 个跨页图片/表格；"
                "应用时会整篇替换。"
            )
            warn.setWordWrap(True)
            layout.addWidget(warn)
        layout.addWidget(self._edit)
        layout.addLayout(btns)

    def document(self) -> QTextDocument:
        return self._doc


class PageViewDialog(QDialog):
    """纸张页面视图对话框。"""

    position_clicked = Signal(int)
    edit_requested = Signal(int)
    document_edited = Signal(object)

    def __init__(self, document: QTextDocument, page_settings: dict, parent=None,
                 header_text: str = "", footer_text: str = "",
                 page_number_config: dict | None = None, provider=None):
        super().__init__(parent)
        self.setWindowTitle(tr("beewrite.page_view.title", "📄 页面视图"))
        self.resize(980, 760)
        self._zoom = 100
        self._source = document
        self._settings = dict(page_settings or {})
        self._header = header_text or ""
        self._footer = footer_text or ""
        self._page_number = dict(page_number_config or {})
        self._provider = provider
        self._last_settings = self._settings_snapshot()

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
        edit_btn = QPushButton(tr("beewrite.page_view.edit", "编辑本页"))
        edit_btn.clicked.connect(self._open_single_page_editor)
        toolbar.addWidget(edit_btn)
        refresh = QPushButton(tr("beewrite.page_view.refresh", "刷新"))
        refresh.clicked.connect(self.refresh_document)
        toolbar.addWidget(refresh)
        close = QPushButton(tr("beewrite.page_view.close", "关闭"))
        close.clicked.connect(self.reject)
        toolbar.addWidget(close)

        self._view = self._make_view(self._source)
        self._view.position_clicked.connect(self.position_clicked)
        self._view.edit_requested.connect(self.edit_requested)
        self._cross_objects = find_cross_page_objects(
            self._view._doc, self._view._content_h)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setWidget(self._view)
        self._scroll.setAlignment(Qt.AlignHCenter | Qt.AlignTop)

        layout = QVBoxLayout(self)
        layout.addLayout(toolbar)
        if self._cross_objects:
            tip = QLabel(
                f"⚠ 检测到 {len(self._cross_objects)} 个跨页图片/表格；"
                "单页编辑会回退为整篇替换。"
            )
            tip.setWordWrap(True)
            layout.addWidget(tip)
        layout.addWidget(self._scroll, 1)
        self._update_label()

        self._timer = QTimer(self)
        self._timer.setInterval(700)
        self._timer.timeout.connect(self._poll_settings)
        if provider is not None:
            self._timer.start()

    def _make_view(self, doc):
        return PaperPageView(
            doc, self._settings, self._header, self._footer,
            self._page_number,
        )

    def _settings_snapshot(self):
        return (
            tuple(sorted(self._settings.items())),
            self._header, self._footer,
            tuple(sorted(self._page_number.items())),
        )

    def _poll_settings(self):
        if self._provider is None or not self.isVisible():
            return
        try:
            doc, settings, header, footer, page_number = self._provider()
        except Exception:
            return
        self._source = doc
        self._settings = dict(settings or {})
        self._header = header or ""
        self._footer = footer or ""
        self._page_number = dict(page_number or {})
        snapshot = self._settings_snapshot()
        if snapshot != self._last_settings:
            self._last_settings = snapshot
            self.refresh_document()

    def _current_page(self) -> int:
        try:
            y = self._scroll.verticalScrollBar().value()
            step = (self._view._page_h + self._view._gap) * self._view._scale
            return max(0, min(self._view.pages - 1, int(y // step)))
        except Exception:
            return 0

    def _open_single_page_editor(self):
        page = self._current_page()
        dialog = SinglePageEditorDialog(
            build_page_document(self._source), self._settings, page, self,
            cross_objects=self._cross_objects,
        )
        if dialog.exec() == QDialog.Accepted:
            edited = dialog.document().clone()
            self._source = edited
            self.document_edited.emit(edited)
            self.refresh_document()

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
        if self._provider is not None:
            try:
                doc, settings, header, footer, page_number = self._provider()
                self._source = doc
                self._settings = dict(settings or {})
                self._header = header or ""
                self._footer = footer or ""
                self._page_number = dict(page_number or {})
                self._last_settings = self._settings_snapshot()
            except Exception:
                pass
        old = self._scroll.takeWidget()
        if old is not None:
            old.deleteLater()
        self._view = self._make_view(self._source)
        self._view.position_clicked.connect(self.position_clicked)
        self._view.edit_requested.connect(self.edit_requested)
        self._cross_objects = find_cross_page_objects(
            self._view._doc, self._view._content_h)
        self._scroll.setWidget(self._view)
        self._view.set_zoom(self._zoom / 100.0)
        self._update_label()
