"""S4.1/S5：高对比度主题与 M2 单页编辑原型。"""
from PySide6.QtWidgets import QPushButton
from PySide6.QtTest import QTest


def test_high_contrast_stylesheet():
    from beeoffice.theme import Theme

    old = Theme.is_high_contrast()
    try:
        Theme.set_high_contrast(True)
        qss = Theme.get_stylesheet()
        assert "#000000" in qss
        assert "2px solid" in qss
    finally:
        Theme.set_high_contrast(old)


def test_high_contrast_editor_styles(beewrite_editor):
    from beeoffice.theme import Theme

    editor = beewrite_editor
    old = Theme.is_high_contrast()
    try:
        Theme.set_high_contrast(True)
        editor.apply_theme()
        assert "#000000" in editor.markdown_editor.styleSheet().lower()
        assert "#000000" in editor.rich_editor.styleSheet().lower()
        assert "#000000" in editor.preview.styleSheet().lower()
    finally:
        Theme.set_high_contrast(old)
        editor.apply_theme()


def test_single_page_editor_prototype(qtbot):
    from beeoffice.plugins.beewrite_page_view import (
        SinglePageEditorDialog, build_page_document,
    )

    doc = build_page_document(markdown_text="# 标题\n\n第一段\n\n第二段")
    dialog = SinglePageEditorDialog(doc, {}, 0)
    qtbot.addWidget(dialog)
    dialog.show()
    assert dialog.document().toPlainText().strip()
    assert dialog._edit.isReadOnly() is False
    # 原型至少提供了应用/取消按钮
    buttons = dialog.findChildren(QPushButton)
    assert any(b.text() == "应用" for b in buttons)
    dialog.close()


def test_single_page_selects_page_range(qtbot):
    from PySide6.QtGui import QTextDocument
    from beeoffice.plugins.beewrite_page_view import SinglePageEditorDialog

    doc = QTextDocument()
    doc.setHtml("<p>" + "</p><p>".join(f"第 {i} 段" for i in range(120)) + "</p>")
    dialog = SinglePageEditorDialog(doc, {}, 0)
    qtbot.addWidget(dialog)
    dialog.show()
    cursor = dialog._edit.textCursor()
    assert cursor.hasSelection()
    assert cursor.selectedText().strip()
    dialog.close()


def test_single_page_keeps_table(qtbot):
    from PySide6.QtGui import QTextDocument
    from beeoffice.plugins.beewrite_page_view import SinglePageEditorDialog

    doc = QTextDocument()
    doc.setHtml("<table><tr><td>A</td><td>B</td></tr></table>")
    dialog = SinglePageEditorDialog(doc, {}, 0)
    qtbot.addWidget(dialog)
    assert "<table" in dialog.document().toHtml().lower()
    dialog.close()


def test_page_edit_apply_preserves_undo(beewrite_editor):
    from beeoffice.plugins.beewrite_page_view import build_page_document

    ed = beewrite_editor
    ed.set_content("# 原文档\n\n原始内容")
    ed._switch_mode("rich_text")
    edited = build_page_document(markdown_text="# 新文档\n\n修改后的内容")
    ed._apply_page_edit(edited)
    assert "修改后的内容" in ed.content()
    ed._undo()
    assert "原始内容" in ed.content()


def test_cross_page_table_detection(qtbot):
    from PySide6.QtCore import QSizeF
    from PySide6.QtGui import QTextDocument
    from beeoffice.plugins.beewrite_page_view import (
        SinglePageEditorDialog, find_cross_page_objects,
    )

    rows = "".join(f"<tr><td>row {i}</td><td>value {i}</td></tr>" for i in range(40))
    doc = QTextDocument()
    doc.setHtml(f"<table>{rows}</table>")
    doc.setPageSize(QSizeF(300, 200))
    objects = find_cross_page_objects(doc, 200)
    assert any(o["type"] == "table" for o in objects), objects

    dialog = SinglePageEditorDialog(doc, {}, 0, cross_objects=objects)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.close()


