# tests/fidelity/test_ui_feedback_2026_10_22.py
"""用户截图反馈修复：WPS 表头不重复、默认 26 列、打开文件全局进度条。"""
import pandas as pd
from PySide6.QtCore import Qt

from beeoffice.plugins.beesheet_model import SheetDataModel


def test_default_grid_is_wps_like(qapp):
    model = SheetDataModel()
    assert len(model.df.columns) == 26, "默认应有 A–Z 26 列（WPS 默认量级）"
    assert len(model.df) == 1000


def test_empty_column_header_letter_not_duplicated(qapp):
    model = SheetDataModel()
    assert model.headerData(0, Qt.Horizontal, Qt.DisplayRole) == "A"
    assert model.headerData(25, Qt.Horizontal, Qt.DisplayRole) == "Z"


def test_named_column_shows_letter_and_name(qapp):
    model = SheetDataModel()
    model.set_full_dataframe(pd.DataFrame({"订单编号": [1]}))
    header = model.headerData(0, Qt.Horizontal, Qt.DisplayRole)
    assert header == "A  订单编号"


def test_app_busy_progress_visible(app):
    app.show_busy_progress("正在加载文档…")
    assert not app._busy_progress.isHidden()
    app.hide_busy_progress()
    assert app._busy_progress.isHidden()
