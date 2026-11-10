"""BeeSheet 图表生成补测（不弹真实窗口）。"""
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QWidget
import pandas as pd

from beeoffice.plugins.beesheet_chart_mixin import ChartMixin


class Cell:
    def __init__(self, r, c): self._r, self._c = r, c
    def row(self): return self._r
    def column(self): return self._c


class Sel:
    def __init__(self, cells): self._cells = cells
    def indexes(self): return self._cells


class SelM:
    def __init__(self, cells): self._cells = cells
    def selection(self): return Sel(self._cells) if self._cells else None


class TV:
    def __init__(self, cells): self._model = SelM(cells)
    def selectionModel(self): return self._model


class M:
    def __init__(self, rows):
        self.df = pd.DataFrame(rows)
    def get_value(self, r, c):
        return self.df.iloc[r, c]


class S(ChartMixin, QWidget):
    def __init__(self, rows, cells):
        QWidget.__init__(self)
        self.model = M(rows)
        self.table_view = TV(cells)
    def _set_status(self, text, ms=0):
        pass


def test_generate_all_chart_types(qtbot, monkeypatch):
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    rows = {"name": ["a", "b"], "value": [1.0, 2.0]}
    cells = [Cell(0, 1), Cell(1, 1)]
    chart = S(rows, cells)
    qtbot.addWidget(chart)
    for kind in ("bar", "line", "pie", "scatter", "area", "radar"):
        chart._generate_chart(kind)


def test_generate_pie_all_zero(qtbot, monkeypatch):
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)
    called = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: called.append(a))
    chart = S({"name": ["a"], "value": [0.0]}, [Cell(0, 1)])
    qtbot.addWidget(chart)
    chart._generate_chart("pie")
    assert called


def test_create_chart_no_selection(qtbot, monkeypatch):
    called = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: called.append(a))
    chart = S({"name": ["a"], "value": [1.0]}, [])
    qtbot.addWidget(chart)
    chart._create_chart()
    assert called
