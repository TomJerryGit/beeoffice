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
