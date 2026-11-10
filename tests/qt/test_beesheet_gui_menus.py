"""结构化补测：BeeSheet 导出/清洗/表头菜单。"""
import pandas as pd
from PySide6.QtCore import QObject, QPoint, QRect, Signal
from PySide6.QtWidgets import QPushButton, QWidget

from beeoffice.plugins.beesheet_data_mixin import DataMixin


class FakeModel(QObject):
    layoutChanged = Signal()
    dataChanged = Signal()

    def __init__(self):
        super().__init__()
        self._loaded_df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})

    @property
    def df(self):
        return self._loaded_df

    def index(self, row, col):
        return (row, col)


class FakeIndex:
    def __init__(self):
        self._valid = True

    def isValid(self):
        return self._valid

    def column(self):
        return 0

    def row(self):
        return 0


class FakeHeader:
    def logicalIndexAt(self, pos):
        return 0

    def sectionViewportPosition(self, col):
        return 0

    def height(self):
        return 20

    def mapToGlobal(self, pos):
        return pos


class FakeViewport:
    def mapToGlobal(self, pos):
        return pos


class FakeTableView:
    def currentIndex(self):
        return FakeIndex()

    def viewport(self):
        return FakeViewport()

    def visualRect(self, index):
        return QRect(0, 0, 10, 10)

    def horizontalHeader(self):
        return FakeHeader()


class FakeMenuSheet(DataMixin, QWidget):
    def __init__(self):
        QWidget.__init__(self)
        self.model = FakeModel()
        self.table_view = FakeTableView()
        self._export_btn = QPushButton("export", self)
        self._active_filters = {}
        self._conditional_formats = {}
        self._filter_list = None
        self._filter_popup = None
        self.statuses = []

    def _set_status(self, text, ms=0):
        self.statuses.append(text)

    def _freeze_cell(self):
        pass

    def _freeze_column(self, col):
        pass

    def _add_comment(self):
        pass


class FakeAction:
    def __init__(self):
        class Sig:
            def connect(self, fn):
                pass
        self.triggered = Sig()


class FakeMenu:
    def __init__(self, *a, **k):
        self.actions_list = []

    def addAction(self, text):
        self.actions_list.append(text)
        return FakeAction()

    def addMenu(self, text):
        return FakeMenu()

    def addSeparator(self):
        pass

    def addSection(self, text):
        pass

    def exec(self, *a, **k):
        FakeMenu.last = list(self.actions_list)


def test_show_export_menu(qtbot, monkeypatch):
    import beeoffice.plugins.beesheet_data_mixin as m
    sheet = FakeMenuSheet()
    qtbot.addWidget(sheet)
    monkeypatch.setattr(m, "QMenu", FakeMenu)
    sheet._show_export_menu()
    joined = " ".join(FakeMenu.last)
    assert "Excel" in joined and "CSV" in joined


def test_show_clean_menu(qtbot, monkeypatch):
    import beeoffice.plugins.beesheet_data_mixin as m
    sheet = FakeMenuSheet()
    qtbot.addWidget(sheet)
    monkeypatch.setattr(m, "QMenu", FakeMenu)
    sheet._show_clean_menu()
    assert any("空格" in t for t in FakeMenu.last)


def test_show_header_context_menu(qtbot, monkeypatch):
    import beeoffice.plugins.beesheet_data_mixin as m
    sheet = FakeMenuSheet()
    qtbot.addWidget(sheet)
    monkeypatch.setattr(m, "QMenu", FakeMenu)
    sheet._show_header_context_menu(QPoint(1, 1))
    assert any("筛选" in t for t in FakeMenu.last)


def test_show_filter_popup(qtbot):
    sheet = FakeMenuSheet()
    qtbot.addWidget(sheet)
    sheet._show_filter_popup(0)
    assert sheet._filter_list is not None
    assert sheet._filter_list.count() == 2
    assert sheet._filter_popup is not None
    sheet._filter_popup.close()
