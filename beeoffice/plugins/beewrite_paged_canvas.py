# beeoffice/plugins/beewrite_paged_canvas.py
"""M3.1-M3.3 分页画布：真实分页、页间间距、页眉页脚、光标、选择、IME 与键盘编辑。

说明：
  - 画布用源 QTextDocument 的克隆绘制；
  - 光标/选择/键盘/IME 编辑写回源文档，再重建画布；
  - 复杂表格内编辑仍由主编辑区承担。
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QRect, QTimer, Qt, Signal
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
    selection_changed = Signal(int, int)
    find_requested = Signal()

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
        self._selection_anchor = None
        self._cursor_visible = True
        self._preedit = ""
        self._dragging = False

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
        self.setAttribute(Qt.WA_InputMethodEnabled, True)
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
        self._sync_view_state()

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
            self._view.installEventFilter(self)
            self._scroll.setWidget(self._view)
            self._label.setText(f"共 {self._view.pages} 页")
            self._sync_view_state()
        except Exception:
            pass

    def page_count(self) -> int:
        return self._view.pages if self._view is not None else 0

    # ------------------------------------------------------------------
    def _selection_bounds(self) -> tuple[int, int]:
        if self._source is None or self._selection_anchor is None:
            return -1, -1
        if self._selection_anchor == self._cursor_position:
            return -1, -1
        return (min(self._selection_anchor, self._cursor_position),
                max(self._selection_anchor, self._cursor_position))

    def _sync_view_state(self):
        if self._view is None:
            return
        start, end = self._selection_bounds()
        self._view.set_selection(start, end)
        self._view.set_cursor_position(self._cursor_position)
        self._view.set_cursor_visible(self._cursor_visible)
        self._view.set_preedit(self._preedit)
        self.selection_changed.emit(start, end)

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

    def _set_cursor(self, position: int, extend: bool = False):
        if self._source is None:
            return
        max_pos = max(0, self._source.characterCount() - 1)
        new_pos = max(0, min(int(position), max_pos))
        if extend:
            if self._selection_anchor is None:
                self._selection_anchor = self._cursor_position
        else:
            self._selection_anchor = None
        self._cursor_position = new_pos
        self._sync_view_state()

    def _cursor_with_selection(self) -> QTextCursor:
        cursor = QTextCursor(self._source)
        start, end = self._selection_bounds()
        if start >= 0:
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
        else:
            cursor.setPosition(self._cursor_position)
        return cursor

    def _sync_after_edit(self):
        source = self._source
        if source is None:
            return
        self._selection_anchor = None
        self._preedit = ""
        self._cursor_position = max(
            0, min(self._cursor_position, max(0, source.characterCount() - 1))
        )
        self.refresh_from(
            source, self._settings, self._header, self._footer,
            self._page_number,
        )
        self.content_changed.emit()

    # ------------------------------------------------------------------
    def eventFilter(self, obj, event):  # noqa: N802
        if not self._editable or obj is not self._view:
            return super().eventFilter(obj, event)
        etype = event.type()
        if etype == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            pos = self._view._position_at(event.position())
            if pos is not None:
                self._dragging = True
                self._set_cursor(pos)
                self.setFocus()
                return True
        elif etype == QEvent.MouseMove and self._dragging:
            if event.buttons() & Qt.LeftButton:
                pos = self._view._position_at(event.position())
                if pos is not None:
                    self._set_cursor(pos, extend=True)
                return True
        elif etype == QEvent.MouseButtonRelease and self._dragging:
            self._dragging = False
            return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    def keyPressEvent(self, event):  # noqa: N802
        if not self._editable or self._source is None:
            super().keyPressEvent(event)
            return
        key = event.key()
        mods = event.modifiers()
        move_ops = {
            Qt.Key_Left: QTextCursor.PreviousCharacter,
            Qt.Key_Right: QTextCursor.NextCharacter,
            Qt.Key_Up: QTextCursor.Up,
            Qt.Key_Down: QTextCursor.Down,
            Qt.Key_Home: QTextCursor.StartOfLine,
            Qt.Key_End: QTextCursor.EndOfLine,
        }

        if key in move_ops and (mods & Qt.ShiftModifier):
            cursor = self._cursor_with_selection()
            cursor.movePosition(move_ops[key], QTextCursor.KeepAnchor)
            self._selection_anchor = cursor.anchor()
            self._cursor_position = cursor.position()
            self._sync_view_state()
            event.accept()
            return

        cursor = self._cursor_with_selection()
        has_selection = cursor.hasSelection()
        handled = True

        if key == Qt.Key_F and (mods & Qt.ControlModifier):
            self.find_requested.emit()
            event.accept()
            return
        if key == Qt.Key_A and (mods & Qt.ControlModifier):
            self._selection_anchor = 0
            self._cursor_position = max(0, self._source.characterCount() - 1)
            self._sync_view_state()
            event.accept()
            return
        if key == Qt.Key_C and (mods & Qt.ControlModifier):
            QApplication.clipboard().setText(cursor.selectedText())
            event.accept()
            return
        if key == Qt.Key_X and (mods & Qt.ControlModifier):
            QApplication.clipboard().setText(cursor.selectedText())
            cursor.removeSelectedText()
            self._cursor_position = cursor.position()
            self._sync_after_edit()
            event.accept()
            return
        if key == Qt.Key_V and (mods & Qt.ControlModifier):
            if has_selection:
                cursor.removeSelectedText()
            cursor.insertText(QApplication.clipboard().text())
        elif key == Qt.Key_Z and (mods & Qt.ControlModifier):
            self._source.undo()
            self._cursor_position = min(
                self._cursor_position,
                max(0, self._source.characterCount() - 1),
            )
            cursor = QTextCursor(self._source)
            cursor.setPosition(self._cursor_position)
        elif key == Qt.Key_Y and (mods & Qt.ControlModifier):
            self._source.redo()
            cursor = QTextCursor(self._source)
            cursor.setPosition(self._cursor_position)
        elif key == Qt.Key_Backspace:
            if has_selection:
                cursor.removeSelectedText()
            else:
                cursor.deletePreviousChar()
        elif key == Qt.Key_Delete:
            if has_selection:
                cursor.removeSelectedText()
            else:
                cursor.deleteChar()
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            if has_selection:
                cursor.removeSelectedText()
            cursor.insertBlock()
        elif key in move_ops:
            cursor.movePosition(move_ops[key])
        elif key in (Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt,
                     Qt.Key_Meta, Qt.Key_CapsLock, Qt.Key_Tab,
                     Qt.Key_Escape):
            handled = False
        elif event.text() and not (mods & (Qt.ControlModifier | Qt.AltModifier)):
            if has_selection:
                cursor.removeSelectedText()
            cursor.insertText(event.text())
        else:
            handled = False

        if handled:
            self._cursor_position = cursor.position()
            self._sync_after_edit()
            event.accept()
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------------
    def inputMethodEvent(self, event):  # noqa: N802
        if not self._editable or self._source is None:
            super().inputMethodEvent(event)
            return
        commit = event.commitString()
        preedit = event.preeditString()
        if commit:
            cursor = self._cursor_with_selection()
            if cursor.hasSelection():
                cursor.removeSelectedText()
            cursor.insertText(commit)
            self._cursor_position = cursor.position()
            self._selection_anchor = None
            self._preedit = ""
            self._sync_after_edit()
        else:
            self._preedit = preedit
            self._sync_view_state()
        event.accept()

    def inputMethodQuery(self, query):  # noqa: N802
        if self._view is None:
            return super().inputMethodQuery(query)
        if query == Qt.ImCursorRectangle:
            rect = self._view._cursor_rect()
            if rect is None:
                return QRect()
            top_left = self._view.mapTo(self, rect.topLeft().toPoint())
            return QRect(top_left, rect.size().toSize())
        if query == Qt.ImCursorPosition:
            return self._cursor_position
        if query == Qt.ImAnchorPosition:
            return (self._selection_anchor
                    if self._selection_anchor is not None
                    else self._cursor_position)
        if query == Qt.ImSurroundingText:
            return self._source.toPlainText() if self._source else ""
        if query == Qt.ImCurrentSelection:
            cursor = self._cursor_with_selection()
            return cursor.selectedText() if cursor.hasSelection() else ""
        return super().inputMethodQuery(query)

    def mousePressEvent(self, event):  # noqa: N802
        self.setFocus()
        super().mousePressEvent(event)
