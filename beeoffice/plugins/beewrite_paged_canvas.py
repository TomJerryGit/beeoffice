# beeoffice/plugins/beewrite_paged_canvas.py
"""M3.1/M3.2/M3.3 分页画布：真实分页、页间间距、页眉页脚、光标与基础键盘编辑。

说明：
  - 画布用源 QTextDocument 的克隆绘制；
  - 光标/键盘编辑写回源文档，再重建画布；
  - 当前支持插入文本、回车、退格、删除、方向键、Home/End、Ctrl+V、Ctrl+Z/Y；
  - 复杂选择/输入法/表格内编辑仍由主编辑区承担。
"""
from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from beeoffice.theme import Theme
from beeoffice.plugins.beewrite_page_view import (
    PaperPageView,
    build_page_document,
)


class PagedCanvas(QWidget):
    position_clicked = Signal(int)
    content_changed = Signal()

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
        self._editable = False
        self._cursor_position = 0
        self._cursor_visible = True

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

        self.setFocusPolicy(Qt.StrongFocus)
        self._blink = QTimer(self)
        self._blink.setInterval(530)
        self._blink.timeout.connect(self._toggle_cursor)

    # ------------------------------------------------------------------
    def set_editable(self, editable: bool):
        self._editable = bool(editable)
        if self._editable:
            self.setFocus()
            self._blink.start()
        else:
            self._blink.stop()
        if self._view is not None:
            self._view.set_cursor_visible(self._cursor_visible)

    def is_editable(self) -> bool:
        return self._editable

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
            self._view.position_clicked.connect(self._on_position_clicked)
            self._scroll.setWidget(self._view)
            self._label.setText(f"共 {self._view.pages} 页")
            if self._editable:
                self._sync_cursor_to_view()
        except Exception:
            pass

    def page_count(self) -> int:
        return self._view.pages if self._view is not None else 0

    # ------------------------------------------------------------------
    def _on_position_clicked(self, position: int):
        if self._editable:
            self._set_cursor(position)
            self.setFocus()
            return
        self.position_clicked.emit(position)

    def _toggle_cursor(self):
        self._cursor_visible = not self._cursor_visible
        if self._view is not None:
            self._view.set_cursor_visible(self._cursor_visible)

    def _sync_cursor_to_view(self):
        if self._view is not None:
            self._view.set_cursor_position(self._cursor_position)
            self._view.set_cursor_visible(self._cursor_visible)

    def _set_cursor(self, position: int):
        if self._source is None:
            return
        max_pos = max(0, self._source.characterCount() - 1)
        self._cursor_position = max(0, min(int(position), max_pos))
        self._sync_cursor_to_view()

    def _document_cursor(self) -> QTextCursor:
        cursor = QTextCursor(self._source)
        cursor.setPosition(self._cursor_position)
        return cursor

    def _sync_after_edit(self):
        source = self._source
        if source is None:
            return
        self._cursor_position = max(
            0, min(self._cursor_position, max(0, source.characterCount() - 1))
        )
        self.refresh_from(
            source, self._settings, self._header, self._footer,
            self._page_number,
        )
        self._sync_cursor_to_view()
        self.content_changed.emit()

    # ------------------------------------------------------------------
    def keyPressEvent(self, event):  # noqa: N802
        if not self._editable or self._source is None:
            super().keyPressEvent(event)
            return
        cursor = self._document_cursor()
        key = event.key()
        mods = event.modifiers()
        handled = True

        if key == Qt.Key_Backspace:
            cursor.deletePreviousChar()
        elif key == Qt.Key_Delete:
            cursor.deleteChar()
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            cursor.insertBlock()
        elif key == Qt.Key_Left:
            cursor.movePosition(QTextCursor.PreviousCharacter)
        elif key == Qt.Key_Right:
            cursor.movePosition(QTextCursor.NextCharacter)
        elif key == Qt.Key_Up:
            cursor.movePosition(QTextCursor.Up)
        elif key == Qt.Key_Down:
            cursor.movePosition(QTextCursor.Down)
        elif key == Qt.Key_Home:
            cursor.movePosition(QTextCursor.StartOfLine)
        elif key == Qt.Key_End:
            cursor.movePosition(QTextCursor.EndOfLine)
        elif key == Qt.Key_V and (mods & Qt.ControlModifier):
            cursor.insertText(QApplication.clipboard().text())
        elif key == Qt.Key_Z and (mods & Qt.ControlModifier):
            self._source.undo()
            cursor = QTextCursor(self._source)
            cursor.movePosition(QTextCursor.End)
        elif key == Qt.Key_Y and (mods & Qt.ControlModifier):
            self._source.redo()
            cursor = QTextCursor(self._source)
            cursor.movePosition(QTextCursor.End)
        elif key in (Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt,
                     Qt.Key_Meta, Qt.Key_CapsLock, Qt.Key_Tab,
                     Qt.Key_Escape):
            handled = False
        elif event.text() and not (mods & (Qt.ControlModifier | Qt.AltModifier)):
            cursor.insertText(event.text())
        else:
            handled = False

        if handled:
            self._cursor_position = cursor.position()
            self._sync_after_edit()
            event.accept()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):  # noqa: N802
        self.setFocus()
        super().mousePressEvent(event)
