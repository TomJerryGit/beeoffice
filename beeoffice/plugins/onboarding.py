# beeoffice/plugins/onboarding.py
from PySide6.QtWidgets import QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout
from PySide6.QtCore import Qt, QRect, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from beeoffice.i18n import tr


class OnboardingStep:
    def __init__(self, target_rect, title, description, position="bottom"):
        self.target_rect = target_rect
        self.title = title
        self.description = description
        self.position = position


class OnboardingOverlay(QWidget):
    finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(parent.rect() if parent else QRect(0, 0, 800, 600))
        # 浮层必须能接收键盘事件，否则 Esc 无效
        self.setFocusPolicy(Qt.StrongFocus)
        self._steps = []
        self._current_step = 0
        self._tip_widget = None

    # ==================== 退出通道（P0：曾把用户卡死） ====================
    def showEvent(self, event):
        super().showEvent(event)
        self.setFocus(Qt.OtherFocusReason)
        self.raise_()
        self.activateWindow()

    def keyPressEvent(self, event):
        """Esc / 回车直接退出引导。"""
        if event.key() in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter):
            self._skip_all()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        """点击遮罩任意位置 = 下一步（最后一步即结束），始终有出路。"""
        self._next_step()
        event.accept()

    def set_steps(self, steps):
        self._steps = steps
        self._current_step = 0
        self._show_current_step()

    def _show_current_step(self):
        if self._tip_widget:
            self._tip_widget.deleteLater()
            self._tip_widget = None
        if self._current_step >= len(self._steps):
            self.finished.emit()
            self.close()
            return
        step = self._steps[self._current_step]
        self._create_tip(step)
        self.update()

    def _create_tip(self, step):
        self._tip_widget = QWidget(self)
        self._tip_widget.setStyleSheet("QWidget{background:#FFF;border:2px solid #FFB300;border-radius:12px}")
        layout = QVBoxLayout(self._tip_widget)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)
        step_label = QLabel(f"第 {self._current_step + 1}/{len(self._steps)} 步")
        step_label.setStyleSheet("color:#FF8F00;font-size:11px;font-weight:bold")
        layout.addWidget(step_label)
        title_label = QLabel(step.title)
        title_label.setStyleSheet("font-size:15px;font-weight:bold;color:#333")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)
        desc_label = QLabel(step.description)
        desc_label.setStyleSheet("font-size:12px;color:#666")
        desc_label.setWordWrap(True)
        desc_label.setMaximumWidth(280)
        layout.addWidget(desc_label)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        skip_btn = QPushButton(tr("auto.onboarding.31a98593", "跳过"))
        skip_btn.setStyleSheet("QPushButton{background:transparent;border:none;color:#999;font-size:12px}QPushButton:hover{color:#666}")
        skip_btn.clicked.connect(self._skip_all)
        btn_layout.addWidget(skip_btn)
        next_text = "知道了" if self._current_step == len(self._steps) - 1 else "下一步"
        next_btn = QPushButton(next_text)
        next_btn.setStyleSheet("QPushButton{background:#FFB300;color:#000;border:none;padding:8px 18px;border-radius:6px;font-weight:bold}QPushButton:hover{background:#FFA000}")
        next_btn.clicked.connect(self._next_step)
        btn_layout.addWidget(next_btn)
        layout.addLayout(btn_layout)
        target = step.target_rect
        tip_w = 320
        # 关键：布局尚未激活时 sizeHint() 可能为 0，
        # 导致卡片被设成 0 高而完全看不见（曾表现为"只有黑框、点不动"）。
        self._tip_widget.ensurePolished()
        if self._tip_widget.layout() is not None:
            self._tip_widget.layout().activate()
        tip_h = max(140, self._tip_widget.sizeHint().height())
        if step.position == "bottom":
            x, y = target.center().x() - tip_w // 2, target.bottom() + 12
        elif step.position == "top":
            x, y = target.center().x() - tip_w // 2, target.top() - tip_h - 12
        elif step.position == "right":
            x, y = target.right() + 12, target.center().y() - tip_h // 2
        else:
            x, y = target.left() - tip_w - 12, target.center().y() - tip_h // 2
        x = max(10, min(x, self.width() - tip_w - 10))
        y = max(10, min(y, self.height() - tip_h - 10))
        self._tip_widget.setGeometry(x, y, tip_w, tip_h)
        self._tip_widget.show()
        self._tip_widget.raise_()

    def _next_step(self):
        self._current_step += 1
        self._show_current_step()

    def _skip_all(self):
        self._current_step = len(self._steps)
        self._show_current_step()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))
        if self._current_step < len(self._steps):
            target = self._steps[self._current_step].target_rect
            # 不再用 CompositionMode_Clear "挖洞"：
            # 在半透明子窗口上挖洞，某些平台会渲染成实心黑块
            # （用户看到的就是一个黑底橙框）。改为只描边。
            pen = QPen(QColor("#FFB300"), 3)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(target.adjusted(-4, -4, 4, 4), 8, 8)


def get_default_steps(parent):
    if not parent: return []
    steps = []
    steps.append(OnboardingStep(
        QRect(parent.width() // 2 - 100, 60, 200, 40),
        "🐝 命令面板", "按 Ctrl+Shift+P 打开命令面板。\n搜索并执行所有功能。", "bottom"
    ))
    steps.append(OnboardingStep(
        QRect(10, 5, 80, 30),
        "📂 快速开始", "点击「文件」菜单新建文档或表格。\n也可以拖拽文件到窗口。", "right"
    ))
    steps.append(OnboardingStep(
        QRect(parent.width() // 3, 5, parent.width() // 3, 35),
        "📑 多标签页", "同时打开多个文档和表格。\n蜜算分析数据，蜜写撰写报告。", "bottom"
    ))
    steps.append(OnboardingStep(
        QRect(parent.width() // 2 - 80, parent.height() // 2 - 20, 160, 40),
        "🚀 开始使用", "1. 新建蜜算表格，导入数据\n2. 新建蜜写文档，选择模板\n3. 关联数据源，一键生成报告\n\n百花寻觅，酿得甜蜜！🐝", "bottom"
    ))
    return steps