def test_page_overlay_toggle(beewrite_editor):
    ed = beewrite_editor
    ed._set_page_overlay_enabled(True)
    assert ed._page_overlay.is_enabled()
    assert not ed._page_overlay.isHidden()
    ed._set_page_overlay_enabled(False)
    assert not ed._page_overlay.is_enabled()


def test_page_scroll_navigation(beewrite_editor):
    ed = beewrite_editor
    ed.set_content("\n\n".join(f"第 {i} 段" for i in range(200)))
    ed._switch_mode("rich_text")
    ed._set_page_overlay_enabled(True)
    before = ed.rich_editor.verticalScrollBar().value()
    ed._page_next()
    after = ed.rich_editor.verticalScrollBar().value()
    assert after >= before
    ed._page_prev()


def test_paged_canvas_toggle(beewrite_editor):
    ed = beewrite_editor
    ed.set_content("\n\n".join(f"第 {i} 段分页测试内容" for i in range(300)))
    ed._switch_mode("rich_text")
    ed._toggle_paged_canvas(True)
    assert ed.editor_stack.currentWidget() is ed._paged_canvas
    assert ed._paged_canvas.page_count() >= 1
    from PySide6.QtCore import Qt
    assert ed._paged_canvas._scroll.alignment() & Qt.AlignHCenter
    ed._toggle_paged_canvas(False)
    assert ed.editor_stack.currentWidget() is ed._rich_frame


def test_paged_canvas_click_returns_editor(beewrite_editor):
    ed = beewrite_editor
    ed.set_content("abcdef\n\n第二段")
    ed._switch_mode("rich_text")
    ed._toggle_paged_canvas(True)
    ed._on_paged_canvas_click(3)
    assert ed.editor_stack.currentWidget() is ed._rich_frame
    assert ed.rich_editor.textCursor().position() == 3


def test_paged_canvas_keyboard_editing(beewrite_editor):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent

    ed = beewrite_editor
    ed.set_content("abcdef")
    ed._switch_mode("rich_text")
    ed._toggle_paged_canvas(True)
    canvas = ed._paged_canvas
    canvas._set_cursor(3)
    canvas.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_X, Qt.NoModifier, "X"))
    assert "abcXdef" in ed.rich_editor.toPlainText()
    canvas.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Backspace, Qt.NoModifier))
    assert "abcdef" in ed.rich_editor.toPlainText()
    assert canvas._view._cursor_position >= 0


def test_paged_canvas_shift_selection_and_clipboard(beewrite_editor):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent, QGuiApplication

    ed = beewrite_editor
    ed.set_content("abcdef")
    ed._switch_mode("rich_text")
    ed._toggle_paged_canvas(True)
    canvas = ed._paged_canvas
    canvas._set_cursor(0)
    canvas.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Right,
                                   Qt.ShiftModifier))
    assert canvas._selection_bounds() == (0, 1)
    canvas.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Right,
                                   Qt.ShiftModifier))
    assert canvas._selection_bounds() == (0, 2)
    canvas.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_C,
                                   Qt.ControlModifier))
    assert QGuiApplication.clipboard().text() == "ab"
    assert ed.rich_editor.textCursor().hasSelection()
    assert ed.rich_editor.textCursor().selectedText() == "ab"


def test_paged_canvas_mouse_selection_and_ime(beewrite_editor):
    from PySide6.QtGui import QInputMethodEvent

    ed = beewrite_editor
    ed.set_content("abcdef")
    ed._switch_mode("rich_text")
    ed._toggle_paged_canvas(True)
    canvas = ed._paged_canvas
    canvas._set_cursor(1)
    canvas._set_cursor(4, extend=True)
    assert canvas._selection_bounds() == (1, 4)
    canvas._set_cursor(6)
    event = QInputMethodEvent()
    event.setCommitString("中文")
    canvas.inputMethodEvent(event)
    assert "abcdef中文" in ed.rich_editor.toPlainText()


