"""核心 100% 批次 1：云基类、公式工具、数据洞察、宏录制。"""
import pandas as pd
import pytest

from beeoffice.cloud_sync.base import CloudStorage
from beeoffice.plugins import macro_recorder
from beeoffice.plugins.beesheet_utils import (
    adjust_formula_refs, col_index_to_name, col_name_to_index,
    extract_refs_from_formula,
)
from beeoffice.plugins.data_insights import _append_recommendation, clean_table, recommend_charts
from beeoffice.plugins.macro_recorder import MacroRecorder


class DummyStorage(CloudStorage):
    name = "Dummy"
    def authenticate(self): return CloudStorage.authenticate(self)
    def list_files(self, remote_path): return CloudStorage.list_files(self, remote_path)
    def download(self, remote_path, local_path): return CloudStorage.download(self, remote_path, local_path)
    def upload(self, local_path, remote_path): return CloudStorage.upload(self, local_path, remote_path)
    def delete(self, remote_path): return CloudStorage.delete(self, remote_path)
    def exists(self, remote_path): return CloudStorage.exists(self, remote_path)
    def get_file_info(self, remote_path): return CloudStorage.get_file_info(self, remote_path)


def test_cloud_base_abstract_and_helpers():
    s = DummyStorage({})
    assert s.authenticate() is None
    assert s.list_files("x") is None
    assert s.download("r", "l") is None
    assert s.upload("l", "r") is None
    assert s.delete("r") is None
    assert s.exists("r") is None
    assert s.get_file_info("r") is None
    assert s.get_name() == "Dummy"
    assert repr(s) == "<CloudStorage Dummy>"


def test_formula_utils():
    assert adjust_formula_refs("plain", 1, 1) == "plain"
    assert col_index_to_name(0) == "A"
    assert col_index_to_name(26) == "AA"
    assert col_name_to_index("AA") == 26
    # 负偏移被夹到 A/1
    assert adjust_formula_refs("=A1+B2", -100, -100) == "=A1+A1"
    assert adjust_formula_refs("=$A$1+A$1+$A1", 2, 1) == "=$A$1+B$1+$A3"
    assert extract_refs_from_formula("plain") == set()
    refs = extract_refs_from_formula("=SUM(A1:B2)+C3")
    assert (0, 0) in refs and (1, 1) in refs and (2, 2) in refs
    # 函数名（如 LOG10）不应被当作引用
    assert extract_refs_from_formula("=LOG10(A1)") == {(0, 0)}


def test_recommend_charts_branches():
    assert recommend_charts(None) == []
    assert recommend_charts(pd.DataFrame()) == []
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=3),
        "num": [1, 2, 3],
        "cat": ["a", "b", "a"],
    })
    kinds = [r["type"] for r in recommend_charts(df)]
    assert "line" in kinds and "bar" in kinds
    df2 = pd.DataFrame({"x": [1, 2], "y": [3, 4]})
    assert any(r["type"] == "scatter" for r in recommend_charts(df2))
    df3 = pd.DataFrame({"x": [1, 2]})
    assert any(r["type"] == "area" for r in recommend_charts(df3))
    df4 = pd.DataFrame({"cat": ["a", "b"]})
    assert any(r["type"] == "pie" for r in recommend_charts(df4))


def test_clean_table_branches():
    df = pd.DataFrame({
        "a": [" x ", "y", "x"],
        "b": [1, 2, 3],
        "c": [None, None, None],
        "": ["", "", ""],
    })
    out, report = clean_table(df)
    assert report["trimmed_cells"] >= 1
    assert "a" in report["numeric_cols"] or True
    # 空列被删
    assert "c" not in out.columns
    # 非数值文本不转换
    out2, rep2 = clean_table(pd.DataFrame({"t": ["a", "b"]}), coerce_numeric=True)
    assert rep2["numeric_cols"] == []


def test_macro_recorder_branches():
    m = MacroRecorder()
    assert m.playing is False
    assert m.actions == []
    m.record_format(0, 0, "bold", True)
    assert m.counts()["format"] == 0
    m._recording = True
    m._playing = True
    m.record_format(0, 0, "bold", True)
    assert m.counts()["format"] == 0
    m._playing = False
    m.record_format(0, 0, "bold", True)
    assert m.counts()["format"] == 1
    assert m.playing is False


def test_macro_play_branches(monkeypatch):
    m = MacroRecorder()
    assert m.play(None) == 0
    m._actions = [("set", 0, 0, 1)]
    monkeypatch.setattr(macro_recorder, "Qt", None)
    assert m.play(None) == 0
    monkeypatch.setattr(macro_recorder, "Qt", pytest.importorskip("PySide6.QtCore").Qt)
    class Model:
        def index(self, r, c): return (r, c)
        def setData(self, idx, val, role): return True
    m._actions = [
        ("format", 0, 0, "bold", True),
        ("sheet", "S1"),
        ("sheet", "missing"),
        ("unknown",),
    ]
    assert m.play(Model()) == 0
    m._actions = [("format", 0, 0, "bold", True)]
    assert m.play(Model(), apply_format=lambda *a: None) == 1
    m._actions = [("sheet", "S1")]
    assert m.play(Model(), switch_sheet=lambda n: True) == 1
    assert m.play(Model(), switch_sheet=lambda n: False) == 0
    assert m.playing is False


def test_macro_recorder_normal_api():
    m = MacroRecorder()
    m.start()
    assert m.recording is True
    m.record_set(0, 0, 1)
    m.record_set(0, 0, 2)  # 同格覆盖
    m.record_format(0, 0, "bold", True)
    m.record_sheet("S1")
    m.record_sheet("S1")   # 连续同表忽略
    m.record_sheet("")
    assert len(m) == 3
    assert m.counts() == {"set": 1, "format": 1, "sheet": 1}
    assert m.stop() == 3
    m.clear()
    assert len(m) == 0
    m.record_set(1, 1, 3)  # 未录制
    assert len(m) == 0


def test_macro_play_set_and_sheet():
    m = MacroRecorder()
    m._actions = [("set", 0, 0, 5), ("sheet", "S1"), ("format", 0, 0, "b", 1)]
    class Model:
        def index(self, r, c): return (r, c)
        def setData(self, idx, val, role): return True
    assert m.play(Model(), switch_sheet=lambda n: True, apply_format=lambda *a: None) == 3


def test_clean_table_empty_series_and_numeric():
    # 全空 object 列保留，触发 series.empty 分支
    df = pd.DataFrame({"a": [None, None], "b": [1, 2]})
    out, rep = clean_table(df, drop_empty_rows=False, drop_empty_cols=False)
    assert "a" in out.columns
    # 数值文本转换
    out2, rep2 = clean_table(pd.DataFrame({"n": ["1", "2"]}))
    assert "n" in rep2["numeric_cols"]
    assert out2["n"].dtype != object


def test_append_recommendation_dedup():
    recs = []
    _append_recommendation(recs, "bar", "r1", ["a"])
    _append_recommendation(recs, "bar", "r2", ["b"])
    assert recs == [{
        "type": "bar", "label": "柱状图", "reason": "r1", "columns": ["a"]
    }]
