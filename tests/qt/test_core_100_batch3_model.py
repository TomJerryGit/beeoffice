"""核心 100% 批次 3：beesheet_model 缺失分支。"""
import pandas as pd
import pytest
from PySide6.QtCore import Qt

from beeoffice.plugins import beesheet_model as bm
from beeoffice.plugins.beesheet_model import SheetDataModel


def make_model(df):
    m = SheetDataModel()
    m.set_full_dataframe(df)
    return m


def test_grow_and_progress_and_df_setter(qtbot):
    m = make_model(pd.DataFrame({"A": [1]}))
    m._grow_to(1)  # 早退
    m._grow_to(4)  # 数值列
    assert m._total_rows == 4
    m._total_rows = 0
    assert m.loading_progress == 1.0
    big = pd.DataFrame({"A": range(SheetDataModel.CHUNK_SIZE + 10)})
    m.df = big
    assert m.is_streaming is True
    # 超出范围的块直接 break
    assert m.load_chunk(99) is True


def test_loading_placeholder_and_blank(qtbot):
    big = pd.DataFrame({"A": range(SheetDataModel.CHUNK_SIZE + 10)})
    m = make_model(big)
    idx = m.index(SheetDataModel.CHUNK_SIZE + 1, 0)
    assert m.data(idx, Qt.DisplayRole) == "⏳"
    assert m.data(idx, Qt.FontRole) is None
    small = make_model(pd.DataFrame({"A": [1]}))
    assert small.data(small.index(small.DEFAULT_ROWS - 1, 0), Qt.DisplayRole) == ""
    assert m.data(m.index(-1, 0), Qt.DisplayRole) is None


def test_format_display(qtbot):
    m = make_model(pd.DataFrame({"A": [1.2]}))
    assert m._format_display_value("abc", {"number_format": "数值"}) == "abc"
    assert m._format_display_value(1234.5, {"number_format": "千分位", "decimals": 1}) == "1,234.5"
    assert m._format_display_value(float("nan"), {}) == ""


def test_icon_set_display(qtbot):
    m = make_model(pd.DataFrame({"A": [1, 5, 9, "bad"]}))
    m._conditional_formats_ref[0] = {"type": "icon_set", "min": 1, "max": 9}
    assert m.data(m.index(0, 0), Qt.DisplayRole).startswith("🔴")
    assert m.data(m.index(1, 0), Qt.DisplayRole).startswith("🟡")
    assert m.data(m.index(2, 0), Qt.DisplayRole).startswith("🟢")
    m._cell_formats_ref[(0, 0)] = {"number_format": "数值", "decimals": 1}
    assert "🔴" in m.data(m.index(0, 0), Qt.DisplayRole)
    # bad 非数字走 except
    assert m.data(m.index(3, 0), Qt.DisplayRole) is not None


def test_tooltip_and_background_states(qtbot):
    m = make_model(pd.DataFrame({"A": ["#ERROR: x", "y", "z" * 60]}))
    assert m.data(m.index(0, 0), Qt.ToolTipRole).startswith("#ERROR")
    assert m.data(m.index(2, 0), Qt.ToolTipRole) is not None
    assert m.data(m.index(0, 0), Qt.BackgroundRole) is not None
    m._highlight_refs.add((1, 0))
    assert m.data(m.index(1, 0), Qt.BackgroundRole) is not None
    m._audit_cells_ref.add((2, 0))
    assert m.data(m.index(2, 0), Qt.BackgroundRole) is not None
    clean = make_model(pd.DataFrame({"A": ["a", "b"]}))
    clean._table_style_ref = {"header_bg": "red", "stripe": True, "stripe_bg": "gray"}
    assert clean.data(clean.index(0, 0), Qt.BackgroundRole) == "red"
    assert clean.data(clean.index(1, 0), Qt.BackgroundRole) == "gray"


def test_conditional_bg_data_bars_and_color_scale(qtbot):
    m = make_model(pd.DataFrame({"A": [1.0, 5.0, 9.0]}))
    m._conditional_formats_ref[0] = {"type": "data_bars", "min": 1, "max": 9}
    assert m.data(m.index(0, 0), Qt.BackgroundRole) is not None
    m._conditional_formats_ref[0] = {"type": "color_scale", "min": 1, "max": 9}
    assert m.data(m.index(0, 0), Qt.BackgroundRole) is not None
    assert m.data(m.index(2, 0), Qt.BackgroundRole) is not None
    # 异常值走 except
    m._conditional_formats_ref[0] = {"type": "data_bars", "min": 0, "max": 1}
    m._loaded_df.iloc[0, 0] = "bad"
    assert m.data(m.index(0, 0), Qt.BackgroundRole) is None


def test_set_data_unloaded_and_grow_and_recorder(qtbot, monkeypatch):
    big = pd.DataFrame({"A": range(SheetDataModel.CHUNK_SIZE + 10)})
    m = make_model(big)
    idx = m.index(SheetDataModel.CHUNK_SIZE + 1, 0)
    assert m.setData(idx, 1, Qt.EditRole) is False  # 未加载块
    m2 = make_model(pd.DataFrame({"A": [1]}))
    assert m2.setData(m2.index(5, 0), 7, Qt.EditRole) is True  # 扩展空白行
    assert m2.setData(m2.index(0, 0), "", Qt.EditRole) is True  # 空值 -> NaN
    import beeoffice.plugins.macro_recorder as mr
    monkeypatch.setattr(mr.RECORDER, "record_set", lambda *a: (_ for _ in ()).throw(RuntimeError("x")))
    assert m2.setData(m2.index(0, 0), 1, Qt.EditRole) is True


def test_get_value_and_header(qtbot):
    m = make_model(pd.DataFrame({"A": [1, 2]}))
    assert m.get_value(1, 0) == 2
    assert m.get_value(99, 0) == ""
    assert m.headerData(0, Qt.Vertical, Qt.DisplayRole) == "1"


def test_model_final_branches(qtbot):
    # 扩展文本列
    m = make_model(pd.DataFrame({"A": ["x"]}))
    m._grow_to(3)
    assert len(m._loaded_df) >= 1
    # 空值显示
    m2 = make_model(pd.DataFrame({"A": [None, ""]}))
    assert m2.data(m2.index(0, 0), Qt.DisplayRole) == ""
    assert m2.data(m2.index(1, 0), Qt.DisplayRole) == ""
    # 条件格式但行未加载
    m3 = make_model(pd.DataFrame({"A": [1]}))
    m3._conditional_formats_ref[0] = {"type": "data_bars", "min": 0, "max": 1}
    assert m3._get_cond_bg(999, 0) is None
    # iloc 抛异常
    class BadDF:
        def __len__(self): return 1
        @property
        def iloc(self):
            class I:
                def __getitem__(self, key): raise ValueError("bad")
            return I()
    m3._loaded_df = BadDF()
    assert m3._get_cond_bg(0, 0) is None
    # 未加载块从 full_df 读取
    big = pd.DataFrame({"A": range(SheetDataModel.CHUNK_SIZE + 10)})
    m4 = make_model(big)
    assert m4.get_value(SheetDataModel.CHUNK_SIZE + 1, 0) == SheetDataModel.CHUNK_SIZE + 1
