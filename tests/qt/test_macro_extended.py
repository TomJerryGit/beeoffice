# -*- coding: utf-8 -*-
"""
宏扩展：格式与跨表动作（阶段三 #8）

v1 只录制单元格赋值；本版扩成三类：
    ("set", r, c, v) / ("format", r, c, key, value) / ("sheet", name)

重点验证：
    · 三类动作按顺序录制与回放
    · 缺回调时跳过而不是抛异常
    · v1 录制的四元组仍可播放（向后兼容）
    · 视图侧：格式变更会被录下来，回放能写回
"""
import pytest

pytest.importorskip("PySide6.QtWidgets")

pd = pytest.importorskip("pandas")

from PySide6.QtCore import Qt  # noqa: E402


@pytest.fixture
def recorder():
    from beeoffice.plugins import macro_recorder

    r = macro_recorder.RECORDER
    r.stop()
    r.clear()
    yield r
    r.stop()
    r.clear()


# ==================== 录制器本身 ====================
def test_records_three_kinds(recorder):
    recorder.start()
    recorder.record_sheet("表2")
    recorder.record_set(0, 0, "1")
    recorder.record_format(0, 0, "bold", True)
    recorder.stop()

    kinds = [a[0] for a in recorder.actions]
    assert kinds == ["sheet", "set", "format"]
    assert recorder.counts() == {"set": 1, "format": 1, "sheet": 1}


def test_consecutive_same_sheet_is_collapsed(recorder):
    recorder.start()
    recorder.record_sheet("表2")
    recorder.record_sheet("表2")
    recorder.stop()
    assert len(recorder) == 1


def test_play_without_format_callback_skips(recorder):
    recorder.start()
    recorder.record_set(0, 0, "1")
    recorder.record_format(0, 0, "bold", True)
    recorder.stop()

    class _Model:
        def __init__(self):
            self.calls = 0

        def index(self, r, c):
            return (r, c)

        def setData(self, idx, value, role=None):
            self.calls += 1
            return True

    m = _Model()
    applied = recorder.play(m)          # 没有 apply_format
    assert applied == 1                 # 只执行了 set
    assert m.calls == 1


def test_play_backward_compatible_with_v1_actions(recorder):
    """v1 录制的是四元组，格式没变，必须还能播。"""
    recorder.start()
    recorder.record_set(1, 2, "旧宏")
    recorder.stop()

    class _Model:
        def __init__(self):
            self.written = []

        def index(self, r, c):
            return (r, c)

        def setData(self, idx, value, role=None):
            self.written.append((idx, value))
            return True

    m = _Model()
    assert recorder.play(m) == 1
    assert m.written == [((1, 2), "旧宏")]


def test_sheet_callback_missing_is_skipped(recorder):
    recorder.start()
    recorder.record_sheet("表2")
    recorder.stop()

    class _Model:
        def index(self, r, c):
            return (r, c)

        def setData(self, *a, **k):
            return True

    assert recorder.play(_Model()) == 0


def test_sheet_callback_result_is_respected(recorder):
    recorder.start()
    recorder.record_sheet("不存在")
    recorder.stop()
    assert recorder.play(None, switch_sheet=lambda name: False) == 0
    assert recorder.play(None, switch_sheet=lambda name: True) == 1


# ==================== 视图集成 ====================
@pytest.fixture(scope="module")
def view(qapp):
    from beeoffice.plugins.beesheet import BeeSheetView

    v = BeeSheetView()
    v.show()
    yield v
    v.close()
    v.deleteLater()


@pytest.fixture(autouse=True)
def _reset(view, recorder):
    view.model.set_full_dataframe(
        pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    )
    view._cell_formats = {}


def test_format_change_is_recorded_and_replayed(view, recorder):
    from PySide6.QtWidgets import QTableView

    recorder.start()
    view.table_view.selectAll()
    view._apply_format_to_selection("bold", True)
    n = recorder.stop()

    assert n >= 1, "格式变更没有被录制"
    assert any(a[0] == "format" and a[3] == "bold" for a in recorder.actions)

    view._cell_formats = {}
    applied = recorder.play(
        view.model, apply_format=view._macro_apply_format
    )
    assert applied == n
    assert view._cell_formats[(0, 0)].get("bold") is True


def test_play_shows_counts_in_status(view, recorder):
    recorder.start()
    view.model.setData(view.model.index(0, 0), "9", Qt.EditRole)
    recorder.record_format(0, 0, "bold", True)
    recorder.stop()

    view._play_macro()
    assert "赋值 1" in view.status_label.text()
    assert "格式 1" in view.status_label.text()


def test_switch_sheet_returns_false_without_main_window(view, recorder):
    """没有主窗口（单测环境）时应安全返回 False，而不是抛异常。"""
    assert view._macro_switch_sheet("任意") is False


def test_switch_sheet_finds_tab(view, monkeypatch):
    class _TabWidget:
        model = view.model

    class _TM:
        def count(self):
            return 1

        def widget(self, i):
            return _TabWidget()

        def tabText(self, i):
            return "📊 销售表"

        def setCurrentIndex(self, i):
            self.current = i

    tm = _TM()

    class _Main:
        tab_manager = tm

    monkeypatch.setattr(view, "_find_main_window", lambda: _Main())
    assert view._macro_switch_sheet("销售表") is True
    assert tm.current == 0
    assert view._macro_switch_sheet("不存在") is False
