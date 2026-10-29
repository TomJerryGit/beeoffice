# beeoffice/plugins/beeshow_layout_mixin.py
"""
蜜演版式系统 Mixin（任务 2.1）

职责：
  - _show_layout_picker : 弹出「选择版式」对话框
  - _apply_layout       : 把版式骨架写入编辑器
  - _get_layout_css     : 返回版式相关 CSS（渲染时拼入主题 CSS）

设计：
  - 版式定义在 beeshow_constants.LAYOUTS，含 id / name / icon /
    description / skeleton 五个字段
  - skeleton 是 Markdown 骨架，含 {title} / {subtitle} 占位符
  - 版式渲染依赖 markdown 的 md_in_html 扩展（保留内联 HTML）
  - 版式 CSS 与主题 CSS 分离：主题管配色，版式管布局

对标：
  - WPS AIPPT 的「分层精调」——内容/版式/样式三层独立
  - 蜜演：Markdown 内容 + LAYOUTS 版式 + SLIDE_THEMES 主题

依赖：
  - PySide6（QDialog / QVBoxLayout / QHBoxLayout / QLabel /
             QPushButton / QScrollArea / QWidget / QGridLayout）
  - beeshow_constants（LAYOUTS / LAYOUT_CSS）

注意：
  - 不导入其他 beeshow_* Mixin，避免循环依赖
  - _apply_layout 会替换编辑器全文，调用前可考虑加确认
"""

import logging

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QGridLayout, QMessageBox,
)
from PySide6.QtCore import Qt

from beeoffice.plugins.beeshow_constants import LAYOUTS, LAYOUT_CSS


class LayoutMixin:
    """蜜演版式系统 Mixin"""

    # ==================== 版式选择对话框 ====================
    def _show_layout_picker(self):
        """
        弹出「选择版式」对话框。

        布局：3 列网格，每个版式一个卡片按钮（图标 + 名称）。
        点击卡片 → 应用版式到当前幻灯片，关闭对话框。
        """
        dlg = QDialog(self)
        dlg.setWindowTitle("📐 选择版式")
        dlg.resize(640, 480)
        layout = QVBoxLayout(dlg)

        # 顶部提示
        tip = QLabel(
            "💡 选择版式后，当前幻灯片内容会被替换为版式骨架。\n"
            "如需保留原内容，请先复制或另存。"
        )
        tip.setStyleSheet(
            "QLabel{color:#666;font-size:12px;padding:8px;"
            "background:#FFF8E1;border-radius:4px;}"
        )
        tip.setWordWrap(True)
        layout.addWidget(tip)

        # 滚动区 + 网格
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setSpacing(12)

        cols = 3
        for i, (layout_id, meta) in enumerate(LAYOUTS.items()):
            card = self._make_layout_card(layout_id, meta, dlg)
            grid.addWidget(card, i // cols, i % cols)

        scroll.setWidget(grid_widget)
        layout.addWidget(scroll)

        # 底部按钮
        bl = QHBoxLayout()
        bl.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dlg.reject)
        bl.addWidget(close_btn)
        layout.addLayout(bl)

        dlg.exec()

    def _make_layout_card(self, layout_id, meta, parent_dlg) -> QWidget:
        """构造单个版式卡片"""
        card = QPushButton()
        card.setCursor(Qt.PointingHandCursor)
        card.setStyleSheet(
            "QPushButton{"
            "background:#FAFAFA;border:1px solid #DDD;"
            "border-radius:8px;padding:12px 8px;"
            "text-align:center;}"
            "QPushButton:hover{"
            "background:#FFF3E0;border-color:#FFB300;}"
        )
        card.setMinimumHeight(90)

        # 卡片内容：图标 + 名称 + 描述
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(4)

        icon_label = QLabel(meta["icon"])
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("font-size:28px;")
        card_layout.addWidget(icon_label)

        name_label = QLabel(meta["name"])
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet(
            "font-size:13px;font-weight:bold;color:#333;"
        )
        card_layout.addWidget(name_label)

        desc_label = QLabel(meta["description"])
        desc_label.setAlignment(Qt.AlignCenter)
        desc_label.setStyleSheet(
            "font-size:11px;color:#888;"
        )
        desc_label.setWordWrap(True)
        card_layout.addWidget(desc_label)

        card.clicked.connect(
            lambda checked=False, lid=layout_id:
                [self._apply_layout(lid), parent_dlg.accept()]
        )
        return card

    # ==================== 应用版式 ====================
    def _apply_layout(self, layout_id: str):
        """
        把指定版式的骨架写入编辑器。

        参数：
          layout_id : LAYOUTS 中的键（如 "title_only" / "two_column"）

        副作用：
          - 替换 _editor 全文（blockSignals 避免触发解析）
          - 调 _update_preview 刷新预览
        """
        meta = LAYOUTS.get(layout_id)
        if meta is None:
            return

        skeleton = meta["skeleton"]

        # 优化规划 §1.7：应用版式会用骨架替换**整份**演示文稿。原实现没有任何
        # 确认、没有撤销，也不限于当前页——用户误点一次即不可恢复。
        # 现在：内容非空时先确认，并在替换前存一份历史快照。
        try:
            has_content = bool(self._editor.toPlainText().strip())
        except Exception:
            has_content = False

        if has_content:
            reply = QMessageBox.question(
                self,
                "应用版式",
                f"「{meta['name']}」会用版式骨架替换整份演示文稿的现有内容。\n\n"
                "如需保留当前内容，请先取消并另存一份。\n\n确定继续吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        if hasattr(self, "_save_snapshot"):
            try:
                self._save_snapshot(force=True)
            except Exception as e:
                logging.error(f"应用版式前保存快照失败: {e}")

        self._editor.blockSignals(True)
        self._editor.setPlainText(skeleton)
        self._editor.blockSignals(False)

        self._current_slide = 0
        self._update_preview()
        self._set_status(
            f"📐 已应用版式：{meta['name']}", 2000
        )

    # ==================== 版式 CSS ====================
    def _get_layout_css(self) -> str:
        """
        返回版式相关 CSS。

        在 _show_slide / _show_play_slide 中与主题 CSS 拼接使用：
          full_css = theme_css + LAYOUT_CSS
        """
        return LAYOUT_CSS + getattr(self, "_master_css", "")