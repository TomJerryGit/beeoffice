# beeoffice/plugins/data_insights.py
"""数据工具箱增强：图表推荐 + 一键清洗（纯 pandas 逻辑）。"""
from __future__ import annotations

import pandas as pd

CHART_LABELS = {
    "bar": "柱状图",
    "line": "折线图",
    "pie": "饼图",
    "scatter": "散点图",
    "area": "面积图",
    "radar": "雷达图",
}


def recommend_charts(df: pd.DataFrame) -> list[dict]:
    """根据列类型/基数返回最多 3 个图表建议。"""
    if df is None or df.empty:
        return []
    numeric = list(df.select_dtypes(include="number").columns)
    datetimes = [
        c for c in df.columns
        if pd.api.types.is_datetime64_any_dtype(df[c])
    ]
    categorical = []
    for col in df.columns:
        if col in numeric or col in datetimes:
            continue
        nunique = df[col].nunique(dropna=True)
        if 2 <= nunique <= 12:
            categorical.append((col, nunique))

    recs: list[dict] = []

    def add(kind: str, reason: str, columns: list[str]):
        if any(r["type"] == kind for r in recs):
            return
        recs.append({
            "type": kind,
            "label": CHART_LABELS[kind],
            "reason": reason,
            "columns": columns,
        })

    if datetimes and numeric:
        add("line", "时间列 + 数值列，适合看趋势",
            [datetimes[0], numeric[0]])
    if categorical and numeric:
        col, nunique = categorical[0]
        add("bar", f"分类列「{col}」({nunique} 类) + 数值列，适合对比",
            [col, numeric[0]])
    if len(numeric) >= 2:
        add("scatter", "两个数值列，适合看相关性", numeric[:2])
    elif len(numeric) == 1:
        add("area", "单个数值列，适合看分布/累计", numeric[:1])
    elif categorical:
        add("pie", f"单分类列「{categorical[0][0]}」，适合看占比",
            [categorical[0][0]])
    return recs[:3]


def clean_table(
    df: pd.DataFrame,
    *,
    trim: bool = True,
    drop_empty_rows: bool = True,
    drop_empty_cols: bool = True,
    drop_duplicates: bool = True,
    coerce_numeric: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """一键清洗：空白/空行空列/重复行/数字文本。"""
    report = {
        "rows_before": len(df),
        "cols_before": len(df.columns),
        "trimmed_cells": 0,
        "dropped_empty_rows": 0,
        "dropped_empty_cols": 0,
        "dropped_duplicates": 0,
        "numeric_cols": [],
    }
    out = df.copy()

    if trim:
        for col in out.columns:
            if out[col].dtype == object:
                report["trimmed_cells"] += int(out[col].map(
                    lambda v: isinstance(v, str) and v != v.strip()
                ).sum())
                out[col] = out[col].map(
                    lambda v: v.strip() if isinstance(v, str) else v
                )

    if drop_empty_rows:
        before = len(out)
        out = out.dropna(how="all")
        out = out[~out.apply(
            lambda row: all(
                str(v).strip() == "" or pd.isna(v) for v in row
            ), axis=1
        )]
        report["dropped_empty_rows"] = before - len(out)

    if drop_empty_cols:
        before = len(out.columns)
        out = out.dropna(axis=1, how="all")
        report["dropped_empty_cols"] = before - len(out.columns)

    if drop_duplicates:
        before = len(out)
        out = out.drop_duplicates(ignore_index=True)
        report["dropped_duplicates"] = before - len(out)

    if coerce_numeric:
        for col in out.columns:
            if out[col].dtype != object:
                continue
            series = out[col].dropna()
            if series.empty:
                continue
            converted = pd.to_numeric(series, errors="coerce")
            if converted.notna().mean() >= 0.8:
                out[col] = pd.to_numeric(out[col], errors="coerce")
                report["numeric_cols"].append(str(col))

    out = out.reset_index(drop=True)
    report["rows_after"] = len(out)
    report["cols_after"] = len(out.columns)
    return out, report
