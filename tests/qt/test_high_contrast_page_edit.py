"""S4.1/S5：高对比度主题与 M2 单页编辑原型。"""
from PySide6.QtWidgets import QPushButton


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
