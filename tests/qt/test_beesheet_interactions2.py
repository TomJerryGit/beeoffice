"""BeeSheet 复制/智能粘贴/行头菜单交互补测。"""
import pandas as pd
from PySide6.QtCore import QObject, QPoint, Signal
from PySide6.QtWidgets import QApplication, QWidget

from beeoffice.plugins.beesheet_data_mixin import DataMixin


class FakeModel(QObject):
    layoutChanged = Signal()
    dataChanged = Signal(object, object)

    def __init__(self):
        super().__init__()
        self._loaded_df = pd.DataFrame({"city": ["A", "B"], "num": [1, 2]})
        self._total_rows = 2
        self._total_cols = 2

    @property
    def df(self):
        return self._loaded_df

    def index(self, row, col):
        return (row, col)

    def get_value(self, row, col):
        return self._loaded_df.iloc[row, col]

    def columnCount(self):
        return len(self._loaded_df.columns)

    def rowCount(self):
        return len(self._loaded_df)


class Cell:
    def __init__(self, row, col):
        self._row, self._col = row, col
    def row(self): return self._row
    def column(self): return self._col


class Selection:
    def __init__(self, cells):
        self._cells = cells
    def indexes(self):
        return self._cells


class SelectionModel:
    def __init__(self, cells):
        self._cells = cells
    def selection(self):
        return Selection(self._cells)


class Index(Cell):
    def isValid(self): return True


class VerticalHeader:
    def logicalIndexAt(self, pos): return 0
    def mapToGlobal(self, pos): return QPoint(0, 0)


class FakeTableView:
    def __init__(self):
        self.selection_model = SelectionModel([Cell(0, 0), Cell(0, 1)])
        self._index = Index(0, 0)
    def selectionModel(self): return self.selection_model
    def currentIndex(self): return self._index
    def verticalHeader(self): return VerticalHeader()


class FakeSheet(DataMixin, QWidget):
    def __init__(self):
        QWidget.__init__(self)
        self.model = FakeModel()
        self.table_view = FakeTableView()
        self._conditional_formats = {}
        self.statuses = []

    def _set_status(self, text, ms=0):
        self.statuses.append(text)


class FakeAction:
    def __init__(self):
        class Sig:
            def connect(self, fn): pass
        self.triggered = Sig()


class FakeMenu:
    last = []

    def __init__(self, *a, **k):
        self.actions_list = []
    def addAction(self, text):
        self.actions_list.append(text); return FakeAction()
    def addSeparator(self): pass
    def addSection(self, text): pass
    def addMenu(self, text): return FakeMenu()
    def exec(self, *a, **k):
        FakeMenu.last = list(self.actions_list)


def test_copy_as_markdown(qtbot):
    s = FakeSheet()
    qtbot.addWidget(s)
    s._copy_as_markdown()
    text = QApplication.clipboard().text()
    assert "| city | num |" in text
    assert s.statuses


def test_smart_paste_tsv(qtbot):
    s = FakeSheet()
    qtbot.addWidget(s)
    QApplication.clipboard().setText("X\tY\nZ\tW")
    s._smart_paste()
    assert s.model.get_value(0, 0) == "X"
    assert s.model.get_value(1, 1) == "W"


def test_smart_paste_single_value(qtbot):
    s = FakeSheet()
    qtbot.addWidget(s)
    QApplication.clipboard().setText("42")
    s._smart_paste()
    assert s.model.get_value(0, 0) == 42


def test_show_row_header_menu(qtbot, monkeypatch):
    import beeoffice.plugins.beesheet_data_mixin as m
    s = FakeSheet()
    qtbot.addWidget(s)
    FakeMenu.last = []
    monkeypatch.setattr(m, "QMenu", FakeMenu)
    s._show_row_header_menu(QPoint(1, 1))
    assert any("复制此行" in t for t in FakeMenu.last)
    assert any("删除此行" in t for t in FakeMenu.last)
