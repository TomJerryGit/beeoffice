# beeoffice/plugins/beewrite_formula.py
"""
蜜写数学公式：LaTeX 输入 + matplotlib 渲染为图片

v5.0.1 修复（P1-11）：
  - 文件头注释拼写修正：beewrite_formula.py → beewrite_formula.py
    （原文件名本身就是 beewrite_，仅注释少了一个 e）
"""

import time
import tempfile
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QDialogButtonBox, QMessageBox, QComboBox,
    QFormLayout
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QImage

# 尝试导入 matplotlib
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False


# ==================== 常用公式模板 ====================
FORMULA_TEMPLATES = {
    "分数": r"\frac{a}{b}",
    "上标": r"x^2",
    "下标": r"x_i",
    "平方根": r"\sqrt{x}",
    "n 次根": r"\sqrt[n]{x}",
    "求和": r"\sum_{i=1}^{n} x_i",
    "连乘": r"\prod_{i=1}^{n} x_i",
    "积分": r"\int_{a}^{b} f(x) dx",
    "极限": r"\lim_{x \to \infty} f(x)",
    "矩阵": r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}",
    "方程组": r"\begin{cases} x + y = 1 \\ x - y = 0 \end{cases}",
    "希腊字母 α": r"\alpha",
    "希腊字母 β": r"\beta",
    "希腊字母 π": r"\pi",
    "无穷": r"\infty",
    "不等于": r"\neq",
    "小于等于": r"\leq",
    "大于等于": r"\geq",
    "属于": r"\in",
    "子集": r"\subset",
    "向量": r"\vec{v}",
    "平均值": r"\bar{x}",
    "微积分": r"\frac{d}{dx} f(x)",
    "偏导": r"\frac{\partial f}{\partial x}",
}


