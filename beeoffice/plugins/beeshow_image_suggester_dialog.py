# beeoffice/plugins/beeshow_image_suggester_dialog.py
"""
蜜演配图选择对话框（任务 1.3）

职责：
  - 展示候选图（缩略图网格）
  - 用户点击选中，双击确定
  - 显示图片来源和作者

依赖：
  - PySide6（QDialog / QVBoxLayout / QHBoxLayout / QLabel / QPushButton /
             QScrollArea / QWidget / QGridLayout）
  - PySide6.QtCore（Qt / QSize）
  - PySide6.QtGui（QPixmap / QImage）
  - urllib（下载缩略图）
"""

import logging
import urllib.request
from io import BytesIO

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QGridLayout,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from beeoffice.i18n import tr


class ImageSuggesterDialog(QDialog):
    """配图选择对话框"""

    def __init__(self, results: list, parent=None):
        """
        :param results: [{"url", "thumb", "source", "author", "query"}]
        :param parent: 父窗口
        """
        super().__init__(parent)
        self.setWindowTitle(tr("auto.beeshow_image_suggester_dialog.bd00cc20", "🖼️ 选择配图"))
        self.resize(800, 600)

        self._results = results
        self._selected = None
        self._cards = []

        layout = QVBoxLayout(self)

        # 顶部提示
        tip = QLabel(
            f"💡 根据当前页内容找到 {len(results)} 张候选图。\n"
            f"单击选中，双击直接插入。"
        )
        tip.setStyleSheet(
            "QLabel{color:#666;font-size:12px;padding:8px;"
            "background:#FFF8E1;border-radius:4px;}"
        )
        tip.setWordWrap(True)
        layout.addWidget(tip)

        # 滚动区
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setSpacing(12)

        cols = 3
        for i, item in enumerate(results):
            card = self._make_card(item, i)
            grid.addWidget(card, i // cols, i % cols)

        scroll.setWidget(grid_widget)
        layout.addWidget(scroll)

        # 底部按钮
        bl = QHBoxLayout()
        bl.addStretch()

        self._insert_btn = QPushButton(tr("auto.beeshow_image_suggester_dialog.22f154d2", "✅ 插入选中图"))
        self._insert_btn.setEnabled(False)
        self._insert_btn.setStyleSheet(
            "QPushButton{background:#FFB300;color:#000;"
            "padding:6px 16px;border:none;border-radius:4px;"
            "font-weight:bold;}"
            "QPushButton:hover{background:#FFA000;}"
            "QPushButton:disabled{background:#EEE;color:#999;}"
        )
        self._insert_btn.clicked.connect(self._on_insert)
        bl.addWidget(self._insert_btn)

        cancel_btn = QPushButton(tr("auto.beeshow_image_suggester_dialog.4d0b4688", "取消"))
        cancel_btn.clicked.connect(self.reject)
        bl.addWidget(cancel_btn)

        layout.addLayout(bl)

    # ==================== 卡片 ====================
    def _make_card(self, item: dict, index: int) -> QWidget:
        """构造单张图片卡片"""
        card = QPushButton()
        card.setCursor(Qt.PointingHandCursor)
        card.setCheckable(True)
        card.setStyleSheet(
            "QPushButton{"
            "background:#FAFAFA;border:2px solid #DDD;"
            "border-radius:6px;padding:8px;text-align:center;}"
            "QPushButton:hover{background:#FFF3E0;border-color:#FFB300;}"
            "QPushButton:checked{background:#FFF3E0;border-color:#FFB300;}"
        )
        card.setMinimumHeight(200)

        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(4)

        # 缩略图
        thumb_label = QLabel(tr("auto.beeshow_image_suggester_dialog.514c33af", "加载中..."))
        thumb_label.setAlignment(Qt.AlignCenter)
        thumb_label.setMinimumHeight(140)
        thumb_label.setStyleSheet(
            "QLabel{background:#EEE;color:#999;font-size:12px;}"
        )
        card_layout.addWidget(thumb_label)

        # 异步加载缩略图
        pixmap = self._load_thumbnail(item.get("thumb", ""))
        if pixmap is not None:
            thumb_label.setPixmap(
                pixmap.scaled(
                    200, 140,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )
            thumb_label.setText("")
        else:
            thumb_label.setText(tr("auto.beeshow_image_suggester_dialog.e8e2e471", "（无法加载）"))

        # 来源信息
        source_label = QLabel(
            f"{item.get('source', '?')} · {item.get('author', '')}"
        )
        source_label.setStyleSheet("font-size:11px;color:#888;")
        source_label.setWordWrap(True)
        card_layout.addWidget(source_label)

        # 点击事件
        card.clicked.connect(
            lambda checked, i=index: self._on_card_clicked(i)
        )
        card.mouseDoubleClickEvent = (
            lambda e, i=index: self._on_card_double_clicked(i)
        )

        self._cards.append(card)
        return card

    def _load_thumbnail(self, url: str):
        """下载缩略图"""
        if not url:
            return None
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "BeeOffice/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            return pixmap if not pixmap.isNull() else None
        except Exception as e:
            logging.debug(f"加载缩略图失败 {url}：{e}")
            return None

    # ==================== 交互 ====================
    def _on_card_clicked(self, index: int):
        """单击选中"""
        # 取消其他选中
        for i, card in enumerate(self._cards):
            if i != index:
                card.setChecked(False)
        self._cards[index].setChecked(True)
        self._selected = index
        self._insert_btn.setEnabled(True)

    def _on_card_double_clicked(self, index: int):
        """双击直接插入"""
        self._selected = index
        self._on_insert()

    def _on_insert(self):
        """点击"插入"按钮"""
        if self._selected is None:
            return
        self.accept()

    def get_selected(self) -> dict:
        """返回选中的图片信息"""
        if self._selected is None:
            return {}
        return self._results[self._selected]