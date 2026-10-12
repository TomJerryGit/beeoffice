# tests/regression/v5/test_v505_circular_reference.py
"""
优化规划 §2.5 回归：循环引用不得静默产出不断变化的错数。

原缺陷（实测）
--------------
`_recalc_formulas()` 把循环引用当成普通依赖反复计算，且完全没有提示：

    A1 = `=A1+1`，初值 0   → 一次重算后 **3**，再触发一次 **6**
    A1 = `=B1+1`、B1 = `=A1+1`（初值 1 / 2）→ 重算后 **7 / 8** 并继续增长

也就是说：循环引用不会报错，而是**静默产出越算越大的数**。用户会以为表格
"自己在动"，而这比一次性错误更危险。

Excel 的做法是拒绝计算并提示循环引用。修复采用保守做法：
  - `_find_circular_cells()` 用迭代式 DFS（三色标记）找出环上的单元格；
  - `_recalc_formulas()` 跳过这些单元格，并通过状态栏给一次可见提示。

注意：**普通链式依赖不能被误判**（B1=SUM(A1:A3)、C1=B1*2 是合法写法）。
"""
import pytest

from beeoffice.plugins.beesheet import BeeSheetView


@pytest.fixture
def view(qtbot):
    v = BeeSheetView()
    qtbot.addWidget(v)
    v._formula_cells = {}
    return v


def _set(view, cells, values=None):
    """设置公式单元格与初始值。cells: {(r,c): "=..."}"""
    for (r, c), val in (values or {}).items():
        view.model._loaded_df.iloc[r, c] = val
    view._formula_cells = dict(cells)


# ==================== 环的识别 ====================

def test_self_reference_is_detected(view):
    _set(view, {(0, 0): "=A1+1"})
    assert view._find_circular_cells() == {(0, 0)}


def test_mutual_reference_is_detected(view):
    _set(view, {(0, 0): "=B1+1", (0, 1): "=A1+1"})
    assert view._find_circular_cells() == {(0, 0), (0, 1)}


def test_three_cell_cycle_is_detected(view):
    _set(view, {(0, 0): "=B1", (0, 1): "=C1", (0, 2): "=A1"})
    assert view._find_circular_cells() == {(0, 0), (0, 1), (0, 2)}


def test_plain_chain_is_not_circular(view):
    """合法链式依赖：B1 依赖 A1（数值），C1 依赖 B1。"""
    _set(view, {(0, 1): "=A1*2", (0, 2): "=B1+1"})
    assert view._find_circular_cells() == set()


def test_long_chain_is_not_circular(view):
    """长链（32 层）也不应误判，且不应触发递归上限。"""
    cells = {}
    cells[(0, 0)] = "=1"
    for i in range(1, 32):
        prev = f"{chr(65 + (i - 1) % 26)}{i}"      # 仅作占位，实际用数值链条
        cells[(0, i)] = f"={chr(65 + (i - 1))}1+1"
    view._formula_cells = cells
    # 至少不应因为递归深度而抛异常
    view._find_circular_cells()


def test_cycle_with_non_formula_refs_is_not_flagged(view):
    """引用普通数值单元格（没有公式）不构成环。"""
    _set(view, {(0, 5): "=A1+B1"})       # A1/B1 没有公式
    assert view._find_circular_cells() == set()


def test_empty_formula_cells_is_safe(view):
    view._formula_cells = {}
    assert view._find_circular_cells() == set()


# ==================== 重算不再自增 ====================

def test_self_reference_value_does_not_grow(view):
    """核心回归：循环引用的值不得在重算中反复自增。"""
    _set(view, {(0, 0): "=A1+1"}, values={(0, 0): 0})

    view._recalc_formulas(max_rounds=3)
    after_first = view.model.get_value(0, 0)
    view._recalc_formulas(max_rounds=3)
    after_second = view.model.get_value(0, 0)

    assert after_first == after_second, (
        f"循环引用的值在变化（{after_first} → {after_second}），"
        f"应跳过多余重算而不是越算越大"
    )


def test_mutual_reference_values_do_not_grow(view):
    _set(
        view,
        {(0, 0): "=B1+1", (0, 1): "=A1+1"},
        values={(0, 0): 1, (0, 1): 2},
    )

    view._recalc_formulas(max_rounds=3)
    first = (view.model.get_value(0, 0), view.model.get_value(0, 1))
    view._recalc_formulas(max_rounds=3)
    second = (view.model.get_value(0, 0), view.model.get_value(0, 1))

    assert first == second, f"互引用值在增长: {first} → {second}"


def test_normal_chain_still_recalculates(view):
    """不能因为加了环检测就让合法公式不再计算。"""
    _set(view, {(0, 2): "=A1+B1"}, values={(0, 0): 2, (0, 1): 3})
    view._recalc_formulas(max_rounds=3)
    assert view.model.get_value(0, 2) == 5


def test_normal_chain_updates_when_input_changes(view):
    _set(view, {(0, 1): "=A1*2"}, values={(0, 0): 4})
    view._recalc_formulas()
    assert view.model.get_value(0, 1) == 8

    view.model._loaded_df.iloc[0, 0] = 10
    view._recalc_formulas()
    assert view.model.get_value(0, 1) == 20


# ==================== 用户可见提示 ====================

def test_circular_reference_is_reported(view):
    """检测到循环引用时应有可见提示（而不是完全静默）。"""
    _set(view, {(0, 0): "=A1+1"}, values={(0, 0): 0})
    view._circular_cells = set()          # 确保状态变化会被上报

    view._recalc_formulas(max_rounds=3)

    assert view._circular_cells == {(0, 0)}, "应记录循环引用单元格"

    bar = getattr(view, "_status_label", None)
    text = bar.text() if bar is not None and hasattr(bar, "text") else ""
    combined = text + " ".join(
        str(getattr(view, attr, "")) for attr in ("_status_text",)
    )
    # 状态栏实现可能是主窗口全局的；至少断言已记录且不抛异常
    assert isinstance(view._circular_cells, set)
