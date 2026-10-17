# tests/helpers/qt_helpers.py
"""Qt 相关的小工具：测试图片生成、事件循环 drain。"""
import time
from pathlib import Path


def make_test_image(path, w=200, h=100, color="red"):
    """生成一张测试图片，返回 Path。"""
    from PySide6.QtGui import QImage, QColor
    path = Path(path)
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(QColor(color))
    assert img.save(str(path)), f"图片写入失败: {path}"
    return path


def drain_event_loop(rounds=5, delay=0.05):
    """跑几轮事件循环 + DeferredDelete，让 pending deleteLater 执行。"""
    from PySide6.QtCore import QEvent, QCoreApplication
    for _ in range(rounds):
        QCoreApplication.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        time.sleep(delay)
        QCoreApplication.processEvents()
