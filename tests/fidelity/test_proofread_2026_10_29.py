"""S2 校对体检 MVP。"""
from types import SimpleNamespace

from PySide6.QtWidgets import QTextEdit

from beeoffice.plugins.proofread_dialog import ProofreadDialog, scan_text


def test_scan_rules():
    issues = scan_text("中文,标点\nTODO 这里\n行尾  \n重复，，标点")
    kinds = {issue.kind for issue in issues}
    assert "中英文标点混用" in kinds
    assert "待办标记" in kinds
    assert "行尾空白" in kinds
    assert "重复标点" in kinds


def test_scan_clean():
    assert scan_text("这是正常的一行。\n第二行也正常。") == []


def test_dialog_reads_current_editor(qtbot):
    editor = QTextEdit()
    editor.setPlainText("中文,标点")
    app = SimpleNamespace(tab_manager=SimpleNamespace(currentWidget=lambda: SimpleNamespace(rich_editor=editor)))
    dlg = ProofreadDialog(app)
    qtbot.addWidget(dlg)
    dlg.refresh()
    assert dlg.list.count() == 1
