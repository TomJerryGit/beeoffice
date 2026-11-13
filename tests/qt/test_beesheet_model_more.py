"""BeeSheet 数据模型补测：格式化/分块加载/条件格式。"""
import pandas as pd
from PySide6.QtCore import Qt

from beeoffice.plugins.beesheet_model import SheetDataModel


def make_model(df=None):
    m = SheetDataModel()
    if df is not None:
        m.set_full_dataframe(df)
    return m


def test_default_and_dataframe(qtbot):
    m = make_model()
    assert m.rowCount() == m.DEFAULT_ROWS
    assert m.columnCount() == m.DEFAULT_COLS
    m.set_full_dataframe(pd.DataFrame({"A": [1, 2], "B": ["x", "y"]}))
    assert m.columnCount() == 2
    assert m.rowCount() == m.DEFAULT_ROWS
    assert m.get_value(0, 0) == 1
    assert m.data(m.index(0, 0), Qt.DisplayRole) == "1"
    assert m.data(m.index(0, 1), Qt.DisplayRole) == "x"
    assert m.data(m.index(5, 0), Qt.DisplayRole) == ""


def test_streaming_chunks(qtbot):
    df = pd.DataFrame({"A": range(SheetDataModel.CHUNK_SIZE + 100)})
    m = make_model(df)
    assert m.is_streaming is True
    assert m.loading_progress < 1.0
    assert m.needs_chunks_for_range(SheetDataModel.CHUNK_SIZE, SheetDataModel.CHUNK_SIZE + 10)
    assert m.load_chunk(1) is True
    assert m.is_streaming is False
    assert m.loading_progress == 1.0
    # 已加载的块再次加载返回 False
    assert m.load_chunk(1) is False


def test_set_data_and_coerce(qtbot):
    m = make_model(pd.DataFrame({"A": [1], "B": ["x"]}))
    idx = m.index(0, 0)
    assert m.setData(idx, "42", Qt.EditRole) is True
    assert m.get_value(0, 0) == 42
    assert m.setData(idx, "3.5", Qt.EditRole) is True
    assert m.get_value(0, 0) == 3.5
    assert m.setData(idx, "abc", Qt.EditRole) is True
    assert m.get_value(0, 0) == "abc"
    from PySide6.QtCore import QModelIndex
    assert m.setData(QModelIndex(), "bad", Qt.EditRole) is False


def test_header_and_flags(qtbot):
    m = make_model(pd.DataFrame({"A": [1]}))
    assert m.headerData(0, Qt.Horizontal, Qt.DisplayRole) == "A"
    assert m.headerData(0, Qt.Vertical, Qt.DisplayRole) == "1"
    assert m.flags(m.index(0, 0)) & Qt.ItemIsEditable


def test_cell_formats_display(qtbot):
    m = make_model(pd.DataFrame({"A": [1234.5], "B": ["x"]}))
    m._cell_formats_ref[(0, 0)] = {
        "number_format": "数值", "decimals": 2, "bold": True,
        "italic": True, "underline": True, "align": "center",
    }
    assert m.data(m.index(0, 0), Qt.DisplayRole) == "1,234.50"
    font = m.data(m.index(0, 0), Qt.FontRole)
    assert font is not None and font.bold()
    assert m.data(m.index(0, 0), Qt.TextAlignmentRole) == Qt.AlignCenter

    m._cell_formats_ref[(0, 0)]["number_format"] = "货币"
    assert m.data(m.index(0, 0), Qt.DisplayRole).startswith("¥")
    m._cell_formats_ref[(0, 0)]["number_format"] = "百分比"
    assert m.data(m.index(0, 0), Qt.DisplayRole).endswith("%")


def test_icon_set_and_background(qtbot):
    m = make_model(pd.DataFrame({"A": [1, 5, 9, "#N/A"]}))
    m._conditional_formats_ref[0] = {
        "type": "icon_set", "min": 1, "max": 9
    }
    assert m.data(m.index(0, 0), Qt.DisplayRole).startswith("🔴")
    assert m.data(m.index(2, 0), Qt.DisplayRole).startswith("🟢")
    bg = m.data(m.index(3, 0), Qt.BackgroundRole)
    assert bg is not None


def test_tooltips(qtbot):
    m = make_model(pd.DataFrame({"A": ["x"]}))
    m._comments_ref[(0, 0)] = "备注"
    assert "备注" in m.data(m.index(0, 0), Qt.ToolTipRole)
    m._comments_ref.clear()
    m._formulas_ref[(0, 0)] = "=SUM(A1:A2)"
    assert "SUM" in m.data(m.index(0, 0), Qt.ToolTipRole)


def test_grow_and_df_setter(qtbot):
    m = make_model(pd.DataFrame({"A": [1]}))
    m._grow_to(4)
    assert m._total_rows == 4
    m.df = pd.DataFrame({"A": [1, 2]})
    assert m.rowCount() == m.DEFAULT_ROWS
    assert m.get_value(1, 0) == 2
