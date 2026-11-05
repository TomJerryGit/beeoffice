"""S4 UI-03：关键对话框 Esc 关闭与键盘焦点契约。"""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox


def _make_comment(app):
    from beeoffice.plugins.beewrite_comment import CommentEditDialog
    return CommentEditDialog(parent=app, initial_text="测试批注")


def _make_pdf_pages(app):
    from beeoffice.plugins.pdf_pages_dialog import PdfPagesDialog
    return PdfPagesDialog(parent=app)


def _make_formula(app):
    from beeoffice.plugins.beewrite_formula import FormulaDialog
    return FormulaDialog(parent=app)


def _make_cloud(app):
    from beeoffice.cloud_settings import CloudSettingsDialog
    return CloudSettingsDialog(parent=app)


@pytest.mark.parametrize("factory", [
    _make_comment, _make_pdf_pages, _make_formula, _make_cloud,
])
def test_escape_closes_dialog(app, qtbot, factory):
    dialog = factory(app)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(30)
    QTest.keyClick(dialog, Qt.Key_Escape)
    qtbot.wait(30)
    assert not dialog.isVisible(), f"{type(dialog).__name__} 未响应 Esc"
    assert dialog.result() == QDialog.Rejected


def test_comment_dialog_has_ok_cancel(app, qtbot):
    dialog = _make_comment(app)
    qtbot.addWidget(dialog)
    box = dialog.findChild(QDialogButtonBox)
    assert box is not None
    assert box.button(QDialogButtonBox.Ok) is not None
    assert box.button(QDialogButtonBox.Cancel) is not None


def test_focus_chain_reaches_buttons(app, qtbot):
    dialog = _make_comment(app)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.activateWindow()
    dialog._edit.setFocus()
    qtbot.wait(30)

    seen = set()
    for _ in range(12):
        dialog.focusNextChild()
        QApplication.processEvents()
        widget = QApplication.focusWidget()
        if widget is not None:
            seen.add(widget.__class__.__name__)
    assert seen, "焦点链为空"
    # 至少能从编辑框走到一个按钮
    assert "QPushButton" in seen, f"Tab 未到达按钮：{seen}"
