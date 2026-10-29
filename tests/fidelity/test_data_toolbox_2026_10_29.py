"""S2 数据工具箱纯逻辑 + GUI 冒烟。"""
import pandas as pd
from PySide6.QtWidgets import QTextEdit

from beeoffice.plugins.data_toolbox_dialog import (
    DataToolboxDialog, dedupe_df, summary_text, trim_df,
)


def test_dedupe_and_trim():
    df = pd.DataFrame({"A": [" x ", "y", " x "], "B": [1, 1, 1]})
    assert len(dedupe_df(df)) == 2
    assert trim_df(df).iloc[0, 0] == "x"


def test_summary_text():
    text = summary_text(pd.DataFrame({"A": [1, None]}))
    assert "行数: 2" in text and "空值 1" in text


def test_dialog_buttons(qtbot):
    class Model:
        df = pd.DataFrame({"A": [1, 1]})

        def set_full_dataframe(self, df):
            self.df = df
    class TableView:
        def setModel(self, model):
            self.model = model

    class View:
        model = Model()
        table_view = TableView()
        status = ""

        def _set_status(self, text, *_):
            self.status = text
    view = View()
    dlg = DataToolboxDialog(view)
    qtbot.addWidget(dlg)
    dlg._dedupe()
    assert len(view.model.df) == 1
