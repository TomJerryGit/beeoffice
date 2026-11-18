"""DataFrame 单元格类型安全写入。"""
from __future__ import annotations

import pandas as pd


def ensure_cell_dtype(df, col, value):
    """在写入混合类型前把列转为 object，避免 pandas FutureWarning。"""
    if df is None or col not in df.columns:
        return
    try:
        series = df[col]
        if isinstance(value, str):
            if (pd.api.types.is_numeric_dtype(series)
                    or pd.api.types.is_datetime64_any_dtype(series)
                    or pd.api.types.is_bool_dtype(series)):
                df[col] = series.astype(object)
    except Exception:
        pass


def ensure_column_dtype(df, col, values):
    for value in values:
        ensure_cell_dtype(df, col, value)
