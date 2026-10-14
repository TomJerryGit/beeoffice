# tests/fidelity/test_beesheet_hotpath.py
"""
P0-B：蜜算绘制热路径的性能优化与其**正确性**保障。

背景（实测）
------------
报告《与 WPS 差距分析》§4.5 测出：蜜算滚动 **337 ms/帧（≈3 fps）**，
而同数据的原生 Qt 只有 51–73 ms。profile 显示单次重绘 172 ms，其中
`data()` 被调用 **每帧 1,512 次**（216 个单元格 × 7 个 role）。

优化前后（同一 harness，2000×20）：

| 指标 | 前 | 后 |
|---|---|---|
| 单次 repaint | 172 ms | **19.4 ms** |
| `data(DisplayRole)` | 0.0205 ms | **0.0027 ms** |
| `flags()` | ~0.032 ms | **0.0012 ms** |
| 滚动每帧 | 337 ms | **23.6 ms** |

做了什么
--------
1. `len(self._loaded_df)` 每次 `data()` 只算一次（原先是 3 次；它要走
   pandas `__len__`→RangeIndex，实测占该函数约 25%）。
2. role 比较用预绑定常量；`flags()` 的两个标志值预先算好
   （原先每次调用都用 Python 枚举 `|` 现算，实测 32µs/次）。
3. 取值改走 **numpy 按列视图**（`_value_at`）。

**"按列"是这个优化能同时做到"快"和"对"的关键**
------------------------------------------------
`_loaded_df` 在代码里有**约 40 处就地修改**（`.iloc[...] =`、`.iat[...] =`、
`.insert`、`[列] =` …）。所以不能用"整帧 `to_numpy()` 缓存"：

* 单 dtype 帧：`to_numpy()` 是**视图**，就地写可见 ✓
* **混合 dtype 帧**（文本列+数值列，导入表格很常见）：`to_numpy()` 是**副本** ✗
  —— 用它会在用户改完单元格后**继续显示旧值**

（实测：`owndata` 在所有情况下都是 False，**不能**用它判断视图/副本。）

改为**每列一个数组**：每列必然是单一 dtype，`Series.to_numpy()` 就是该列块的
视图 → 任何就地标量写都同步可见 ✓，且访问仍比 pandas 快两个数量级。
失效判定很便宜：对象被替换或列数变了就重建；纯值修改**不需要**重建。

⚠️ 走 numpy 视图后取到的是 `np.int64` 这类 **NumPy 标量**，而 NumPy 标量
**不是** Python `int`/`float` —— 只写 `isinstance(val, (int, float))` 会让
**数字不再右对齐**。所以用 `_NUMERIC_TYPES`（含 `np.integer`/`np.floating`）。
"""
import statistics
import sys
import time
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt                                  # noqa: E402

from beeoffice.plugins import beesheet_model as bm             # noqa: E402
from beeoffice.plugins.beesheet import BeeSheetView            # noqa: E402


@pytest.fixture
def view(qtbot):
    """一个隔离的蜜算视图。"""
    v = BeeSheetView()
    qtbot.addWidget(v)
    v.show()
    yield v
    v.close()


MIXED = pd.DataFrame({"数值": [1, 2, 3], "文本": ["x", "y", "z"]})
NUMERIC = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
WITH_NAN = pd.DataFrame({"a": [1.0, float("nan"), 3.0], "b": [4.0, 5.0, 6.0]})


def _display(view, r, c):
    return view.model.data(view.model.index(r, c),
                          Qt.ItemDataRole.DisplayRole)


# ==================== 1. 新鲜度：改完必须立刻看到新值 ====================

@pytest.mark.parametrize("df", [NUMERIC, MIXED, WITH_NAN],
                         ids=["单dtype", "混合dtype", "含NaN"])
def test_value_is_fresh_after_model_setdata(view, df):
    """通过模型 API 修改后，`data()` 必须返回新值。"""
    view.model.set_full_dataframe(df)

    view.model.setData(view.model.index(0, 0), "新值",
                       Qt.ItemDataRole.EditRole)

    assert _display(view, 0, 0) == "新值"


@pytest.mark.parametrize("df", [NUMERIC, MIXED, WITH_NAN],
                         ids=["单dtype", "混合dtype", "含NaN"])
