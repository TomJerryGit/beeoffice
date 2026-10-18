# -*- coding: utf-8 -*-
"""
蜜算宏：录制与回放（P1-29）

缺陷：
    菜单里有"录制宏 / 播放宏"，但 `BeeSheetView` 上没有
    `_toggle_macro_recording` / `_play_macro`，调用方 hasattr 判断后
    静默跳过——点击完全没反应，属于"菜单在、功能没有"。

修复：
    新增宏录制器 + 视图混入，录制单元格赋值并回放到当前表。
"""
import pytest

pytest.importorskip("PySide6.QtWidgets")

pd = pytest.importorskip("pandas")

from PySide6.QtCore import Qt  # noqa: E402


@pytest.fixture
def recorder():
    """
    用模块级单例：模型 `setData` 记录到的是 `RECORDER`，
    测试若另建实例会录不到东西（这也说明单例接线是通的）。
    """
    from beeoffice.plugins import macro_recorder

    r = macro_recorder.RECORDER
    r.stop()
    r.clear()
    yield r
    r.stop()
    r.clear()


@pytest.fixture
def model():
    from beeoffice.plugins.beesheet_model import SheetDataModel

    m = SheetDataModel()
    m.set_full_dataframe(pd.DataFrame({"a": [0, 0], "b": [0, 0]}))
    return m


def _get(model, r, c):
    return model.data(model.index(r, c), Qt.DisplayRole)


def test_record_and_play_roundtrip(recorder, model):
    recorder.start()
    model.setData(model.index(0, 0), "7", Qt.EditRole)
    model.setData(model.index(1, 1), "9", Qt.EditRole)
    assert recorder.stop() == 2

    # 清掉数据再回放
    model.setData(model.index(0, 0), "0", Qt.EditRole)
    model.setData(model.index(1, 1), "0", Qt.EditRole)
    assert recorder.play(model) == 2
    assert _get(model, 0, 0) == "7"
    assert _get(model, 1, 1) == "9"


def test_not_recording_means_no_capture(recorder, model):
    model.setData(model.index(0, 0), "5", Qt.EditRole)
    assert len(recorder) == 0


def test_repeated_edit_same_cell_collapses(recorder, model):
    """连续改同一格只保留最后一次，避免拖拽填充产生上百条动作。"""
    recorder.start()
    for v in ("1", "2", "3"):
        model.setData(model.index(0, 0), v, Qt.EditRole)
    assert recorder.stop() == 1
    assert recorder.actions[0][3] == "3"


def test_play_does_not_record_itself(recorder, model):
    recorder.start()
    model.setData(model.index(0, 0), "4", Qt.EditRole)
    recorder.stop()

    recorder.start()                 # 再开一轮录制（start 会清空动作）
    assert len(recorder) == 0
    recorder.play(model)             # 回放期间不得被记进新宏
    assert len(recorder) == 0, "回放产生的 setData 被误录进了宏"


def test_empty_macro_plays_zero(recorder, model):
    assert recorder.play(model) == 0


def test_view_exposes_macro_entry_points(qtbot):
    """视图必须真的有这两个方法，否则菜单点了没反应。"""
    from beeoffice.plugins.beesheet import BeeSheetView

    view = BeeSheetView()
    qtbot.addWidget(view)
    assert hasattr(view, "_toggle_macro_recording")
    assert hasattr(view, "_play_macro")

    view._toggle_macro_recording()   # 开始
    view.model.setData(view.model.index(0, 0), "42", Qt.EditRole)
    view._toggle_macro_recording()   # 结束
    view._play_macro()               # 回放不应抛异常
    view.close()