def test_paged_canvas_formatting_sync(beewrite_editor):
    from PySide6.QtGui import QFont

    ed = beewrite_editor
    ed.set_content("abcdef")
    ed._switch_mode("rich_text")
    ed._toggle_paged_canvas(True)
    canvas = ed._paged_canvas
    canvas._set_cursor(0)
    canvas._set_cursor(3, extend=True)
    ed._toggle_bold()
    fmt = ed.rich_editor.document().findBlock(0).begin().fragment().charFormat()
    assert fmt.fontWeight() == QFont.Bold


def test_paged_canvas_search_highlight(beewrite_editor):
    ed = beewrite_editor
    ed.set_content("abc def abc")
    ed._switch_mode("rich_text")
    ed._toggle_paged_canvas(True)
    canvas = ed._paged_canvas
    canvas._open_search()
    canvas._search_edit.setText("abc")
    canvas._highlight_search()
    assert len(canvas._view._highlights) == 2
    canvas._search_next(True)
    assert canvas._selection_bounds() != (-1, -1)
    canvas._close_search()
    assert canvas._view._highlights == []


def test_paged_canvas_typing_debounced(beewrite_editor):
    import time
    from PySide6.QtCore import QEvent, QTimer, Qt
    from PySide6.QtGui import QKeyEvent

    ed = beewrite_editor
    ed.set_content("\n\n".join(f"第 {i} 段性能测试内容" for i in range(120)))
    ed._switch_mode("rich_text")
    ed._toggle_paged_canvas(True)
    canvas = ed._paged_canvas
    started = time.perf_counter()
    for _ in range(30):
        canvas.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_X, Qt.NoModifier, "x"))
    elapsed = time.perf_counter() - started
    assert elapsed < 5.0
    canvas._flush_refresh()
    assert not canvas._pending_refresh


def test_word_doc_enters_paged_edit(beewrite_editor):
    ed = beewrite_editor
    ed.set_content("abcdef")
    ed.set_doc_kind("word")
    ed._enter_paged_edit()
    assert ed.editor_stack.currentWidget() is ed._paged_canvas
    assert ed._paged_canvas.page_count() >= 1
    from PySide6.QtCore import Qt
    assert ed._paged_canvas._scroll.alignment() & Qt.AlignHCenter
    ed._toggle_paged_canvas(False)
    assert ed.editor_stack.currentWidget() is ed._rich_frame
    assert ed.rich_editor.document().pageSize().width() == -1


def test_paged_canvas_fit_width_and_zoom(beewrite_editor):
    ed = beewrite_editor
    ed.set_content("abcdef")
    ed._switch_mode("rich_text")
    ed._toggle_paged_canvas(True)
    canvas = ed._paged_canvas
    canvas.fit_width()
    assert canvas._fit_width_mode
    assert canvas._view._scale > 0
    before = canvas._view._scale
    canvas._zoom_in()
    assert canvas._view._scale >= before
    assert not canvas._fit_width_mode
    assert "%" in canvas._zoom_label.text()


def test_paged_canvas_table_in_place_edit(beewrite_editor):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent, QTextCursor

    ed = beewrite_editor
    ed._switch_mode("rich_text")
    ed.rich_editor.setHtml(
        '<table border="1"><tr><td>cell1</td><td>cell2</td></tr></table>'
    )
    ed._enter_paged_edit()
    doc = ed.rich_editor.document()
    found = doc.find("cell1")
    assert not found.isNull()
    canvas = ed._paged_canvas
    canvas._set_cursor(found.position() + 2)
    canvas.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_X, Qt.NoModifier, "X"))
    assert "X" in ed.rich_editor.toPlainText()
    assert list(doc.rootFrame().childFrames())