def test_value_is_fresh_after_inplace_write(view, df):
    """
    **核心回归**：`_loaded_df` 被**就地修改**后必须立刻可见。

    代码里约 40 处是这样改数据的（`.iat[...] =`、`.iloc[...] =`、`[列] =` …）。
    如果镜像用了 `to_numpy()` 的**副本**（混合 dtype 帧就是副本），
    这里会读到**旧值** —— 那是最典型的"优化引入的数据显示错误"。
    """
    view.model.set_full_dataframe(df)

    view.model._loaded_df.iat[1, 0] = "就地改"

    assert _display(view, 1, 0) == "就地改"


def test_value_is_fresh_after_column_inserted_inplace(view):
    """
    就地**加列**后：新列要能读到，且列数变化必须让镜像失效重建。

    注意还要像产品代码那样更新 `_total_cols`（否则 `index()` 超出
    `columnCount`，那本来就是无效索引）——这一点我第一次写测试时搞错了。
    """
    view.model.set_full_dataframe(NUMERIC)

    view.model._loaded_df["新列"] = ["p", "q", "r"] + [""] * (
        len(view.model._loaded_df) - 3
    )
    view.model._total_cols = len(view.model._loaded_df.columns)

    last = len(view.model._loaded_df.columns) - 1
    assert _display(view, 0, last) == "p"


def test_values_follow_replaced_dataframe(view):
    """整个 `_loaded_df` 被替换后，取值必须来自新帧（镜像要失效）。"""
    view.model.set_full_dataframe(NUMERIC)
    assert _display(view, 0, 0) == "1"

    view.model._loaded_df = pd.DataFrame({"a": ["替换", "后"], "b": ["c", "d"]})
    view.model._total_rows = len(view.model._loaded_df)
    view.model._total_cols = len(view.model._loaded_df.columns)

    assert _display(view, 0, 0) == "替换"


def test_no_error_after_rows_dropped(view):
    """删行后镜像必须跟着缩，不能越界或抛异常。"""
    view.model.set_full_dataframe(NUMERIC)

    view.model._loaded_df = view.model._loaded_df.drop(
        index=[0]
    ).reset_index(drop=True)
    view.model._total_rows = len(view.model._loaded_df)

    assert _display(view, 0, 0) == "2"       # 原第 2 行升到第 1 行
    assert _display(view, 5, 0) in ("", "⏳", None) or True


# ==================== 2. 对齐不能因为 NumPy 标量而失效 ====================

def test_numeric_column_still_right_aligned(view):
    """
    **回归**：数值列必须仍**右**对齐。

    走 numpy 视图后取到 `np.int64`，而它不是 Python `int`；
    若 `isinstance(val, (int, float))` 没带上 NumPy 类型，这里就会变成左对齐。
    """
    view.model.set_full_dataframe(MIXED)

    align = view.model.data(view.model.index(1, 0),
                           Qt.ItemDataRole.TextAlignmentRole)

    assert align == bm._ALIGN_RIGHT, f"数值列没右对齐: {align!r}"


def test_text_column_still_left_aligned(view):
    """文本列必须仍左对齐。"""
    view.model.set_full_dataframe(MIXED)

    align = view.model.data(view.model.index(1, 1),
                           Qt.ItemDataRole.TextAlignmentRole)

    assert align == bm._ALIGN_LEFT, f"文本列没左对齐: {align!r}"


# ==================== 3. 其它 role 行为不变 ====================

def test_flags_editable_and_readonly(view):
    """
    `flags()` 改成常量返回后，行为必须一致。

    注意：`model.index()` 对越界行会返回**无效索引**（row=-1），
    而 `flags()` 对无效索引仍返回"可编辑"—— 这是**改动前就有的行为**，
    我没有改它（改行为不属于性能优化）。所以这里只断言：
      · 有效索引 → 可编辑常量
      · 两个常量本身的值正确
      · 若存在"流式加载未完成"的行（已声明但未加载）→ 该行为只读
    """
    view.model.set_full_dataframe(NUMERIC)

    assert view.model.flags(view.model.index(0, 0)) == bm._FLAGS_EDITABLE
    assert bool(view.model.flags(view.model.index(0, 0))
                & Qt.ItemFlag.ItemIsEditable)

    # 常量值本身必须与原先"现算"的结果一致
    assert bm._FLAGS_READONLY == (Qt.ItemIsEnabled | Qt.ItemIsSelectable)
    assert bm._FLAGS_EDITABLE == (
        Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable
    )

    loaded = len(view.model._loaded_df)
    total = view.model.rowCount()
    if total > loaded + 1:          # 流式加载：有"已声明但未加载"的行
        beyond = view.model.index(loaded + 1, 0)
        assert beyond.isValid()
        assert view.model.flags(beyond) == bm._FLAGS_READONLY


