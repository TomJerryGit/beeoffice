"""GUI 覆盖率批次：BeeSheet 导入与填充柄。"""
import pandas as pd
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from beeoffice.plugins.beesheet import BeeSheetView


@pytest.fixture
def sheet(qtbot, monkeypatch):
    v = BeeSheetView()
    qtbot.addWidget(v)
    v.model.set_full_dataframe(pd.DataFrame({"A": [1, 2], "B": ["x", "y"]}))
    v.table_view.setModel(v.model)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    return v


def test_import_text_file(sheet, tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("a\tb\n1\t2", encoding="utf-8")
    sheet._import_text_file(str(f))
    assert len(sheet.model._loaded_df) == 2


def test_read_and_apply_csv(sheet, tmp_path):
    f = tmp_path / "a.csv"
    f.write_text("a,b\n1,2\n3,4", encoding="utf-8")
    df = sheet._read_sheet_file(str(f))
    assert len(df) == 2
    assert sheet._apply_imported_dataframe(df, str(f)) is True
    assert len(sheet.model._loaded_df) == 2


def test_apply_large_dataframe(sheet, monkeypatch):
    big = pd.DataFrame({"A": range(200001)})
    calls = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    assert sheet._apply_imported_dataframe(big, "big.csv") is False
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    assert sheet._apply_imported_dataframe(big, "big.csv") is True
    assert sheet.model._full_df is not None and len(sheet.model._full_df) == 200000


def test_import_file_small(sheet, tmp_path, monkeypatch):
    f = tmp_path / "a.csv"
    f.write_text("a,b\n1,2", encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(f), ""))
    sheet._import_file()
    assert len(sheet.model._loaded_df) == 1


class FakeHandle(QWidget):
    def __init__(self):
        super().__init__()
        self.calls = []
    def show(self): self.calls.append("show")
    def hide(self): self.calls.append("hide")
    def move(self, x, y): self.calls.append(("move", x, y))
    def raise_(self): self.calls.append("raise")
    def grabMouse(self): self.calls.append("grab")
    def releaseMouse(self): self.calls.append("release")


class FakeEvent:
    def __init__(self, button=Qt.LeftButton, pos=QPoint(0, 0)):
        self._button = button
        self._pos = pos
        self.accepted = False
    def button(self): return self._button
    def globalPosition(self):
        outer = self
        class P:
            def toPoint(self): return outer._pos
        return P()
    def globalPos(self): return self._pos
    def accept(self): self.accepted = True


def test_fill_handle_position_and_press(sheet):
    sheet._fill_handle = FakeHandle()
    sheet.table_view.selectRow(0)
    sheet._update_fill_handle_position()
    assert "show" in sheet._fill_handle.calls
    ev = FakeEvent()
    sheet._fill_handle_press(ev)
    assert sheet._fill_start_range is not None
    assert ev.accepted


def test_fill_handle_move_release(sheet, monkeypatch):
    sheet._fill_handle = FakeHandle()
    sheet._fill_start_range = (0, 0, 0, 0)
    sheet._fill_direction = "down"
    sheet._fill_target = 2
    sheet._formula_cells = {}
    monkeypatch.setattr(sheet.table_view, "indexAt", lambda pos: sheet.model.index(2, 0))
    ev = FakeEvent(pos=QPoint(0, 0))
    sheet._fill_handle_move(ev)
    assert sheet._fill_direction == "down"
    sheet._fill_handle_release(FakeEvent())
    assert sheet.model.get_value(1, 0) == 1


def test_fill_release_down_formula(sheet):
    sheet._fill_handle = FakeHandle()
    sheet._fill_start_range = (0, 0, 0, 0)
    sheet._fill_direction = "down"
    sheet._fill_target = 2
    sheet._formula_cells = {(0, 0): "=A1"}
    sheet._fill_handle_release(FakeEvent())
    assert (1, 0) in sheet._formula_cells


def test_fill_release_right(sheet):
    sheet._fill_handle = FakeHandle()
    sheet.model.set_full_dataframe(pd.DataFrame({"A": [1, 2], "B": ["", ""]}))
    sheet.table_view.setModel(sheet.model)
    sheet._fill_start_range = (0, 0, 0, 0)
    sheet._fill_direction = "right"
    sheet._fill_target = 1
    sheet._formula_cells = {}
    sheet._fill_handle_release(FakeEvent())
    assert sheet.model.get_value(0, 1) == 1


def test_fill_release_none(sheet):
    sheet._fill_handle = FakeHandle()
    sheet._fill_start_range = None
    sheet._fill_direction = None
    sheet._fill_handle_release(FakeEvent())
    assert sheet._fill_start_range is None


def test_import_large_prompt_no(sheet, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    f = tmp_path / "a.txt"; f.write_text("a\tb", encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(f), ""))
    import beeoffice.plugins.beesheet as m
    monkeypatch.setattr(m.os.path, "getsize", lambda p: 60 * 1024 * 1024)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    sheet._import_file()
    assert len(sheet.model._loaded_df) == 1


def test_import_large_prompt_yes(sheet, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    f = tmp_path / "a.csv"; f.write_text("a\nb", encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(f), ""))
    import beeoffice.plugins.beesheet as m
    monkeypatch.setattr(m.os.path, "getsize", lambda p: 60 * 1024 * 1024)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    calls = []
    sheet.load_large_file = lambda p: calls.append(p)
    sheet._import_file()
    assert calls


def test_fill_release_down_auto_grow(sheet):
    sheet._fill_handle = FakeHandle()
    sheet.model.set_full_dataframe(pd.DataFrame({"A": [1]}))
    sheet.table_view.setModel(sheet.model)
    sheet._fill_start_range = (0, 0, 0, 0)
    sheet._fill_direction = "down"
    sheet._fill_target = 3
    sheet._formula_cells = {}
    sheet._fill_handle_release(FakeEvent())
    assert len(sheet.model._loaded_df) >= 4


def test_fill_release_right_auto_grow(sheet):
    sheet._fill_handle = FakeHandle()
    sheet.model.set_full_dataframe(pd.DataFrame({"A": [1, 2]}))
    sheet.table_view.setModel(sheet.model)
    sheet._fill_start_range = (0, 0, 0, 0)
    sheet._fill_direction = "right"
    sheet._fill_target = 3
    sheet._formula_cells = {}
    sheet._fill_handle_release(FakeEvent())
    assert len(sheet.model._loaded_df.columns) >= 4
