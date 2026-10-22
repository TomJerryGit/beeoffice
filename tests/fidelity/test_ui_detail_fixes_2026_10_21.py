# tests/fidelity/test_ui_detail_fixes_2026_10_21.py
"""
2026-10-21 GUI 实跑发现的 UI/文案细节修复回归：

1. 快捷键浮层：Markdown 未渲染（显示 `## 全局`、反引号）→ 用 setMarkdown；
2. 大纲自动编号与用户手写编号叠加（`1.1 一、目标`）→ 已有编号不再叠加；
3. 保真提示 note-only 文案矛盾（items=[] 却写"有内容无法完整保留"）；
4. 大表载入中的提示：不再让用户"重新打开文件"，而是"仍在后台加载，请稍候"；
5. 三件套「另存为取消」必须置 `_save_canceled`（供状态栏显示"已取消保存"）。
"""

from PySide6.QtWidgets import QTextEdit

from beeoffice.plugins.beewrite_outline import OutlinePanel
from beeoffice.plugins.beesheet_model import SheetDataModel
from beeoffice.plugins.fidelity_report import FidelityReport

from beeoffice.plugins.beewrite_export_mixin import ExportMixin


# ==================== 1. 大纲编号 ====================

class TestOutlineManualNumbering:
    def test_chinese_number_is_detected(self):
        assert OutlinePanel._has_manual_numbering("一、目标达成情况")
        assert OutlinePanel._has_manual_numbering("（二）工作回顾")

    def test_numeric_number_is_detected(self):
        assert OutlinePanel._has_manual_numbering("1.1 核心指标")
        assert OutlinePanel._has_manual_numbering("2、下一步计划")
        assert OutlinePanel._has_manual_numbering("第一章 总则")

    def test_plain_heading_is_not_numbered(self):
        assert not OutlinePanel._has_manual_numbering("目标达成情况")
        assert not OutlinePanel._has_manual_numbering("核心指标")


# ==================== 2. 快捷键浮层 Markdown ====================

def test_shortcuts_overlay_renders_markdown(app):
    app._show_shortcuts_overlay()
    try:
        dlg = app._shortcuts_dlg
        assert dlg is not None
        editors = dlg.findChildren(QTextEdit)
        assert editors, "快捷键浮层里没有 QTextEdit"
        plain = editors[0].toPlainText()
        # 渲染后不应再把 `##` / 反引号当正文显示
        assert "## 全局" not in plain, f"Markdown 未渲染: {plain[:120]!r}"
        assert "`Ctrl+S`" not in plain, f"反引号未渲染: {plain[:120]!r}"
    finally:
        app._close_shortcuts_overlay()


# ==================== 3. 保真提示 note-only 文案 ====================

def test_fidelity_note_only_prompt_does_not_claim_losses(monkeypatch):
    captured = {}

    def _fake_warning(parent, title, text, *args, **kwargs):
        captured["title"] = title
        captured["text"] = text
        return QMessageBox.Yes

    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "warning", _fake_warning)

    class _Dummy:
        _fidelity_report = FidelityReport(
            path="说明.pptx", items=[], note="蜜演目前只支持导出 PPTX，不支持导入"
        )

    assert ExportMixin._confirm_fidelity_losses(_Dummy()) is True
    assert captured["title"] == "保真度提示"
    assert "无法完整保留" not in captured["text"], captured["text"]
    assert "提示" in captured["text"]


# ==================== 4. 大表载入提示 ====================

def test_partial_sheet_loading_message_says_wait_not_reopen():
    model = SheetDataModel()
    model._fully_loaded = False
    model._full_loader = None
    assert model.ensure_fully_loaded() is False
    assert "后台加载" in model.load_error
    assert "重新打开" in model.load_error  # 仅作为兜底提示出现
    assert "没有可用的完整数据加载器" not in model.load_error


# ==================== 5. 三件套保存取消标记 ====================

def _no_path(*_a, **_k):
    return ("", "")


def test_beewrite_save_cancel_sets_flag(beewrite_editor, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(_no_path))
    beewrite_editor._doc_kind = "markdown"
    beewrite_editor._current_file_path = None
    assert beewrite_editor.save() is False
    assert beewrite_editor._save_canceled is True


def test_beeshow_save_cancel_sets_flag(beeshow_view, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(_no_path))
    beeshow_view._current_file_path = None
    assert beeshow_view.save() is False
    assert beeshow_view._save_canceled is True


def test_beesheet_save_as_cancel_sets_flag(monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    from beeoffice.plugins.beesheet import BeeSheetView

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(_no_path))
    view = BeeSheetView()
    view._current_file_path = None
    assert view.save_as() is False
    assert view._save_canceled is True
