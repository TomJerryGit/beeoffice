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


def test_save_chart(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    chart = S({"name": ["a"], "value": [1.0]}, [Cell(0, 1)])
    saved = []
    class Fig:
        def savefig(self, path, **kwargs):
            saved.append((path, kwargs))
    target = tmp_path / "chart.png"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *a, **k: (str(target), ""))
    chart._save_chart(Fig(), None)
    assert saved and saved[0][0] == str(target)
    # 取消保存
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    chart._save_chart(Fig(), None)
    assert len(saved) == 1


def test_create_chart_with_selection(qtbot, monkeypatch):
    calls = []
    chart = S({"name": ["a", "b"], "value": [1.0, 2.0]},
              [Cell(0, 1), Cell(1, 1)])
    qtbot.addWidget(chart)
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)
    monkeypatch.setattr(chart, "_generate_chart", lambda kind: calls.append(kind))
    chart._create_chart()
    assert calls == ["bar"]


def test_pivot_no_data(qtbot, monkeypatch):
    import pandas as pd
    from PySide6.QtWidgets import QMessageBox
    called = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: called.append(a))
    chart = S({"name": [], "value": []}, [])
    chart.model.df = pd.DataFrame(columns=["name", "value"])
    qtbot.addWidget(chart)
    chart._show_pivot_table()
    assert called


def test_pivot_accepted_creates_tab(qtbot, monkeypatch):
    import beeoffice.plugins.beesheet_chart_mixin as m
    import pandas as pd
    from PySide6.QtWidgets import QDialog

    class FakeDlg:
        Accepted = QDialog.Accepted
        def __init__(self, df, parent):
            self.result_config = (
                pd.DataFrame({"x": [1]}),
                {"rows": ["name"], "cols": [], "values": ["value"],
                 "aggfunc": "sum", "margins": False},
            )
        def exec(self):
            return QDialog.Accepted

    class TM:
        def __init__(self): self.tabs = []
        def addTab(self, w, title): self.tabs.append((w, title))
        def setCurrentWidget(self, w): self.current = w

    class Parent:
        def __init__(self): self.tab_manager = TM()

    monkeypatch.setattr(m, "PivotTableDialog", FakeDlg)
    chart = S({"name": ["a", "b"], "value": [1.0, 2.0]}, [])
    parent = Parent()
    chart._find_main_window = lambda: parent
    qtbot.addWidget(chart)
    chart._show_pivot_table()
    assert parent.tab_manager.tabs
