# -*- coding: utf-8 -*-
"""
蜜算分块加载：行号与数据必须严格对齐（P1-16）

缺陷：
    模型取值用 `.iloc[r, c]`（按位置），但已加载 DataFrame 用
    `pd.concat(..., ignore_index=False)` 直接追加。
    跳着加载（先看第 3 块再回第 1 块）时，第 1 块被追加到末尾，
    位置与绝对行号错位 —— 界面上表现为"这一行显示了别的行的数据"。

修复：
    分块统一以绝对行号为索引，加载后排序，
    保证 `_loaded_df.iloc[r]` 始终就是第 r 行。

说明：
    未加载的行由模型显示占位符 "⏳"（流式加载的预期行为），
    所以断言只看"已加载位置"的 (行号, 值) 对。
"""
import pytest

pytest.importorskip("PySide6.QtWidgets")

pd = pytest.importorskip("pandas")

PLACEHOLDER = "⏳"
EMPTY = ""      # v5.2 起，超出数据范围的行显示空串（工作区空白行）


@pytest.fixture
def model(monkeypatch):
    from beeoffice.plugins.beesheet_model import SheetDataModel

    monkeypatch.setattr(SheetDataModel, "CHUNK_SIZE", 2)
    m = SheetDataModel()
    m.set_full_dataframe(pd.DataFrame({"v": [0, 1, 2, 3, 4, 5]}))
    return m


def _loaded(m):
    """返回 [(绝对行号, 值)]，跳过占位行。"""
    from PySide6.QtCore import Qt

    out = []
    for r in range(m.rowCount()):
        val = m.data(m.index(r, 0), Qt.DisplayRole)
        if val not in (PLACEHOLDER, EMPTY):
            out.append((r, val))
    return out


def test_total_rows_at_least_data_length(model):
    # 空表默认有最小网格（1000 行），所以只断言"不少于数据行数"
    assert model.rowCount() >= 6


def test_sequential_loading_keeps_order(model):
    model.load_chunk(1)
    model.load_chunk(2)
    assert _loaded(model) == [
        (0, "0"), (1, "1"), (2, "2"),
        (3, "3"), (4, "4"), (5, "5"),
    ]


def test_out_of_order_loading_keeps_order(model):
    """先加载第 3 块，再回头加载第 2 块——错行最容易出现的顺序。"""
    model.load_chunk(2)
    model.load_chunk(1)
    assert _loaded(model) == [
        (0, "0"), (1, "1"), (2, "2"),
        (3, "3"), (4, "4"), (5, "5"),
    ]


def test_jump_forward_fills_the_gap(model):
    """
    直接跳到第 3 块时必须把中间缺的块补齐——
    模型靠"连续前缀"判断占位，中间挖洞会让后面整体前移。
    """
    model.load_chunk(2)
    assert _loaded(model) == [
        (0, "0"), (1, "1"), (2, "2"),
        (3, "3"), (4, "4"), (5, "5"),
    ]


def test_loading_same_chunk_twice_is_noop(model):
    assert model.load_chunk(1) is True
    assert model.load_chunk(1) is False
    assert _loaded(model) == [(0, "0"), (1, "1"), (2, "2"), (3, "3")]


def test_non_default_index_is_normalised(monkeypatch):
    """源表索引不是 RangeIndex 时，位置映射同样要正确。"""
    from beeoffice.plugins.beesheet_model import SheetDataModel

    monkeypatch.setattr(SheetDataModel, "CHUNK_SIZE", 2)
    m = SheetDataModel()
    m.set_full_dataframe(
        pd.DataFrame({"v": [10, 11, 12, 13]}, index=[100, 200, 300, 400])
    )

    assert _loaded(m) == [(0, "10"), (1, "11")]
    m.load_chunk(1)
    assert _loaded(m) == [
        (0, "10"), (1, "11"), (2, "12"), (3, "13"),
    ]