class FormulaDialog(QDialog):
    """公式编辑对话框"""

    def __init__(self, parent=None, initial_latex=""):
        super().__init__(parent)
        self.setWindowTitle("∑ 数学公式")
        self.resize(720, 560)
        self._result_path = None
        self._result_latex = None

        if not HAS_MPL:
            QMessageBox.warning(
                self, "缺少依赖",
                "数学公式需要 matplotlib：\n"
                "pip install matplotlib"
            )
            return

        self._build_ui()

        if initial_latex:
            self._input_edit.setPlainText(initial_latex)
            self._render_preview()

    # ==================== UI ====================
    def _build_ui(self):
        layout = QVBoxLayout(self)

        # 输入区
        layout.addWidget(QLabel("LaTeX 公式（不需要 $ 或 \\[ 包裹）："))

        self._input_edit = QTextEdit()
        self._input_edit.setStyleSheet(
            "QTextEdit{border:1px solid #CCC;border-radius:4px;"
            "padding:8px;font-family:Consolas;font-size:14px;}"
        )
        self._input_edit.setMaximumHeight(80)
        self._input_edit.setPlaceholderText(
            r"例如：\frac{a}{b} 或 \sum_{i=1}^{n} x_i"
        )
        self._input_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._input_edit)

        # 模板区
        tpl_group_layout = QHBoxLayout()

        self._tpl_combo = QComboBox()
        self._tpl_combo.addItem("（选择模板插入）")
        for name in FORMULA_TEMPLATES.keys():
            self._tpl_combo.addItem(name)
        self._tpl_combo.currentTextChanged.connect(
            self._on_template_selected
        )
        tpl_group_layout.addWidget(self._tpl_combo)
        tpl_group_layout.addStretch()

        layout.addLayout(tpl_group_layout)

        # 预览区
        layout.addWidget(QLabel("预览："))

        self._preview_label = QLabel("（输入公式后自动预览）")
        self._preview_label.setAlignment(Qt.AlignCenter)
        self._preview_label.setMinimumHeight(160)
        self._preview_label.setStyleSheet(
            "QLabel{background:#FFF;border:1px solid #DDD;"
            "border-radius:4px;color:#999;padding:8px;}"
        )
        layout.addWidget(self._preview_label, 1)

        # 选项
        opt_layout = QFormLayout()

        self._fontsize_combo = QComboBox()
        self._fontsize_combo.addItems([
            "12", "14", "16", "18", "20", "24", "28"
        ])
        self._fontsize_combo.setCurrentText("18")
        self._fontsize_combo.currentTextChanged.connect(
            self._render_preview
        )
        opt_layout.addRow("字号:", self._fontsize_combo)

        self._color_combo = QComboBox()
        self._color_combo.addItems([
            "黑色", "深蓝", "深红", "深绿"
        ])
        self._color_combo.currentTextChanged.connect(
            self._render_preview
        )
        opt_layout.addRow("颜色:", self._color_combo)

        layout.addLayout(opt_layout)

        # 底部按钮
        btns = QDialogButtonBox()

        btn_render = QPushButton("🔄 刷新预览")
        btn_render.clicked.connect(self._render_preview)
        btns.addButton(btn_render, QDialogButtonBox.ActionRole)

        btn_insert = QPushButton("✅ 插入公式")
        btn_insert.setStyleSheet(
            "QPushButton{background:#FFB300;color:#000;"
            "padding:6px 16px;border:none;border-radius:4px;"
            "font-weight:bold;}"
            "QPushButton:hover{background:#FFA000;}"
        )
        btn_insert.clicked.connect(self._insert_formula)
        btns.addButton(btn_insert, QDialogButtonBox.AcceptRole)

        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btns.addButton(btn_cancel, QDialogButtonBox.RejectRole)

        layout.addWidget(btns)

        # 首次渲染
        self._render_preview()

    # ==================== 事件 ====================
    def _on_text_changed(self):
        """输入变化时延迟刷新（防抖）"""
        from PySide6.QtCore import QTimer
        if hasattr(self, '_render_timer'):
            self._render_timer.stop()
        else:
            self._render_timer = QTimer(self)
            self._render_timer.setSingleShot(True)
            self._render_timer.timeout.connect(self._render_preview)
        self._render_timer.start(400)

    def _on_template_selected(self, text):
        if text == "（选择模板插入）":
            return
        template = FORMULA_TEMPLATES.get(text, "")
        if template:
            cursor = self._input_edit.textCursor()
            cursor.insertText(template)
            self._input_edit.setTextCursor(cursor)

    # ==================== 渲染 ====================
    def _render_preview(self):
        """渲染公式为预览图"""
        latex = self._input_edit.toPlainText().strip()
        if not latex:
            self._preview_label.setText("（输入公式后自动预览）")
            self._preview_label.setPixmap(QPixmap())
            return

        # 清理：去除可能的 $ 或 \[ \]
        latex = self._clean_latex(latex)

        try:
            pixmap = self._render_latex_to_pixmap(latex)
            self._preview_label.setPixmap(pixmap)
            self._preview_label.setText("")
        except Exception as e:
            self._preview_label.setText(
                f"❌ 渲染失败：{e}\n\n请检查 LaTeX 语法"
            )
            self._preview_label.setPixmap(QPixmap())

    @staticmethod
    def _clean_latex(latex):
        """去除常见包裹符"""
        latex = latex.strip()
        # 去除 $...$ 或 $$...$$
        if latex.startswith("$$") and latex.endswith("$$"):
            latex = latex[2:-2]
        elif latex.startswith("$") and latex.endswith("$"):
            latex = latex[1:-1]
        # 去除 \[ \] 或 \( \)
        if latex.startswith(r"\[") and latex.endswith(r"\]"):
            latex = latex[2:-2]
        elif latex.startswith(r"\(") and latex.endswith(r"\)"):
            latex = latex[2:-2]
        return latex.strip()

    def _render_latex_to_pixmap(self, latex, dpi=150):
        """用 matplotlib 渲染 LaTeX 为 QPixmap"""
        fontsize = int(self._fontsize_combo.currentText())

        color_map = {
            "黑色": "#000000",
            "深蓝": "#0D47A1",
            "深红": "#B71C1C",
            "深绿": "#1B5E20",
        }
        color = color_map.get(self._color_combo.currentText(), "#000000")

        # 渲染
        fig = plt.figure(figsize=(6, 1.2), dpi=dpi)
        fig.patch.set_alpha(0)

        text = fig.text(
            0.5, 0.5, f"${latex}$",
            fontsize=fontsize,
            ha="center", va="center",
            color=color,
        )

        # 保存到内存
        import io
        buf = io.BytesIO()
        fig.savefig(
            buf, format="png", dpi=dpi,
            bbox_inches="tight",
            transparent=True,
            pad_inches=0.05
        )
        plt.close(fig)

        # 转 QPixmap
        buf.seek(0)
        qimg = QImage.fromData(buf.getvalue(), "PNG")
        return QPixmap.fromImage(qimg)

    # ==================== 插入 ====================
    def _insert_formula(self):
        latex = self._input_edit.toPlainText().strip()
        if not latex:
            QMessageBox.information(self, "提示", "请输入公式")
            return

        latex = self._clean_latex(latex)

        try:
            # 渲染并保存到临时文件
            fontsize = int(self._fontsize_combo.currentText())
            dpi = 200  # 插入时用更高分辨率
            color_map = {
                "黑色": "#000000",
                "深蓝": "#0D47A1",
                "深红": "#B71C1C",
                "深绿": "#1B5E20",
            }
            color = color_map.get(
                self._color_combo.currentText(), "#000000"
            )

            fig = plt.figure(figsize=(6, 1.2), dpi=dpi)
            fig.patch.set_alpha(0)
            fig.text(
                0.5, 0.5, f"${latex}$",
                fontsize=fontsize,
                ha="center", va="center",
                color=color,
            )

            tmp_dir = Path(tempfile.gettempdir()) / "beeoffice_formulas"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = tmp_dir / f"formula_{int(time.time()*1000)}.png"
            fig.savefig(
                str(tmp_path), format="png", dpi=dpi,
                bbox_inches="tight",
                transparent=True,
                pad_inches=0.1
            )
            plt.close(fig)

            self._result_path = str(tmp_path)
            self._result_latex = latex
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "渲染失败", str(e))

    def get_result_path(self):
        return self._result_path

    def get_latex(self):
        return self._result_latex