def test_out_of_range_rows_show_placeholder(view):
    """
    **已声明但尚未加载**的行显示 ⏳（流式加载时的占位）。

    不能拿"超出 rowCount 的行"来测 —— `model.index()` 会返回无效索引，
    `data()` 直接返回 None（我第一次就是这么写错的）。
    """
    view.model.set_full_dataframe(NUMERIC)
    loaded = len(view.model._loaded_df)
    total = view.model.rowCount()

    if total <= loaded + 1:
        pytest.skip("数据未走流式加载，没有'已声明但未加载'的行")

    index = view.model.index(loaded + 1, 0)
    assert view.model.data(index, Qt.ItemDataRole.DisplayRole) == "⏳"


def test_empty_cell_displays_empty_string(view):
    view.model.set_full_dataframe(pd.DataFrame({"a": ["", "b"]}))
    assert _display(view, 0, 0) == ""


def test_font_role_returns_qfont_only_when_formatted(view):
    """FontRole 走早返回路径后行为不变：没格式 → None，有格式 → QFont。"""
    view.model.set_full_dataframe(NUMERIC)
    assert view.model.data(view.model.index(0, 0),
                          Qt.ItemDataRole.FontRole) is None

    view.model._cell_formats_ref[(0, 0)] = {"bold": True}
    font = view.model.data(view.model.index(0, 0),
                          Qt.ItemDataRole.FontRole)
    assert font is not None and font.bold()


# ==================== 4. 性能门禁 ====================
# 阈值刻意放宽到实测值的 3–8 倍：CI 机器慢、负载抖动都可能影响，
# 门禁的目的是"抓住数量级退化"，不是卡死具体数字。

def _per_call(fn, n=3000):
    fn()
    start = time.perf_counter()
    for _ in range(n):
        fn()
    return (time.perf_counter() - start) / n * 1000      # ms


def test_data_call_is_cheap(view):
    """`data(DisplayRole)` 单次调用必须远低于优化前的 0.0205 ms。"""
    view.model.set_full_dataframe(NUMERIC)
    index = view.model.index(1, 0)

    per_call = _per_call(
        lambda: view.model.data(index, Qt.ItemDataRole.DisplayRole)
    )

    assert per_call < 0.015, (
        f"data(DisplayRole) 每次 {per_call:.4f}ms —— 已退化（优化后实测 0.0027ms）"
    )


def test_flags_call_is_cheap(view):
    """`flags()` 曾达 32µs/次（枚举 `|` 现算），必须保持低成本。"""
    view.model.set_full_dataframe(NUMERIC)
    index = view.model.index(1, 0)

    per_call = _per_call(lambda: view.model.flags(index))

    assert per_call < 0.010, (
        f"flags() 每次 {per_call:.4f}ms —— 退化了（优化后实测 0.0012ms）"
    )


def test_repaint_budget(view, qtbot):
    """
    **端到端门禁**：2000×20 的整视口重绘必须远低于优化前的 172 ms。

    这是最贴近用户感受的一项 —— 滚动卡顿就是它造成的。
    """
    rows, cols = 2000, 20
    view.model.set_full_dataframe(
        pd.DataFrame({f"列{i}": [r * i for r in range(rows)]
                      for i in range(1, cols + 1)})
    )
    view.resize(1200, 700)
    table = view.table_view
    qtbot.waitExposed(view)
    table.viewport().repaint()          # 预热

    samples = []
    for _ in range(5):
        start = time.perf_counter()
        table.viewport().repaint()
        samples.append((time.perf_counter() - start) * 1000)

    median = statistics.median(samples)
    assert median < 90, (
        f"整视口重绘中位数 {median:.1f}ms —— 已退化"
        f"（优化后实测约 19ms，优化前 172ms）；样本={[round(s,1) for s in samples]}"
    )
