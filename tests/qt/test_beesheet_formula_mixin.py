"""结构化补测：FormulaMixin 公式栏/预览/函数插入/重算。"""
import pandas as pd
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QLabel, QLineEdit, QWidget

from beeoffice.plugins.beesheet_formula_mixin import FormulaMixin


class FakeModel(QObject):
    dataChanged = Signal()

    def __init__(self):
        super().__init__()
        self._loaded_df = pd.DataFrame({"a": [1, 2], "b": [0, 0]})
        self._total_rows = 2
        self._total_cols = 2

    def get_value(self, row, col):
        return self._loaded_df.iloc[row, col]

    def set_value(self, row, col, value):
        self._loaded_df.iloc[row, col] = value

    def index(self, row, col):
        return (row, col)


class FakeIndex:
    def __init__(self, row=0, col=0, valid=True):
        self._row, self._col, self._valid = row, col, valid

    def isValid(self):
        return self._valid

    def row(self):
        return self._row

    def column(self):
        return self._col


class FakeTableView:
    def __init__(self, valid=True):
        self._index = FakeIndex(valid=valid)

    def currentIndex(self):
        return self._index


class FakeFormulaSheet(FormulaMixin, QWidget):
    FUNCTION_REFERENCE = {"SUM": ("SUM(数值1, [数值2], ...)", "数学")}

    def __init__(self, valid=True):
        QWidget.__init__(self)
        self.formula_bar = QLineEdit(self)
        self._param_tip = QLabel(self)
        self._preview_label = QLabel(self)
        self._last_func_tip = ""
        self._formula_cells = {}
        self.model = FakeModel()
        self.table_view = FakeTableView(valid)
        self.statuses = []

    def _set_status(self, text, ms=0):
        self.statuses.append(text)


def test_param_tip_and_preview(qtbot):
    s = FakeFormulaSheet()
    qtbot.addWidget(s)
    s._update_param_tip("=SUM(")
    assert "SUM" in s._param_tip.text()
    assert s._last_func_tip == "SUM"
    s._update_param_tip("=NOPE(")
    assert s._last_func_tip == ""

    s._update_formula_preview("=1+1")
    assert s._preview_label.text() == "= 2"
    s._update_formula_preview("=SUM(")
    assert not s._preview_label.isVisible()
    s._update_formula_preview("abc")
    assert not s._preview_label.isVisible()


def test_insert_function(qtbot):
    s = FakeFormulaSheet()
    qtbot.addWidget(s)
    s._insert_function("SUM")
    assert s.formula_bar.text() == "=SUM("
    assert s.statuses


def test_insert_function_without_cell(qtbot, monkeypatch):
    import beeoffice.plugins.beesheet_formula_mixin as m
    monkeypatch.setattr(m.QMessageBox, "information", lambda *a, **k: None)
    s = FakeFormulaSheet(valid=False)
    qtbot.addWidget(s)
    s.formula_bar.setText("")
    s._insert_function("SUM")
    assert s.formula_bar.text() == ""


def test_recalc_formulas(qtbot):
    s = FakeFormulaSheet()
    qtbot.addWidget(s)
    s._formula_cells = {(0, 1): "=1+1"}
    s._recalc_formulas()
    assert s.model.get_value(0, 1) == 2
