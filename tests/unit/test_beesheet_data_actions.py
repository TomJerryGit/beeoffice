"""结构化补测：BeeSheet DataMixin 筛选/清洗/批量/粘贴。"""
import pandas as pd
from PySide6.QtCore import QObject, Signal

from beeoffice.plugins.beesheet_data_mixin import DataMixin


class FakeModel(QObject):
    layoutChanged = Signal()
    dataChanged = Signal()

    def __init__(self, rows):
        super().__init__()
        self._loaded_df = pd.DataFrame(rows)
        self._total_rows = len(self._loaded_df)
        self._total_cols = len(self._loaded_df.columns)

    @property
    def df(self):
        return self._loaded_df

    def index(self, row, col):
        return (row, col)


class FakeSheet(DataMixin):
    def __init__(self, rows):
        self.model = FakeModel(rows)
        self._dirty = False
        self._conditional_formats = {}
        self.commands = []
        self.statuses = []

    def _push_command(self, command):
        self.commands.append(command)

    def _set_status(self, text, ms=0):
        self.statuses.append(text)


def make_sheet():
    return FakeSheet(
        {"name": [" Alice ", "Bob", "Bob"], "num": ["1", "2", "3"],
         "raw": ["a-1", "b-2", "c-3"]}
    )


def test_clean_trim_and_number():
    s = make_sheet()
    s._clean_trim(0)
    assert s.model._loaded_df["name"].tolist() == ["Alice", "Bob", "Bob"]
    s._clean_to_number(1)
    assert s.model._loaded_df["num"].tolist() == [1, 2, 3]
    assert len(s.commands) == 2


def test_clean_remove_dups():
    s = make_sheet()
    before = len(s.model._loaded_df)
    s._clean_remove_dups()
    assert len(s.commands) == 1
    assert before == 3


def test_filter_contains():
    s = make_sheet()
    s.filter_contains(0, "bob")
    assert len(s.model.df) == 2
    s.filter_contains(0, "zzz")
    assert len(s.model.df) == 2


def test_split_column(monkeypatch):
    import beeoffice.plugins.beesheet_data_mixin as m
    monkeypatch.setattr(m.QInputDialog, "getText", lambda *a, **k: ("-", True))
    s = make_sheet()
    s._split_column(2)
    assert "raw_1" in s.model._loaded_df.columns
    assert "raw_2" in s.model._loaded_df.columns


def test_batch_convert_transform_dedup_move():
    s = make_sheet()
    s._batch_convert_column(1, "number")
    assert str(s.model._loaded_df["num"].dtype).startswith("int")
    s._batch_convert_column(0, "text")
    s._batch_transform_column(0, "upper")
    assert s.model._loaded_df["name"].tolist() == [" ALICE ", "BOB", "BOB"]
    s._batch_transform_column(0, "lower")
    assert s.model._loaded_df["name"].tolist() == [" alice ", "bob", "bob"]
    s._batch_transform_column(0, "trim")
    assert s.model._loaded_df["name"].tolist() == ["alice", "bob", "bob"]
    s._batch_deduplicate_column(0)
    assert len(s.model._loaded_df) == 2
    s._move_column(0, 1)
    assert s.model._loaded_df.columns[0] != "name"


def test_paste_data_and_single_value():
    s = make_sheet()
    s._paste_data([["x", "1"], ["y", "2"]], 0, 0, "文本")
    assert s.model._loaded_df.iloc[0, 0] == "x"
    assert s.model._loaded_df.iloc[1, 1] == 2
    assert s._dirty is True
    s._paste_single_value("10\n20", 0, 1)
    assert s.model._loaded_df.iloc[0, 1] == 10
    assert s.model._loaded_df.iloc[1, 1] == 20
