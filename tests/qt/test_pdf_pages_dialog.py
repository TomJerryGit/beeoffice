# -*- coding: utf-8 -*-
"""
PDF 页面工具对话框（阶段四 P0-1）

只测"界面装配与输入校验"——实际文件操作用例在 tests/unit/test_pdf_pages.py
里已经覆盖，对话框这里不重复跑一遍 PDF 处理。
"""
import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QMessageBox  # noqa: E402

from beeoffice.plugins.pdf_pages_dialog import PdfPagesDialog  # noqa: E402


@pytest.fixture
def dlg(qtbot):
    d = PdfPagesDialog()
    qtbot.addWidget(d)
    return d


def test_default_mode_is_merge_and_shows_list(dlg):
    assert dlg.current_mode() == "merge"
    assert dlg.file_list.isVisibleTo(dlg)
    assert not dlg.src_edit.isVisibleTo(dlg)


def test_switch_to_extract_shows_source_and_range(dlg):
    dlg.mode_combo.setCurrentIndex(1)  # 提取页面
    assert dlg.current_mode() == "extract"
    assert dlg.src_edit.isVisibleTo(dlg)
    assert dlg.range_edit.isVisibleTo(dlg)
    assert not dlg.file_list.isVisibleTo(dlg)


def test_rotate_shows_angle(dlg):
    dlg.mode_combo.setCurrentIndex(3)  # 旋转页面
    assert dlg.angle_combo.isVisibleTo(dlg)


def test_split_every_shows_chunk_size(dlg):
    dlg.mode_combo.setCurrentIndex(4)  # 拆分文件
    dlg.split_combo.setCurrentIndex(1)  # 每 N 页
    assert dlg.every_spin.isVisibleTo(dlg)


def test_run_without_output_warns(dlg, monkeypatch):
    calls = []
    monkeypatch.setattr(
        QMessageBox, "warning",
        lambda *a, **k: calls.append(a[-1] if a else k),
    )
    dlg._run()
    assert calls, "没有输出路径时应弹出提示"


def test_require_source_raises_when_empty(dlg):
    from beeoffice.plugins import pdf_pages

    with pytest.raises(pdf_pages.PdfPageError, match="源文件"):
        dlg._require_source()


def test_merge_with_one_file_warns(dlg, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *a, **k: calls.append(a[-1] if a else k)
    )
    dlg.out_edit.setText(str(tmp_path / "out.pdf"))
    dlg.file_list.addItem(str(tmp_path / "a.pdf"))
    dlg._run()
    assert calls, "只选了一个文件时应提示至少两个"
    assert "两个" in str(calls[0])


def test_move_file_reorders(dlg):
    dlg.file_list.addItem("a.pdf")
    dlg.file_list.addItem("b.pdf")
    dlg.file_list.setCurrentRow(0)
    dlg._move_file(1)
    assert dlg.file_list.item(0).text() == "b.pdf"
    assert dlg.file_list.item(1).text() == "a.pdf"
