"""BeeShow 原生图表对象：持久化标记 + PPTX 原生 Chart 导出。"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path

MARKER_RE = re.compile(r"<!--\s*beeoffice-chartobj:\s*(\{.*?\})\s*-->", re.DOTALL)


def parse_charts(md: str):
    m = MARKER_RE.search(md or "")
    if not m:
        return [], md or ""
    try:
        data = json.loads(m.group(1))
        return list(data.get("charts", [])), MARKER_RE.sub("", md or "").strip()
    except Exception:
        return [], md or ""


def marker_for(charts) -> str:
    return "<!-- beeoffice-chartobj: " + json.dumps(
        {"charts": list(charts)}, ensure_ascii=False, separators=(",", ":")
    ) + " -->"


def chart_html(charts) -> str:
    from io import BytesIO
    from beeoffice.plugins.beeshow_chart import render_chart_png
    parts = []
    if isinstance(charts, dict):
        charts = [charts]
    for c in charts or []:
        data = str(c.get("data", ""))
        kind = str(c.get("type", "bar"))
        try:
            tmp = Path(__import__("tempfile").gettempdir()) / "beeoffice_charts" / "preview.png"
            render_chart_png(data, kind, str(tmp))
            b64 = base64.b64encode(tmp.read_bytes()).decode("ascii")
            parts.append(
                '<img class="native-chart" style="max-width:80%;max-height:55%;" '
                f'src="data:image/png;base64,{b64}">'
            )
        except Exception:
            parts.append('<div class="native-chart">图表</div>')
    return "".join(parts)


def apply_native_charts(pptx_path: str, configs) -> int:
    from pptx import Presentation
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE
    from pptx.util import Inches

    prs = Presentation(pptx_path)
    count = 0
    for slide, charts in zip(prs.slides, configs or []):
        if isinstance(charts, dict):
            charts = [charts]
        for i, cfg in enumerate(charts or []):
            from beeoffice.plugins.beeshow_chart import parse_chart_data
            labels, values = parse_chart_data(str(cfg.get("data", "")))
            if not labels:
                continue
            kind = str(cfg.get("type", "bar"))
            xl = {"line": XL_CHART_TYPE.LINE, "pie": XL_CHART_TYPE.PIE}.get(
                kind, XL_CHART_TYPE.COLUMN_CLUSTERED
            )
            data = CategoryChartData()
            data.categories = labels
            data.add_series(cfg.get("title", "系列 1"), values)
            left = Inches(1.0 + i * 0.2)
            top = Inches(1.5 + i * 0.2)
            width = Inches(8.0)
            height = Inches(4.5)
            gf = slide.shapes.add_chart(xl, left, top, width, height, data)
            gf.chart.has_title = True
            gf.chart.chart_title.text_frame.text = cfg.get("title", "BeeShow 图表")
            count += 1
    prs.save(pptx_path)
    return count
