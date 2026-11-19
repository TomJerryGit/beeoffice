"""Excel 公式深度：数组区间运算/跨表数组。"""
import pandas as pd
from beeoffice.plugins.beesheet_engine import FormulaEngine


class _Model:
    def __init__(self, rows, sheets=None):
        self.rows = rows
        self.sheets = sheets or {}

    def get_value(self, r, c):
        try:
            return self.rows[r][c]
        except (IndexError, TypeError):
            return None

    def _get_sheet_data(self, name):
        return self.sheets.get(name)


def test_array_range_arithmetic():
    m = _Model([[1, 2], [3, 4], [5, 6]])
    assert FormulaEngine.evaluate("=SUM(A1:A3*B1:B3)", m) == 44.0
    assert FormulaEngine.evaluate("=MAX(A1:A3+B1:B3)", m) == 11.0
    assert FormulaEngine.evaluate("=MIN(A1:A3-B1:B3)", m) == -1.0


def test_cross_sheet_array_arithmetic():
    m = _Model([[1]], {"S1": pd.DataFrame({"A": [10, 20], "B": [2, 3]})})
    assert FormulaEngine.evaluate("=SUM(S1!A1:A2*S1!B1:B2)", m) == 80.0
    assert FormulaEngine.evaluate("=AVERAGE(S1!A1:A2+S1!B1:B2)", m) == 17.5
