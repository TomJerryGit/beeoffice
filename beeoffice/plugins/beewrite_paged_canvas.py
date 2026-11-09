# beeoffice/plugins/beewrite_paged_canvas.py
"""M3.1-M3.3 分页画布：真实分页、页间间距、页眉页脚、光标、选择、IME 与键盘编辑。

说明：
  - 画布用源 QTextDocument 的克隆绘制；
  - 光标/选择/键盘/IME 编辑写回源文档，再重建画布；
  - 复杂表格内编辑仍由主编辑区承担。
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QRect, QTimer, Qt, Signal
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from beeoffice.theme import Theme
from beeoffice.plugins.beewrite_page_view import (
    PaperPageView,
    find_cross_page_objects,
)


class PagedCanvas(QWidget):
    position_clicked = Signal(int)
    content_changed = Signal()
    selection_changed = Signal(int, int)
    find_requested = Signal()
    object_edit_requested = Signal(int)

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
        self._pending_refresh = False
        self._last_selection = (-1, -1)

        _t = Theme.tokens()
        self._label = QLabel("共 0 页")
        self._label.setStyleSheet(
            f"QLabel{{color:{_t['muted']};font-size:12px;padding:2px 8px;}}"
        )
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self._scroll.setStyleSheet(
            f"QScrollArea{{background:{_t['surface_alt']};border:none;}}"
        )

        self._search_bar = QWidget()
        search_layout = QHBoxLayout(self._search_bar)
        search_layout.setContentsMargins(8, 2, 8, 2)
        search_layout.setSpacing(4)
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("在分页画布中查找…")
        self._search_edit.returnPressed.connect(self._search_next)
        self._search_prev_btn = QPushButton("上一个")
        self._search_prev_btn.clicked.connect(lambda: self._search_next(False))
        self._search_next_btn = QPushButton("下一个")
        self._search_next_btn.clicked.connect(lambda: self._search_next(True))
        self._search_close_btn = QPushButton("关闭")
        self._search_close_btn.clicked.connect(self._close_search)
        search_layout.addWidget(self._search_edit, 1)
        search_layout.addWidget(self._search_prev_btn)
        search_layout.addWidget(self._search_next_btn)
        search_layout.addWidget(self._search_close_btn)
        self._search_bar.hide()
        self._object_label = QLabel("")
        self._object_label.setWordWrap(True)
        self._object_label.setStyleSheet(
            f"QLabel{{color:{_t['muted']};background:{_t['surface_alt']};"
            "font-size:11px;padding:3px 8px;}"
        )
        self._object_label.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._label)
        layout.addWidget(self._object_label)
        layout.addWidget(self._search_bar)
        layout.addWidget(self._scroll, 1)

        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_InputMethodEnabled, True)
        self._blink = QTimer(self)
        self._blink.setInterval(530)
        self._blink.timeout.connect(self._toggle_cursor)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(35)
        self._refresh_timer.timeout.connect(self._flush_refresh)

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
            if self._view is not None and self._view._doc is document:
                self._view._settings = dict(self._settings)
                self._view._header = self._header
                self._view._footer = self._footer
                self._view._page_number = dict(self._page_number)
                self._view.recalc()
            else:
                old = self._scroll.takeWidget()
                if old is not None:
                    old.deleteLater()
                self._view = PaperPageView(
                    document, self._settings,
                    header_text=self._header,
                    footer_text=self._footer,
                    page_number_config=self._page_number,
                )
                self._view.position_clicked.connect(self._on_position_clicked)
                self._view.installEventFilter(self)
                self._scroll.setWidget(self._view)
            self._label.setText(f"共 {self._view.pages} 页")
            try:
                cross = find_cross_page_objects(
                    self._view._doc, self._view._content_h
                )
            except Exception:
                cross = []
            if cross:
                self._object_label.setText(
                    f"⚠ 检测到 {len(cross)} 个跨页表格/图片；"
                    "点击对象将切回连续编辑"
                )
                self._object_label.show()
            else:
                self._object_label.hide()
            self._sync_view_state()
        except Exception:
            pass

    def page_count(self) -> int:
        return self._view.pages if self._view is not None else 0

    def release_source_layout(self):
        """离开分页画布时恢复源文档的连续布局。"""
        if self._source is not None:
            try:
                from PySide6.QtCore import QSizeF
                self._source.setPageSize(QSizeF(-1, -1))
            except Exception:
                pass

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
        if (start, end) != self._last_selection:
            self._last_selection = (start, end)
            self.selection_changed.emit(start, end)

    def _on_position_clicked(self, position: int):
        if self._editable:
            if self._object_at(position):
                self.object_edit_requested.emit(position)
                return
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
        self._sync_view_state()
        self._pending_refresh = True
        self._refresh_timer.start()
        self.content_changed.emit()

    def _flush_refresh(self):
        if not self._pending_refresh or self._source is None:
            return
        self._pending_refresh = False
        if self._view is not None:
            self._view.recalc()
            self._label.setText(f"共 {self._view.pages} 页")
            self._sync_view_state()

    # ------------------------------------------------------------------
    def _open_search(self):
        self._search_bar.show()
        self._search_edit.setFocus()
        self._search_edit.selectAll()
        self._highlight_search()

    def _close_search(self):
        self._search_bar.hide()
        if self._view is not None:
            self._view.set_highlights([])
        self.setFocus()

    def _highlight_search(self):
        if self._view is None or self._source is None:
            return
        text = self._search_edit.text()
        ranges = []
        if text:
            cursor = QTextCursor(self._source)
            while len(ranges) < 500:
                found = self._source.find(text, cursor, QTextDocument.FindFlags())
                if found.isNull():
                    break
                ranges.append((found.selectionStart(), found.selectionEnd()))
                cursor = found
            self._view.set_highlights(ranges)

    def _search_next(self, forward=True):
        if self._pending_refresh:
            self._flush_refresh()
        text = self._search_edit.text()
        if not text or self._source is None:
            return
        cursor = QTextCursor(self._source)
        cursor.setPosition(max(0, self._cursor_position))
        found = self._source.find(text, cursor, QTextDocument.FindFlags())
        if found.isNull() and not forward:
            found = self._source.find(
                text, QTextCursor(self._source), QTextDocument.FindFlags()
            )
        elif found.isNull():
            found = self._source.find(
                text, QTextCursor(self._source), QTextDocument.FindFlags()
            )
        if found.isNull():
            return
        self._selection_anchor = found.selectionStart()
        self._cursor_position = found.selectionEnd()
        self._sync_view_state()
        if self._view is not None:
            rect = self._view._cursor_rect()
            if rect is not None:
                self._scroll.ensureVisible(
                    int(rect.center().x()), int(rect.center().y()), 40, 40
                )

    # ------------------------------------------------------------------
    def _object_at(self, position: int) -> bool:
        if self._source is None:
            return False
        try:
            cursor = QTextCursor(self._source)
            cursor.setPosition(max(0, min(position,
                                           self._source.characterCount() - 1)))
            if cursor.currentTable() is not None:
                return True
            block = cursor.block()
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if (frag.isValid()
                        and frag.position() <= position
                        < frag.position() + frag.length()
                        and frag.charFormat().isImageFormat()):
                    return True
                it += 1
        except Exception:
            return False
        return False

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
            self._open_search()
            event.accept()
            return
        if key == Qt.Key_Escape and self._search_bar.isVisible():
            self._close_search()
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
