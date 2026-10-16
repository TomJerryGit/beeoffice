from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PySide6.QtCore import Qt

def create_app_icon():
    pixmap = QPixmap(256, 256)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor("#FFB300"))
    painter.setPen(QColor("#E65100"))
    painter.drawEllipse(28, 28, 200, 200)
    font = QFont("Segoe UI Emoji", 80)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "🐝")
    painter.end()
    return QIcon(pixmap)
