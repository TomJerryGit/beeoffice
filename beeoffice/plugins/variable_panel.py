# beeoffice/plugins/variable_panel.py
"""
蜜写数据变量面板：显示文档中 {{ 数据源.字段 }} 变量及其实时值

v5.0.1 修复（P1-9）：
  - update_variables 在重建 source_combo 时保留用户当前选择
    原实现每次都 clear() + addItems()，用户选中的源被重置为第一个。
    现在先记录 currentText，重填后若仍存在则恢复，否则回退。
  - blockSignals 避免重建触发 currentTextChanged
"""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel,
                                QListWidget, QListWidgetItem, QPushButton,
                                QHBoxLayout, QComboBox, QFileDialog)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor


class VariablePanel(QWidget):
    """数据变量面板（文档中的 {{ ... }} 占位符实时预览）"""

    refresh_requested = Signal()
    bind_data_source = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(250)
        self.setMaximumWidth(350)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        title = QLabel("📊 数据变量")
        title.setStyleSheet(
            "font-weight: bold; font-size: 14px; color: #FF8F00;"
        )
        layout.addWidget(title)

        sl = QHBoxLayout()
        self.source_combo = QComboBox()
        self.source_combo.setPlaceholderText("选择数据源...")
        sl.addWidget(self.source_combo)
        bind_btn = QPushButton("绑定文件")
        bind_btn.clicked.connect(self._bind_file)
        sl.addWidget(bind_btn)
        layout.addLayout(sl)

        self.var_list = QListWidget()
        self.var_list.setAlternatingRowColors(True)
        layout.addWidget(self.var_list)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.status_label)

        refresh_btn = QPushButton("🔄 刷新变量")
        refresh_btn.clicked.connect(self.refresh_requested.emit)
        layout.addWidget(refresh_btn)

    def update_variables(self, previews, available_sources):
        """
        刷新变量列表和数据源下拉框

        P1-9：保留用户当前选择的数据源
          - 先记录 currentText
          - 重建后若原选择仍存在则恢复，否则回退到第一个
          - 用 blockSignals 避免重建过程触发 currentTextChanged
        """
        # ---------- 变量列表 ----------
        self.var_list.clear()
        for p in previews:
            icon = {"resolved": "✅", "unresolved": "❌",
                    "error": "⚠️"}.get(p["status"], "❓")
            item = QListWidgetItem(
                f"{icon} {p['variable']}\n    → {p['value']}"
            )
            item.setData(Qt.UserRole, p)
            if p["status"] == "unresolved":
                item.setForeground(QColor("#D32F2F"))
            elif p["status"] == "resolved":
                item.setForeground(QColor("#388E3C"))
            self.var_list.addItem(item)

        # ---------- 数据源下拉框（保留用户选择） ----------
        previous = self.source_combo.currentText()
        self.source_combo.blockSignals(True)
        try:
            self.source_combo.clear()
            self.source_combo.addItems(available_sources)
            # 若原选择仍存在，恢复它
            if previous and previous in available_sources:
                self.source_combo.setCurrentText(previous)
        finally:
            self.source_combo.blockSignals(False)

    def _bind_file(self):
        """弹出文件对话框绑定新的数据源"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择数据源文件", "",
            "数据文件 (*.csv *.xlsx *.xls)"
        )
        if path:
            from pathlib import Path
            name = Path(path).stem
            # 若同名已存在，不重复添加
            existing = [self.source_combo.itemText(i)
                        for i in range(self.source_combo.count())]
            if name not in existing:
                self.source_combo.addItem(name)
            self.source_combo.setCurrentText(name)
            self.bind_data_source.emit(name, path)