def test_paged_canvas_image_select_delete(beewrite_editor, tmp_path):
    from pathlib import Path
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent, QTextCursor, QTextImageFormat

    ed = beewrite_editor
    ed._switch_mode("rich_text")
    src = (Path(__file__).resolve().parents[2]
           / "docs" / "ui-baseline" / "2026-11-05" / "06-page-overlay.png")
    img = tmp_path / "tiny.png"
    img.write_bytes(src.read_bytes())
    doc = ed.rich_editor.document()
    cursor = QTextCursor(doc)
    cursor.movePosition(QTextCursor.End)
    fmt = QTextImageFormat()
    fmt.setName(str(img))
    fmt.setWidth(20)
    fmt.setHeight(20)
    cursor.insertImage(fmt)
    ed._enter_paged_edit()
    block = doc.begin()
    pos = None
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid() and frag.charFormat().isImageFormat():
                pos = frag.position()
                break
            it += 1
        if pos is not None:
            break
        block = block.next()
    assert pos is not None
    canvas = ed._paged_canvas
    canvas._set_cursor(pos)
    canvas.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier))
    has_image = False
    block = ed.rich_editor.document().begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid() and frag.charFormat().isImageFormat():
                has_image = True
            it += 1
        block = block.next()
    assert not has_image


def test_paged_canvas_table_row_column_ops(beewrite_editor):
    ed = beewrite_editor
    ed._switch_mode("rich_text")
    ed.rich_editor.setHtml(
        '<table border="1"><tr><td>a</td><td>b</td></tr>'
        '<tr><td>c</td><td>d</td></tr></table>'
    )
    ed._enter_paged_edit()
    canvas = ed._paged_canvas
    doc = ed.rich_editor.document()
    found = doc.find("a")
    canvas._set_cursor(found.position())
    table = canvas._current_table()
    assert table is not None
    rows, cols = table.rows(), table.columns()
    assert canvas.insert_table_row(False)
    assert table.rows() == rows + 1
    assert canvas.insert_table_column()
    assert table.columns() == cols + 1
    assert canvas.delete_table_column()
    assert table.columns() == cols
    assert canvas.delete_table_row()
    assert table.rows() == rows


def test_paged_canvas_image_resize_delete(beewrite_editor, tmp_path):
    from pathlib import Path
    from PySide6.QtGui import QTextCursor, QTextImageFormat

    ed = beewrite_editor
    ed._switch_mode("rich_text")
    src = (Path(__file__).resolve().parents[2]
           / "docs" / "ui-baseline" / "2026-11-05" / "06-page-overlay.png")
    img = tmp_path / "img.png"
    img.write_bytes(src.read_bytes())
    doc = ed.rich_editor.document()
    cursor = QTextCursor(doc)
    cursor.movePosition(QTextCursor.End)
    fmt = QTextImageFormat()
    fmt.setName(str(img))
    fmt.setWidth(200)
    fmt.setHeight(120)
    cursor.insertImage(fmt)
    ed._enter_paged_edit()
    canvas = ed._paged_canvas
    # 找到图片位置
    pos = None
    block = doc.begin()
    while block.isValid() and pos is None:
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid() and frag.charFormat().isImageFormat():
                pos = frag.position()
                break
            it += 1
        block = block.next()
    assert pos is not None
    canvas._set_cursor(pos)
    assert canvas.resize_image(50)
    assert canvas.delete_image()
    has_image = False
    block = doc.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid() and frag.charFormat().isImageFormat():
                has_image = True
            it += 1
        block = block.next()
    assert not has_image


def test_paged_canvas_alignment_list_heading(beewrite_editor):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QTextCursor

    ed = beewrite_editor
    ed.set_content("hello")
    ed._switch_mode("rich_text")
    ed._enter_paged_edit()
    canvas = ed._paged_canvas
    canvas._set_cursor(0)
    canvas._set_cursor(5, extend=True)
    canvas.set_alignment(Qt.AlignCenter)
    bf = ed.rich_editor.document().findBlock(0).blockFormat()
    assert bf.alignment() & Qt.AlignHCenter
    canvas.set_heading(1)
    assert ed.rich_editor.document().findBlock(0).blockFormat().headingLevel() == 1
    canvas._set_cursor(0)
    canvas.insert_list(False)
    assert ed.rich_editor.document().findBlock(0).textList() is not None
