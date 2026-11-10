"""BeeShow 打印绘制补测：把排版计划画成 PDF。"""
from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QImage
from PySide6.QtPrintSupport import QPrinter

from beeoffice.plugins.beeshow_print_mixin import (
    MODE_HANDOUT,
    MODE_NOTES,
    MODE_OUTLINE,
    MODE_SLIDES,
    ShowPrintMixin,
)


def paint(tmp_path, mode, count=2, per_page=2, empty=False):
    path = tmp_path / f"{mode}.pdf"
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(path))
    plan = ShowPrintMixin._build_print_plan(
        count, mode=mode, per_page=per_page,
        titles=[f"标题{i}" for i in range(count)],
        notes=[f"备注{i}" for i in range(count)],
    )
    if empty:
        plan = ShowPrintMixin._build_print_plan(0)
    images = {}
    for i in range(count):
        img = QImage(80, 60, QImage.Format.Format_RGB32)
        img.fill(QColor("#FF0000") if i % 2 == 0 else QColor("#00FF00"))
        images[i] = img
    ShowPrintMixin._paint_plan(printer, plan, images)
    assert path.exists() and path.stat().st_size > 0
    return path, plan


@pytest.mark.parametrize("mode,per_page", [
    (MODE_SLIDES, 1), (MODE_HANDOUT, 1), (MODE_HANDOUT, 2),
    (MODE_HANDOUT, 4), (MODE_HANDOUT, 6), (MODE_HANDOUT, 9),
    (MODE_NOTES, 1), (MODE_OUTLINE, 1),
])
def test_paint_plan_modes(qtbot, tmp_path, mode, per_page):
    paint(tmp_path, mode, per_page=per_page)


def test_paint_plan_empty(qtbot, tmp_path):
    paint(tmp_path, MODE_SLIDES, count=0, empty=True)


def test_paint_plan_missing_image(qtbot, tmp_path):
    path = tmp_path / "missing.pdf"
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(path))
    plan = ShowPrintMixin._build_print_plan(3)
    ShowPrintMixin._paint_plan(printer, plan, {})
    assert path.exists() and path.stat().st_size > 0
