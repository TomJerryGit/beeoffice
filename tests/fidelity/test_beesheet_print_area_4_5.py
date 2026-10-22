# tests/fidelity/test_beesheet_print_area_4_5.py
"""
蜜算打印区域 4.5 回归（2026-10-22）。

- 设置打印区域（选区 / 已用区域）后，打印预览/PDF 只取该矩形；
- 保存 xlsx 后 `ws.print_area` 持久化，重新打开能恢复；
- 取消后恢复"选区 > 已用区域"的原行为。
"""
import pandas as pd
from openpyxl import load_workbook

from beeoffice.plugins.beesheet import BeeSheetView


def _view(qtbot):
    view = BeeSheetView()
    qtbot.addWidget(view)
    view.model.set_full_dataframe(
        pd.DataFrame({
            "A": list(range(1, 21)),
            "B": [f"b{i}" for i in range(1, 21)],
            "C": [i * 2 for i in range(1, 21)],
            "D": [i * 3 for i in range(1, 21)],
            "E": [i * 4 for i in range(1, 21)],
        })
    )
    return view


def test_set_print_area_limits_collect(qtbot):
    view = _view(qtbot)
    assert view._set_print_area((1, 5, 0, 3)) is True
    assert view._print_area == (1, 5, 0, 3)

    data = view._collect_print_data()
    assert len(data["headers"]) == 3
    assert len(data["rows"]) == 4
    assert data["rows"][0][0] == 2          # 视图第 2 行（1 基）
    assert data["rows"][-1][0] == 5


def test_print_area_written_and_read_back(qtbot, tmp_path):
    view = _view(qtbot)
    view._set_print_area((1, 5, 0, 3))
    path = tmp_path / "printarea.xlsx"
    assert view._write_xlsx(str(path)) is True

    wb = load_workbook(path)
    raw = wb.active.print_area
    if isinstance(raw, (list, tuple)):
        raw = raw[0]
    normalized = str(raw).replace("$", "")
    assert "A3" in normalized and "C6" in normalized, raw

    reader = BeeSheetView()
    qtbot.addWidget(reader)
    reader._load_view_styles_from(str(path), "")
    assert reader._print_area == (1, 5, 0, 3)


def test_clear_print_area_restores_default(qtbot):
    view = _view(qtbot)
    view._set_print_area((1, 5, 0, 3))
    view._clear_print_area()
    assert view._print_area is None
    data = view._collect_print_data()
    assert len(data["headers"]) == 5
    assert len(data["rows"]) == 20
