# beeoffice/plugins/beeshow_master_dialog.py
"""S2 蜜演母版设置 MVP：主题/字体/强调色/页脚 Logo。"""
from __future__ import annotations

import base64
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from beeoffice.plugins.beeshow_constants import SLIDE_THEMES


def build_master_css(font_family: str = "", font_size: int = 24,
                     accent: str = "#2196F3", footer: str = "",
                     logo_path: str = "") -> str:
    rules = ["body{font-family:'%s';font-size:%dpx;}" %
             (font_family or "sans-serif", int(font_size))]
    if accent:
        rules.append("h1,h2,h3{color:%s;}" % accent)
    if footer or logo_path:
        bg = ""
        if logo_path and Path(logo_path).is_file():
            data = base64.b64encode(Path(logo_path).read_bytes()).decode()
            suffix = Path(logo_path).suffix.lstrip(".") or "png"
            bg = ("background-image:url(data:image/%s;base64,%s);"
                  "background-repeat:no-repeat;background-size:24px 24px;"
                  "padding-left:28px;" % (suffix, data))
        content = (footer or "").replace('"', '\\"')
        rules.append(
            'body::after{content:"%s";position:fixed;right:24px;bottom:12px;'
            'font-size:12px;color:#888;%s}' % (content, bg)
        )
    return "\n".join(rules)


class BeeShowMasterDialog(QDialog):
    def __init__(self, view, parent=None):
        super().__init__(parent)
        self._view = view
        self.setWindowTitle("🎨 母版设置")
        self.resize(520, 360)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(list(SLIDE_THEMES.keys()))
        current = getattr(view, "_current_theme", "")
        if current in SLIDE_THEMES:
            self.theme_combo.setCurrentText(current)
        self.font_combo = QFontComboBox()
        self.font_size = QSpinBox()
        self.font_size.setRange(12, 72)
        self.font_size.setValue(24)
        self.accent_edit = QLineEdit("#2196F3")
        self.footer_edit = QLineEdit()
        self.footer_edit.setPlaceholderText("页脚文字，如：BeeOffice · 2026")
        self.logo_edit = QLineEdit()
        self.logo_edit.setPlaceholderText("可选：Logo 图片路径")
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse_logo)

        form = QFormLayout()
        form.addRow("主题:", self.theme_combo)
        form.addRow("正文字体:", self.font_combo)
        form.addRow("正文字号:", self.font_size)
        form.addRow("强调色:", self.accent_edit)
        form.addRow("页脚:", self.footer_edit)
        form.addRow("页脚 Logo:", self.logo_edit)
        form.addRow("", browse)
        layout_btn = QPushButton("插入版式…（当前演示）")
        layout_btn.clicked.connect(lambda: view._show_layout_picker())
        apply_btn = QPushButton("应用到全部幻灯片")
        apply_btn.clicked.connect(self._apply)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addWidget(layout_btn)
        buttons.addStretch()
        buttons.addWidget(apply_btn)
        buttons.addWidget(close_btn)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(buttons)

    def _browse_logo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 Logo", "", "图片 (*.png *.jpg *.jpeg)"
        )
        if path:
            self.logo_edit.setText(path)

    def _apply(self):
        if self.theme_combo.currentText() != getattr(
            self._view, "_current_theme", ""
        ):
            try:
                self._view._theme_combo.setCurrentText(
                    self.theme_combo.currentText()
                )
            except Exception:  # noqa: BLE001
                pass
        self._view._master_css = build_master_css(
            self.font_combo.currentFont().family(),
            self.font_size.value(),
            self.accent_edit.text().strip(),
            self.footer_edit.text().strip(),
            self.logo_edit.text().strip(),
        )
        try:
            self._view._show_slide(self._view._current_slide)
        except Exception:  # noqa: BLE001
            pass
        self._view._set_status("母版已应用", 3000)
        self.accept()
