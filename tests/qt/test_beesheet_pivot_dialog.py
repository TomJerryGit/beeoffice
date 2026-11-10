"""BeeSheet 数据透视表配置对话框补测。"""
import pandas as pd

from beeoffice.plugins.beesheet_dialogs import PivotTableDialog
from PySide6.QtCore import Qt


def test_pivot_build_success(qtbot):
    df = pd.DataFrame({"城市": ["北京", "上海", "北京"], "金额": [1, 2, 3]})
    dlg = PivotTableDialog(df)
    qtbot.addWidget(dlg)
    pivot, err = dlg._build_pivot({
        "rows": ["城市"], "cols": [], "values": ["金额"],
        "aggfunc": "sum", "margins": False,
    })
    assert err is None
    assert pivot is not None
    assert len(pivot) == 2


def test_pivot_build_no_fields(qtbot):
    df = pd.DataFrame({"城市": ["北京"], "金额": [1]})
    dlg = PivotTableDialog(df)
    qtbot.addWidget(dlg)
    pivot, err = dlg._build_pivot({
        "rows": [], "cols": [], "values": ["金额"],
        "aggfunc": "sum", "margins": False,
    })
    assert pivot is None
    assert "必须" in err


def test_pivot_build_invalid_agg(qtbot):
    df = pd.DataFrame({"城市": ["北京"], "金额": [1]})
    dlg = PivotTableDialog(df)
    qtbot.addWidget(dlg)
    pivot, err = dlg._build_pivot({
        "rows": ["城市"], "cols": [], "values": ["金额"],
        "aggfunc": "not-a-func", "margins": False,
    })
    assert pivot is None and err


def test_get_config(qtbot):
    df = pd.DataFrame({"城市": ["北京", "上海"], "金额": [1, 2]})
    dlg = PivotTableDialog(df)
    qtbot.addWidget(dlg)
    # 选中行字段和值字段
    dlg.row_list.item(0).setSelected(True)
    dlg.col_list.clearSelection()
    for i in range(dlg.value_list.count()):
        if dlg.value_list.item(i).text() == "金额":
            dlg.value_list.item(i).setSelected(True)
    config = dlg._get_config()
    assert config is not None
    assert "城市" in config["rows"]
    assert "金额" in config["values"]
