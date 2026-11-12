"""结构化补测：BeeSheet DataMixin 筛选/清洗/批量/粘贴。"""
import pandas as pd
from PySide6.QtCore import QObject, Signal

from beeoffice.plugins.beesheet_data_mixin import DataMixin


class FakeModel(QObject):
    layoutChanged = Signal()
    dataChanged = Signal(object, object)

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

    def get_value(self, row, col):
        return self._loaded_df.iloc[row, col]

    def rowCount(self):
        return len(self._loaded_df)

    def columnCount(self):
        return len(self._loaded_df.columns)


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

    def _col_index_to_name(self, col):
        return chr(65 + col)


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


def test_export_files(tmp_path, monkeypatch):
    import beeoffice.plugins.beesheet_data_mixin as m
    sheet = make_sheet()
    targets = {
        "csv": tmp_path / "out.csv",
        "html": tmp_path / "out.html",
        "md": tmp_path / "out.md",
        "json": tmp_path / "out.json",
    }
    monkeypatch.setattr(m.QFileDialog, "getSaveFileName", lambda *a, **k: (str(targets[sheet._export_target]), ""))
    monkeypatch.setattr(m.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(m.QMessageBox, "warning", lambda *a, **k: None)
    sheet._export_target = "csv"; sheet._export_csv()
    sheet._export_target = "html"; sheet._export_html_table()
    sheet._export_target = "md"; sheet._export_markdown_file()
    sheet._export_target = "json"; sheet._export_json()
    for p in targets.values():
        assert p.exists() and p.stat().st_size > 0


def test_row_and_column_edits(qtbot, monkeypatch):
    import beeoffice.plugins.beesheet_data_mixin as m
    monkeypatch.setattr(m.QMessageBox, "question", lambda *a, **k: m.QMessageBox.Yes)
    from PySide6.QtWidgets import QApplication
    sheet = make_sheet()
    sheet._copy_row(0)
    assert "Alice" in QApplication.clipboard().text()
    before = len(sheet.model._loaded_df)
    sheet._insert_row_at(1)
    assert len(sheet.model._loaded_df) == before + 1
    sheet._copy_column(0)
    assert "Alice" in QApplication.clipboard().text()
    sheet._insert_column_at(1)
    assert len(sheet.model._loaded_df.columns) == 4
    sheet._delete_column_at(1)
    assert len(sheet.model._loaded_df.columns) == 3


def test_delete_row_yes(monkeypatch):
    import beeoffice.plugins.beesheet_data_mixin as m
    sheet = make_sheet()
    monkeypatch.setattr(m.QMessageBox, "question", lambda *a, **k: m.QMessageBox.Yes)
    n = len(sheet.model._loaded_df)
    sheet._delete_row_at(0)
    assert len(sheet.model._loaded_df) == n - 1


def test_conditional_formats():
    sheet = make_sheet()
    sheet._add_data_bars(1)
    assert sheet._conditional_formats[1]["type"] == "data_bars"
    sheet._add_color_scale(1)
    assert sheet._conditional_formats[1]["type"] == "color_scale"
    sheet._clear_cond_format(1)
    assert 1 not in sheet._conditional_formats


def test_flash_fill_patterns():
    s = make_sheet()
    assert s._is_pattern_source("abc-123", "123") is True
    assert s._is_pattern_source("北京", "北京") is True
    assert s._is_pattern_source("", "x") is False
    assert s._learn_pattern("abc", "abc") == ("copy", None)
    assert s._learn_pattern("abc", "ABC") == ("upper", None)
    assert s._learn_pattern("ABC", "abc") == ("lower", None)
    assert s._learn_pattern("abcdef", "abc") == ("prefix", 3)
    assert s._learn_pattern("abcdef", "def") == ("suffix", 3)
    assert s._learn_pattern("a123b", "123") == ("extract_number", None)
    assert s._learn_pattern("abc北京xyz", "北京") == ("extract_chinese", None)
    assert s._learn_pattern("a-b-c", "b") == ("split", ("-", 1))
    assert s._learn_pattern("x", "pre-x") == ("add_prefix", "pre-")
    assert s._learn_pattern("x", "x-post") == ("add_suffix", "-post")
    assert s._apply_pattern(("copy", None), "x") == "x"
    assert s._apply_pattern(("upper", None), "x") == "X"
    assert s._apply_pattern(("lower", None), "X") == "x"
    assert s._apply_pattern(("prefix", 2), "abc") == "ab"
    assert s._apply_pattern(("suffix", 2), "abc") == "bc"
    assert s._apply_pattern(("extract_number", None), "a12b3") == "123"
    assert s._apply_pattern(("extract_chinese", None), "a北京b") == "北京"
    assert s._apply_pattern(("split", ("-", 1)), "a-b") == "b"
    assert s._apply_pattern(("add_prefix", "P"), "x") == "Px"
    assert s._apply_pattern(("add_suffix", "S"), "x") == "xS"
    assert s._apply_pattern(("unknown", None), "x") is None


def test_detect_source_column():
    s = FakeSheet({"a": ["x-1"], "b": ["1"], "c": [""]})
    assert s._detect_source_column(0, 1, "1") == 0
    assert s._detect_source_column(0, 0, "x-1") == 1
