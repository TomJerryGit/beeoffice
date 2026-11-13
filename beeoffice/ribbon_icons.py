"""BeeOffice 内置 SVG 图标集。

不依赖外部图片文件，避免 PyInstaller 资源漏打包。
图标为线性风格，颜色可按主题替换。
"""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QSize
from PySide6.QtGui import QIcon, QPainter, QPixmap, QImage
from PySide6.QtSvg import QSvgRenderer

# 24x24 viewBox，{color} 由 ribbon_icon 替换
_ICONS = {
    "new": '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v5h5"/><path d="M12 12v6M9 15h6"/>',
    "open": '<path d="M3 7h7l2 2h9v10H3z"/><path d="M3 7V5h6l2 2"/>',
    "save": '<path d="M5 3h12l2 2v16H5z"/><path d="M8 3v6h7V3"/><path d="M8 14h8v7H8z"/>',
    "import": '<path d="M12 3v11"/><path d="M8 10l4 4 4-4"/><path d="M4 17v3h16v-3"/>',
    "export": '<path d="M12 14V3"/><path d="M8 7l4-4 4 4"/><path d="M4 17v3h16v-3"/>',
    "paste": '<rect x="6" y="4" width="12" height="17" rx="2"/><path d="M9 4V2h6v2"/><path d="M9 9h6M9 13h6M9 17h4"/>',
    "find": '<circle cx="10" cy="10" r="6"/><path d="M15 15l6 6"/>',
    "sum": '<path d="M6 4h12l-7 8 7 8H6"/>',
    "chart": '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    "pivot": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 3v18"/><path d="M13 13h4v4h-4z"/>',
    "comment": '<path d="M4 4h16v12H9l-5 4z"/><path d="M8 9h8M8 13h6"/>',
    "fill": '<path d="M5 12l7-8 7 8-7 8z"/><path d="M9 13h9"/>',
    "sort": '<path d="M8 4v16M5 7l3-3 3 3"/><path d="M16 20V4M13 17l3 3 3-3"/>',
    "filter": '<path d="M3 4h18l-7 8v7l-4 2v-9z"/>',
    "clean": '<path d="M4 20h16"/><path d="M6 16l7-12 4 2-7 12z"/><path d="M10 8l5 3"/>',
    "validation": '<path d="M12 2l8 3v7c0 5-4 8-8 10-4-2-8-5-8-10V5z"/><path d="M8 12l3 3 5-6"/>',
    "function": '<path d="M5 20l5-16h7"/><path d="M7 12h8"/><path d="M15 10l3 8M18 10l-3 8"/>',
    "book": '<path d="M3 5c2 0 5 1 9 3 4-2 7-3 9-3v14c-2 0-5 1-9 3-4-2-7-3-9-3z"/><path d="M12 8v14"/>',
    "tag": '<path d="M3 3h9l9 9-9 9-9-9z"/><circle cx="8" cy="8" r="1.5"/>',
    "trace": '<circle cx="5" cy="6" r="2"/><circle cx="19" cy="18" r="2"/><path d="M7 6h5a3 3 0 0 1 3 3v6a3 3 0 0 0 3 3"/>',
    "natural": '<path d="M4 4h16v10H9l-5 4z"/><path d="M8 8h8M8 11h5"/><path d="M18 2v3M21 5h-3"/>',
    "freeze": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 10h18"/><path d="M8 14v3M12 14v3M16 14v3"/>',
    "unfreeze": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 10h18"/><path d="M8 14v3M12 14v5M16 14v3"/>',
    "style": '<path d="M12 3a9 9 0 1 0 0 18c2 0 3-1 3-2 0-2-2-2-2-4 0-2 2-3 4-3h2c1-2 1-4-1-6-2-2-4-3-6-3z"/><circle cx="8" cy="9" r="1"/><circle cx="11" cy="6" r="1"/><circle cx="15" cy="7" r="1"/>',
    "compat": '<path d="M4 4h10v10H4z"/><path d="M10 10h10v10H10z"/><path d="M2 18l3 3 5-6"/>',
    "stats": '<path d="M4 20V8M10 20V4M16 20v-9M22 20H2"/><path d="M4 8l6-4 6 7 6-3"/>',
    "insert-row": '<rect x="3" y="3" width="18" height="7" rx="1"/><path d="M12 13v8M8 17h8"/>',
    "delete-row": '<rect x="3" y="3" width="18" height="7" rx="1"/><path d="M8 17h8"/>',
    "insert-col": '<rect x="3" y="3" width="7" height="18" rx="1"/><path d="M17 8v8M13 12h8"/>',
    "delete-col": '<rect x="3" y="3" width="7" height="18" rx="1"/><path d="M13 12h8"/>',
    "merge": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 12h18M12 3v18"/><path d="M9 9l-3 3 3 3M15 9l3 3-3 3"/>',
    "table": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18M15 3v18"/>',
    "undo": '<path d="M9 7L4 12l5 5"/><path d="M4 12h9a6 6 0 0 1 6 6"/>',
    "redo": '<path d="M15 7l5 5-5 5"/><path d="M20 12h-9a6 6 0 0 0-6 6"/>',
    "command": '<rect x="3" y="3" width="18" height="18" rx="4"/><path d="M8 9h8M8 13h5"/>',
}


@lru_cache(maxsize=128)
def ribbon_icon(name: str, color: str = "#374151") -> QIcon:
    """按名称生成 SVG QIcon；未知名称返回空图标。"""
    body = _ICONS.get(name)
    if not body:
        return QIcon()
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
        'viewBox="0 0 24 24">'
        '<g fill="none" stroke="' + color + '" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round">'
        + body + "</g></svg>"
    )
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    image = QImage(QSize(48, 48), QImage.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    return QIcon(QPixmap.fromImage(image))


__all__ = ["ribbon_icon"]
