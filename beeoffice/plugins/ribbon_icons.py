# beeoffice/plugins/ribbon_icons.py
"""统一 Ribbon 图标工厂（阶段 4）。

不依赖外部 PNG/SVG 资源：用 QPainter 画 24px 线性图标，避免打包漏资源；
颜色跟随当前主题 token（深色主题自动用浅色线条）。
"""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap


def _color() -> str:
    try:
        from beeoffice.theme import Theme
        return Theme.tokens()["text"]
    except Exception:  # noqa: BLE001
        return "#4A4A4A"


def make_icon(name: str, color: str | None = None, size: int = 28) -> QIcon:
    """按名字生成统一线条图标；未知名字返回文件图标。"""
    color = color or _color()
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(color), max(1.4, size / 14))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    s = size
    m = s * 0.18
    w = s - 2 * m
    r = QRectF(m, m, w, w)
    name = (name or "").lower()

    if name == "save":
        p.drawRect(QRectF(m + 2, m + 2, w - 4, w - 4))
        p.drawLine(QPointF(m + 5, m + 3), QPointF(m + 5, m + 10))
        p.drawRect(QRectF(m + w * 0.55, m + 2, w * 0.28, w * 0.22))
        p.drawRect(QRectF(m + 5, m + w - 5, w - 10, w * 0.28))
    elif name == "print":
        p.drawRect(QRectF(m + 2, m + 2, w - 4, w * 0.30))
        p.drawRect(QRectF(m, m + w * 0.34, w, w * 0.36))
        p.drawRect(QRectF(m + w * 0.18, m + w * 0.66, w * 0.64, w * 0.24))
    elif name == "export":
        p.drawRect(QRectF(m + 2, m + w * 0.55, w - 4, w * 0.32))
        p.drawLine(QPointF(s / 2, m + 2), QPointF(s / 2, m + w * 0.52))
        p.drawLine(QPointF(s / 2, m + 2), QPointF(s / 2 - w * 0.18, m + w * 0.20))
        p.drawLine(QPointF(s / 2, m + 2), QPointF(s / 2 + w * 0.18, m + w * 0.20))
    elif name == "undo":
        p.drawArc(QRectF(m + 2, m + 2, w, w), 40 * 16, 220 * 16)
        p.drawLine(QPointF(m + 2, m + w * 0.28), QPointF(m + 2, m + w * 0.58))
        p.drawLine(QPointF(m + 2, m + w * 0.28), QPointF(m + w * 0.30, m + w * 0.28))
    elif name == "redo":
        p.drawArc(QRectF(m + 2, m + 2, w, w), -80 * 16, 220 * 16)
        p.drawLine(QPointF(s - m - 2, m + w * 0.28), QPointF(s - m - 2, m + w * 0.58))
        p.drawLine(QPointF(s - m - 2, m + w * 0.28), QPointF(s - m - w * 0.30, m + w * 0.28))
    elif name == "play":
        p.setBrush(QColor(color))
        p.drawPolygon([QPointF(m + 5, m + 3), QPointF(m + 5, s - m - 3), QPointF(s - m - 5, s / 2)])
    elif name == "table":
        p.drawRect(r)
        p.drawLine(QPointF(s / 2, m), QPointF(s / 2, s - m))
        p.drawLine(QPointF(m, s / 2), QPointF(s - m, s / 2))
    elif name == "image":
        p.drawRect(r)
        p.drawEllipse(QPointF(m + w * 0.28, m + w * 0.28), w * 0.10, w * 0.10)
        p.drawPolyline([QPointF(m + 2, s - m - 4), QPointF(m + w * 0.42, s - m - w * 0.38),
                        QPointF(m + w * 0.62, s - m - w * 0.18), QPointF(s - m - 3, s - m - 5)])
    elif name == "link":
        p.drawEllipse(QRectF(m + 1, m + w * 0.22, w * 0.48, w * 0.48))
        p.drawEllipse(QRectF(m + w * 0.50, m + w * 0.22, w * 0.48, w * 0.48))
        p.drawLine(QPointF(m + w * 0.35, s / 2), QPointF(m + w * 0.66, s / 2))
    elif name == "toc":
        for i in range(3):
            y = m + 4 + i * w * 0.30
            p.drawLine(QPointF(m + 5, y), QPointF(s - m - 5, y))
            p.drawPoint(QPointF(m + 2, y))
    elif name == "comment":
        p.drawRoundedRect(QRectF(m + 1, m + 1, w - 2, w * 0.62), 3, 3)
        p.drawPolyline([QPointF(m + w * 0.28, m + w * 0.62),
                        QPointF(m + w * 0.22, s - m - 2),
                        QPointF(m + w * 0.50, m + w * 0.62)])
    elif name == "track":
        p.drawLine(QPointF(m + 1, s - m - 4), QPointF(s - m - 4, m + 4))
        p.drawLine(QPointF(s - m - 10, s - m - 4), QPointF(s - m - 4, s - m - 10))
        p.drawLine(QPointF(m + 1, s - m - 4), QPointF(s - m - 4, m + 4))
    elif name == "search":
        p.drawEllipse(QRectF(m + 1, m + 1, w * 0.64, w * 0.64))
        p.drawLine(QPointF(m + w * 0.68, m + w * 0.68), QPointF(s - m - 1, s - m - 1))
    elif name == "view":
        p.drawEllipse(QRectF(m, m + w * 0.22, w, w * 0.56))
        p.drawEllipse(QRectF(s / 2 - w * 0.14, s / 2 - w * 0.14, w * 0.28, w * 0.28))
    elif name == "page":
        p.drawRect(QRectF(m + w * 0.18, m + 1, w * 0.64, w - 2))
        for i in range(3):
            y = m + 6 + i * w * 0.22
            p.drawLine(QPointF(m + w * 0.30, y), QPointF(s - m - w * 0.28, y))
    elif name == "formula":
        p.drawText(r, Qt.AlignCenter, "fx")
    elif name == "data":
        for i, h in enumerate((0.35, 0.60, 0.45, 0.75)):
            x = m + 2 + i * w * 0.23
            p.drawLine(QPointF(x, s - m - 3), QPointF(x, s - m - 3 - w * h))
    elif name == "home":
        p.drawPolyline([QPointF(m, s / 2), QPointF(s / 2, m + 2), QPointF(s - m, s / 2)])
        p.drawRect(QRectF(m + 5, s / 2, w - 10, w * 0.40))
    elif name == "insert":
        p.drawLine(QPointF(s / 2, m + 2), QPointF(s / 2, s - m - 2))
        p.drawLine(QPointF(m + 2, s / 2), QPointF(s - m - 2, s / 2))
    else:
        p.drawRect(r)
        p.drawLine(QPointF(m + 2, s / 2), QPointF(s - m - 2, s / 2))

    p.end()
    return QIcon(pm)
