# beeoffice/plugins/beeshow_animation_panel.py
"""蜜演动画面板（阶段 A）：选择器动画列表 + 切换效果库。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from beeoffice.plugins.beeshow_animation import (
    EFFECTS,
    TRANSITIONS,
    AnimationEntry,
    config_dict,
)


class AnimationPanelDialog(QDialog):
    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🎬 动画面板")
        self.resize(760, 480)
        config = config or {}
        self._transition = QComboBox()
        for key, label in TRANSITIONS.items():
            self._transition.addItem(label, key)
        idx = self._transition.findData(config.get("transition", "none"))
        if idx >= 0:
            self._transition.setCurrentIndex(idx)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["目标（CSS 选择器）", "效果", "时长(ms)", "延迟(ms)"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)

        add_btn = QPushButton("＋ 添加")
        add_btn.clicked.connect(lambda: self._add_row())
        del_btn = QPushButton("删除")
        del_btn.clicked.connect(self._remove_row)
        up_btn = QPushButton("上移")
        up_btn.clicked.connect(lambda: self._move(-1))
        down_btn = QPushButton("下移")
        down_btn.clicked.connect(lambda: self._move(1))
        row = QHBoxLayout()
        for btn in (add_btn, del_btn, up_btn, down_btn):
            row.addWidget(btn)
        row.addStretch()

        form = QFormLayout()
        form.addRow("切换效果:", self._transition)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(QLabel("动画按列表顺序依次播放；目标填 CSS 选择器（如 h1、.card、img）。"))
        layout.addWidget(self.table, 1)
        layout.addLayout(row)
        btns = QHBoxLayout()
        ok = QPushButton("应用")
        ok.clicked.connect(self._accept)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(ok)
        btns.addWidget(cancel)
        layout.addLayout(btns)

        for item in config.get("entries", []):
            self._add_row(item)

    def _add_row(self, item=None):
        item = item or {}
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(
            row, 0, QTableWidgetItem(str(item.get("selector", "h1")))
        )
        combo = QComboBox()
        for key, (category, label, _name) in EFFECTS.items():
            combo.addItem(f"{category}·{label}", key)
        idx = combo.findData(item.get("effect", "fade_in"))
        combo.setCurrentIndex(max(0, idx))
        self.table.setCellWidget(row, 1, combo)
        self.table.setItem(
            row, 2, QTableWidgetItem(str(item.get("duration", 500)))
        )
        self.table.setItem(
            row, 3, QTableWidgetItem(str(item.get("delay", 0)))
        )

    def _remove_row(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def _move(self, delta):
        row = self.table.currentRow()
        target = row + delta
        if row < 0 or not 0 <= target < self.table.rowCount():
            return
        for col in range(4):
            widget = self.table.cellWidget(row, col)
            if widget is not None:
                self.table.removeCellWidget(row, col)
                self.table.setCellWidget(target, col, widget)
            else:
                a = self.table.takeItem(row, col)
                b = self.table.takeItem(target, col)
                self.table.setItem(row, col, b)
                self.table.setItem(target, col, a)
        self.table.setCurrentCell(target, 0)

    def _accept(self):
        entries = []
        for row in range(self.table.rowCount()):
            selector = (self.table.item(row, 0).text() or "").strip()
            combo = self.table.cellWidget(row, 1)
            effect = combo.currentData() if combo else "fade_in"
            try:
                duration = int(self.table.item(row, 2).text())
                delay = int(self.table.item(row, 3).text())
                entries.append(AnimationEntry(
                    selector, effect, duration, delay
                ))
            except Exception as e:  # noqa: BLE001
                QMessageBox.warning(self, "动画配置错误", f"第 {row+1} 行：{e}")
                return
        self._config = config_dict(
            self._transition.currentData() or "none", entries
        )
        self.accept()

    def get_config(self):
        return getattr(self, "_config", config_dict("none", []))
