# tests/test_p2_regression/test_p1_01_column_names.py
"""P1-1 回归：超过 26 列时列名正确"""
from beeoffice.plugins.beesheet_model import SheetDataModel


def test_30_columns_no_garbage(qapp):
    model = SheetDataModel()
    model._init_empty(rows=10, cols=30)
    cols = list(model._full_df.columns)
    assert cols[0] == "A"
    assert cols[25] == "Z"
    assert cols[26] == "AA"
    assert cols[29] == "AD"
    for c in cols:
        assert c.isalpha()


def test_52_columns(qapp):
    model = SheetDataModel()
    model._init_empty(rows=10, cols=52)
    cols = list(model._full_df.columns)
    assert cols[51] == "AZ"
