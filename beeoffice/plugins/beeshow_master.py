"""BeeShow 母版配置：占位符样式、页脚/日期/页码、版式绑定。"""
from __future__ import annotations

import json
import re

MARKER_RE = re.compile(r"<!--\s*beeoffice-master:\s*(\{.*?\})\s*-->", re.DOTALL)

DEFAULT_MASTER = {
    "title_font": "Microsoft YaHei",
    "title_size": 32,
    "title_color": "#E67E22",
    "body_font": "Microsoft YaHei",
    "body_size": 18,
    "body_color": "#333333",
    "footer": "",
    "date": "",
    "show_date": True,
    "show_page": True,
    "layout": "title_only",
}


def parse_master(md: str):
    m = MARKER_RE.search(md or "")
    if not m:
        return dict(DEFAULT_MASTER), md or ""
    try:
        data = json.loads(m.group(1))
        cfg = dict(DEFAULT_MASTER)
        cfg.update(data if isinstance(data, dict) else {})
        return cfg, MARKER_RE.sub("", md or "").strip()
    except Exception:
        return dict(DEFAULT_MASTER), md or ""


def marker_for(cfg) -> str:
    return "<!-- beeoffice-master: " + json.dumps(cfg, ensure_ascii=False, separators=(",", ":")) + " -->"


def master_css(cfg) -> str:
    return (
        f"h1{{font-family:'{cfg.get('title_font')}';font-size:{cfg.get('title_size',32)}px;"
        f"color:{cfg.get('title_color')};}}"
        f"h2,h3,p,li{{font-family:'{cfg.get('body_font')}';"
        f"font-size:{cfg.get('body_size',18)}px;color:{cfg.get('body_color')};}}"
        ".master-footer{position:fixed;bottom:10px;left:18px;font-size:12px;color:#888;}"
        ".master-date{position:fixed;bottom:10px;left:50%;transform:translateX(-50%);"
        "font-size:12px;color:#888;}"
    )


def overlay_html(cfg, page_number: int = 1) -> str:
    parts = []
    if cfg.get("footer"):
        parts.append(f'<div class="master-footer">{cfg["footer"]}</div>')
    if cfg.get("show_date") and cfg.get("date"):
        parts.append(f'<div class="master-date">{cfg["date"]}</div>')
    if cfg.get("show_page"):
        parts.append(f'<div class="master-page">{page_number}</div>')
    return "".join(parts)
