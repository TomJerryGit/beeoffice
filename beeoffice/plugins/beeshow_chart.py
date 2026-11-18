"""BeeShow 简易图表生成：数据表 -> PNG。"""
from __future__ import annotations

import csv
import io
from pathlib import Path


def parse_chart_series(text: str):
    """支持多系列：首行可写「标签,系列1,系列2」。"""
    rows = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.replace("\t", ",").split(",")]
        if parts:
            rows.append(parts)
    if not rows:
        return [], []
    header = rows[0]
    has_header = len(header) > 2 or any(not _is_number(x) for x in header[1:])
    if has_header:
        names = header[1:]
        data_rows = rows[1:]
    else:
        names = ["系列 1"]
        data_rows = rows
    labels = [r[0] for r in data_rows]
    series = []
    for ci, name in enumerate(names):
        vals = []
        for r in data_rows:
            try:
                vals.append(float(r[ci + 1]))
            except (IndexError, ValueError):
                vals.append(0.0)
        series.append((name, vals))
    return labels, series


def _is_number(value: str) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def parse_chart_data(text: str):
    rows = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.replace("\t", ",").split(",")]
        if parts:
            rows.append(parts)
    if not rows:
        return [], []
    labels = [r[0] for r in rows]
    values = []
    for r in rows:
        try:
            values.append(float(r[1]))
        except (IndexError, ValueError):
            values.append(0.0)
    return labels, values


def render_chart_png(text: str, chart_type: str, out: str) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    labels, series = parse_chart_series(text)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 4))
    if chart_type == "pie":
        vals = series[0][1] if series else []
        ax.pie([abs(v) for v in vals], labels=labels, autopct="%1.1f%%")
    elif chart_type == "line":
        for name, vals in series:
            ax.plot(labels, vals, "o-", label=name)
        ax.tick_params(axis="x", rotation=30)
        ax.legend()
    else:
        import numpy as np
        x = np.arange(len(labels))
        width = 0.8 / max(1, len(series))
        for i, (name, vals) in enumerate(series):
            ax.bar(x + i * width, vals, width=width, label=name)
        ax.set_xticks(x); ax.set_xticklabels(labels, rotation=30)
        ax.legend()
    ax.set_title("BeeShow 图表")
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return str(out)
