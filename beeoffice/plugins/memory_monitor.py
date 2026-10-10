# beeoffice/plugins/memory_monitor.py
import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar
)
from PySide6.QtCore import QTimer, Qt

class MemoryMonitor(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🐝 内存监控")
        self.setMinimumWidth(380)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        self._history = []
        self._peak = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("📊 内存使用情况")
        title.setStyleSheet("font-weight: bold; font-size: 15px; color: #FF8F00;")
        layout.addWidget(title)

        self.current_label = QLabel("当前: -- MB")
        self.current_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(self.current_label)

        self.peak_label = QLabel("峰值: -- MB")
        self.peak_label.setStyleSheet("color: #888;")
        layout.addWidget(self.peak_label)

        self.progress = QProgressBar()
        self.progress.setMaximum(500)
        self.progress.setFormat("%v MB / 500 MB")
        self.progress.setTextVisible(True)
        layout.addWidget(self.progress)

        self.trend_label = QLabel("趋势: 监测中...")
        self.trend_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.trend_label)

        btn_layout = QHBoxLayout()
        gc_btn = QPushButton("🗑️ 手动垃圾回收")
        gc_btn.clicked.connect(self._manual_gc)
        btn_layout.addWidget(gc_btn)

        reset_btn = QPushButton("🔄 重置统计")
        reset_btn.clicked.connect(self._reset)
        btn_layout.addWidget(reset_btn)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update)
        self._timer.start(1000)
        self._update()

    def _update(self):
        try:
            import psutil
            mb = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
        except ImportError:
            self.current_label.setText("需要安装 psutil")
            return

        if mb > self._peak:
            self._peak = mb

        self._history.append(mb)
        if len(self._history) > 120:
            self._history = self._history[-120:]

        self.current_label.setText(f"当前: {mb:.1f} MB")
        self.peak_label.setText(f"峰值: {self._peak:.1f} MB")
        self.progress.setValue(int(mb))

        # 颜色指示
        if mb > 400:
            self.progress.setStyleSheet(
                "QProgressBar { border: 1px solid #DDD; border-radius: 4px; }"
                "QProgressBar::chunk { background-color: #D32F2F; border-radius: 3px; }"
            )
        elif mb > 200:
            self.progress.setStyleSheet(
                "QProgressBar { border: 1px solid #DDD; border-radius: 4px; }"
                "QProgressBar::chunk { background-color: #F57C00; border-radius: 3px; }"
            )
        else:
            self.progress.setStyleSheet(
                "QProgressBar { border: 1px solid #DDD; border-radius: 4px; }"
                "QProgressBar::chunk { background-color: #4CAF50; border-radius: 3px; }"
            )

        if len(self._history) >= 10:
            diff = sum(self._history[-5:]) / 5 - sum(self._history[:5]) / 5
            if diff > 5:
                self.trend_label.setText(f"⚠️ 趋势: 上升 +{diff:.1f} MB/10s")
                self.trend_label.setStyleSheet("color: #D32F2F; font-size: 12px;")
            elif diff < -5:
                self.trend_label.setText(f"✅ 趋势: 下降 {diff:.1f} MB/10s")
                self.trend_label.setStyleSheet("color: #4CAF50; font-size: 12px;")
            else:
                self.trend_label.setText("✅ 趋势: 稳定")
                self.trend_label.setStyleSheet("color: #666; font-size: 12px;")

    def _manual_gc(self):
        import gc
        gc.collect()
        self._update()

    def _reset(self):
        self._peak = 0
        self._history = []
        # 不调 _update()，避免立刻把 _peak 更新为当前内存。
        # 只清空显示，等下一次定时器触发再刷新。
        self.current_label.setText("当前: -- MB")
        self.peak_label.setText("峰值: 0.0 MB")
        self.trend_label.setText("趋势: 监测中...")
        self.progress.setValue(0)

    def closeEvent(self, event):
        self._timer.stop()
        event.accept()
