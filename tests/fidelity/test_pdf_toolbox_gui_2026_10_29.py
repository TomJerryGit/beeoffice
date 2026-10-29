# tests/fidelity/test_pdf_toolbox_gui_2026_10_29.py
"""S1：PDF 工具箱 GUI 冒烟测试（不弹文件对话框）。"""
from beeoffice.plugins.pdf_toolbox_dialog import OPERATIONS, PdfToolboxDialog


def test_dialog_operations_and_field_visibility(qtbot):
    dlg = PdfToolboxDialog()
    qtbot.addWidget(dlg)
    dlg.show()
    qtbot.wait(20)
    assert dlg.op_combo.count() == len(OPERATIONS)
    assert dlg.log.isReadOnly()

    # 加密：密码/权限可见，页码隐藏
    dlg.op_combo.setCurrentIndex(dlg.op_combo.findData("encrypt"))
    qtbot.wait(10)
    assert dlg.password_edit.isVisibleTo(dlg)
    assert dlg.allow_print.isVisibleTo(dlg)
    assert not dlg.pages_edit.isVisibleTo(dlg)

    # 水印
    dlg.op_combo.setCurrentIndex(dlg.op_combo.findData("watermark"))
    qtbot.wait(10)
    assert dlg.watermark_edit.isVisibleTo(dlg)


def test_dialog_validation_reports_missing_input(qtbot):
    dlg = PdfToolboxDialog()
    qtbot.addWidget(dlg)
    assert dlg._validate() is None
    assert "请先选择输入 PDF" in dlg.log.toPlainText()


def test_delete_requires_page_range(qtbot, tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    dlg = PdfToolboxDialog()
    qtbot.addWidget(dlg)
    dlg.op_combo.setCurrentIndex(dlg.op_combo.findData("delete"))
    dlg.input_edit.setText(str(pdf))
    dlg.output_edit.setText(str(tmp_path / "out.pdf"))
    assert dlg._validate() is None
    assert "删除页面必须填写页码范围" in dlg.log.toPlainText()
