"""BeeShow 简易图表生成：数据表 -> PNG。"""
from __future__ import annotations

import csv
import io
from pathlib import Path


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
    labels, values = parse_chart_data(text)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 4))
    if chart_type == "pie":
        ax.pie([abs(v) for v in values], labels=labels, autopct="%1.1f%%")
    elif chart_type == "line":
        ax.plot(labels, values, "o-", color="#1565C0")
        ax.tick_params(axis="x", rotation=30)
    else:
        ax.bar(labels, values, color="#FFB300")
        ax.tick_params(axis="x", rotation=30)
    ax.set_title("BeeShow 图表")
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return str(out)
