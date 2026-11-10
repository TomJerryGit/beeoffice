"""结构化补测：BeeSheet 筛选弹窗交互。"""
import pandas as pd
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QListWidget, QWidget

from beeoffice.plugins.beesheet_data_mixin import DataMixin


class FakeModel(QObject):
    layoutChanged = Signal()
    dataChanged = Signal()

    def __init__(self):
        super().__init__()
        self._loaded_df = pd.DataFrame({"city": ["北京", "上海", "北京", "广州"]})

    @property
    def df(self):
        return self._loaded_df

    def index(self, row, col):
        return (row, col)


class FakePopup:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeFilterSheet(DataMixin, QWidget):
    def __init__(self):
        QWidget.__init__(self)
        self.model = FakeModel()
        self._filter_list = QListWidget(self)
        self._filter_popup = FakePopup()
        self._active_filters = {}
        self.statuses = []

    def _set_status(self, text, ms=0):
        self.statuses.append(text)


def test_update_filter_list_and_search(qtbot):
    s = FakeFilterSheet()
    qtbot.addWidget(s)
    s._update_filter_list(0)
    assert s._filter_list.count() == 3  # 北京/上海/广州
    s._update_filter_list(0, "北")
    assert s._filter_list.count() == 1


def test_select_all_false_then_apply_filter(qtbot):
    s = FakeFilterSheet()
    qtbot.addWidget(s)
    s._update_filter_list(0)
    s._select_all_filter(False)
    # 仅保留北京
    for i in range(s._filter_list.count()):
        item = s._filter_list.item(i)
        if item.data(Qt.UserRole) == "北京":
            item.setCheckState(Qt.Checked)
    s._apply_filter(0)
    assert s._filter_popup.closed is True
    assert 0 in s._active_filters
    assert len(s.model._loaded_df) == 2


def test_apply_filter_all_selected_clears(qtbot):
    s = FakeFilterSheet()
    qtbot.addWidget(s)
    s._update_filter_list(0)
    s._active_filters[0] = {"x"}
    s._apply_filter(0)
    assert 0 not in s._active_filters
