# beeoffice/plugins/beewrite_page_extras.py
"""
蜜写水印 + 页码：只在导出 PDF / HTML 时生效
编辑视图不显示（Qt 限制）

v5.0.1 修复（P1-11）：
  - 文件头注释拼写修正：beewrite_page_extras.py → beewrite_page_extras.py
    （原文件名本身就是 beewrite_，仅注释少了一个 e）
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLabel, QLineEdit,
    QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox,
    QDialogButtonBox, QColorDialog, QPushButton
)
from PySide6.QtGui import QColor


class WatermarkDialog(QDialog):
    """水印设置对话框"""

    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("💧 水印设置")
        self.resize(420, 340)

        config = config or {}
        self._color = QColor(config.get("color", "#CCCCCC"))

        layout = QVBoxLayout(self)
        form = QFormLayout()

        # 水印文字
        self._text_edit = QLineEdit(
            config.get("text", "内部资料")
        )
        self._text_edit.setPlaceholderText("输入水印文字")
        form.addRow("水印文字:", self._text_edit)

        # 字号
        self._fontsize_spin = QSpinBox()
        self._fontsize_spin.setRange(20, 200)
        self._fontsize_spin.setValue(config.get("fontsize", 80))
        self._fontsize_spin.setSuffix(" px")
        form.addRow("字号:", self._fontsize_spin)

        # 颜色
        self._color_btn = QPushButton("选择颜色")
        self._color_btn.setStyleSheet(
            f"QPushButton{{background:{self._color.name()};"
            f"padding:6px;border:1px solid #CCC;border-radius:3px;}}"
        )
        self._color_btn.clicked.connect(self._pick_color)
        form.addRow("颜色:", self._color_btn)

        # 不透明度
        self._opacity_spin = QDoubleSpinBox()
        self._opacity_spin.setRange(0.05, 1.0)
        self._opacity_spin.setSingleStep(0.05)
        self._opacity_spin.setValue(config.get("opacity", 0.15))
        self._opacity_spin.setDecimals(2)
        form.addRow("不透明度:", self._opacity_spin)

        # 旋转角度
        self._angle_spin = QSpinBox()
        self._angle_spin.setRange(-90, 90)
        self._angle_spin.setValue(config.get("angle", -45))
        self._angle_spin.setSuffix("°")
        form.addRow("旋转角度:", self._angle_spin)

        # 应用位置
        self._position_combo = QComboBox()
        self._position_combo.addItems([
            "居中", "平铺（重复）"
        ])
        form.addRow("位置:", self._position_combo)

        layout.addLayout(form)

        # 提示
        tip = QLabel(
            "💡 水印只在导出 PDF / HTML 时生效。\n"
            "编辑视图不显示水印（Qt 限制）。"
        )
        tip.setStyleSheet(
            "QLabel{color:#666;font-size:11px;padding:8px;"
            "background:#FFF8E1;border-radius:4px;}"
        )
        tip.setWordWrap(True)
        layout.addWidget(tip)

        # 按钮
        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )

        btn_clear = QPushButton("清除水印")
        btn_clear.clicked.connect(self._clear)
        btns.addButton(btn_clear, QDialogButtonBox.ActionRole)

        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self._cleared = False

    def _pick_color(self):
        c = QColorDialog.getColor(self._color)
        if c.isValid():
            self._color = c
            self._color_btn.setStyleSheet(
                f"QPushButton{{background:{c.name()};"
                f"padding:6px;border:1px solid #CCC;"
                f"border-radius:3px;}}"
            )

    def _clear(self):
        self._cleared = True
        self.accept()

    def get_config(self):
        """返回配置，None 表示清除水印"""
        if self._cleared:
            return None
        text = self._text_edit.text().strip()
        if not text:
            return None
        return {
            "text": text,
            "fontsize": self._fontsize_spin.value(),
            "color": self._color.name(),
            "opacity": self._opacity_spin.value(),
            "angle": self._angle_spin.value(),
            "tile": self._position_combo.currentText().startswith("平铺"),
        }


class PageNumberDialog(QDialog):
    """页码设置对话框"""

    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📄 页码设置")
        self.resize(400, 280)

        config = config or {}
        layout = QVBoxLayout(self)
        form = QFormLayout()

        # 启用
        self._enable_check = QCheckBox("在导出 PDF 时添加页码")
        self._enable_check.setChecked(config.get("enabled", False))
        form.addRow(self._enable_check)

        # 位置
        self._position_combo = QComboBox()
        self._position_combo.addItems([
            "底部居中", "底部右侧", "底部左侧",
            "顶部居中", "顶部右侧", "顶部左侧",
        ])
        pos = config.get("position", "底部居中")
        idx = self._position_combo.findText(pos)
        if idx >= 0:
            self._position_combo.setCurrentIndex(idx)
        form.addRow("位置:", self._position_combo)

        # 格式
        self._format_combo = QComboBox()
        self._format_combo.addItems([
            "1", "第 1 页", "第 1 页 / 共 N 页",
            "1 / N", "Page 1", "Page 1 of N",
        ])
        fmt = config.get("format", "第 1 页 / 共 N 页")
        idx = self._format_combo.findText(fmt)
        if idx >= 0:
            self._format_combo.setCurrentIndex(idx)
        form.addRow("格式:", self._format_combo)

        # 数字格式（5.3：DOCX 页码域也支持罗马数字）
        self._num_format_combo = QComboBox()
        self._num_format_combo.addItem("阿拉伯数字 (1,2,3)", "arabic")
        self._num_format_combo.addItem("小写罗马 (i,ii,iii)", "lowerRoman")
        self._num_format_combo.addItem("大写罗马 (I,II,III)", "upperRoman")
        idx2 = self._num_format_combo.findData(
            config.get("num_format", "arabic")
        )
        if idx2 >= 0:
            self._num_format_combo.setCurrentIndex(idx2)
        form.addRow("数字格式:", self._num_format_combo)

        # 起始页码
        self._start_spin = QSpinBox()
        self._start_spin.setRange(1, 9999)
        self._start_spin.setValue(config.get("start", 1))
        form.addRow("起始页码:", self._start_spin)

        # 字号
        self._fontsize_spin = QSpinBox()
        self._fontsize_spin.setRange(8, 24)
        self._fontsize_spin.setValue(config.get("fontsize", 10))
        self._fontsize_spin.setSuffix(" pt")
        form.addRow("字号:", self._fontsize_spin)

        layout.addLayout(form)

        # 提示
        tip = QLabel(
            "💡 页码用于导出 DOCX/PDF：DOCX 写入 Word 页码域（可更新），"
            "PDF 通过 CSS @page 规则。"
        )
        tip.setStyleSheet(
            "QLabel{color:#666;font-size:11px;padding:8px;"
            "background:#FFF8E1;border-radius:4px;}"
        )
        tip.setWordWrap(True)
        layout.addWidget(tip)

        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_config(self):
        return {
            "enabled": self._enable_check.isChecked(),
            "position": self._position_combo.currentText(),
            "format": self._format_combo.currentText(),
            "start": self._start_spin.value(),
            "fontsize": self._fontsize_spin.value(),
            "num_format": self._num_format_combo.currentData() or "arabic",
        }


class HeaderFooterDialog(QDialog):
    """页眉/页脚文字编辑（5.1，2026-10-22）。"""

    def __init__(self, header="", footer="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("📋 页眉页脚")
        self.resize(520, 260)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._header_edit = QLineEdit(header or "")
        self._header_edit.setPlaceholderText("页眉文字，留空表示不写页眉")
        self._footer_edit = QLineEdit(footer or "")
        self._footer_edit.setPlaceholderText("页脚文字，留空表示不写页脚")
        form.addRow("页眉:", self._header_edit)
        form.addRow("页脚:", self._footer_edit)
        layout.addLayout(form)
        tip = QLabel(
            "💡 页眉页脚会写入 DOCX 导出件；分节文档只改第 1 节，"
            "其余节保持原样。页码请用「📄 页码」设置。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("QLabel{color:#666;font-size:11px;padding:8px;}")
        layout.addWidget(tip)
        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def values(self):
        return (
            self._header_edit.text().strip(),
            self._footer_edit.text().strip(),
        )


# ==================== 导出时注入 CSS ====================
def build_watermark_html(watermark_config):
    """生成水印 HTML 片段"""
    if not watermark_config:
        return ""
    text = watermark_config.get("text", "")
    if not text:
        return ""
    fs = watermark_config.get("fontsize", 80)
    color = watermark_config.get("color", "#CCCCCC")
    opacity = watermark_config.get("opacity", 0.15)
    angle = watermark_config.get("angle", -45)
    tile = watermark_config.get("tile", False)

    if tile:
        # 平铺水印（背景重复）
        return f"""
<style>
body {{
    background-image: url("data:image/svg+xml;utf8,\
<svg xmlns='http://www.w3.org/2000/svg' width='300' height='200'>\
<text x='150' y='100' font-size='{fs//3}' fill='{color}' \
fill-opacity='{opacity}' transform='rotate({angle} 150 100)' \
text-anchor='middle' dominant-baseline='middle'>{text}</text>\
</svg>");
    background-repeat: repeat;
    background-attachment: fixed;
}}
</style>
"""
    else:
        # 单个居中水印
        return f"""
<div style="position:fixed;top:0;left:0;width:100%;height:100%;
     pointer-events:none;z-index:9999;overflow:hidden;">
    <div style="position:absolute;top:50%;left:50%;
         transform:translate(-50%,-50%) rotate({angle}deg);
         font-size:{fs}px;color:{color};opacity:{opacity};
         font-weight:bold;white-space:nowrap;
         user-select:none;">
        {text}
    </div>
</div>
"""


def build_page_number_css(page_config):
    """生成页码 CSS"""
    if not page_config or not page_config.get("enabled"):
        return ""

    pos_map = {
        "底部居中": "bottom-center",
        "底部右侧": "bottom-right",
        "底部左侧": "bottom-left",
        "顶部居中": "top-center",
        "顶部右侧": "top-right",
        "顶部左侧": "top-left",
    }
    pos = pos_map.get(page_config.get("position", "底部居中"),
                       "bottom-center")
    fmt = page_config.get("format", "第 1 页 / 共 N 页")
    fs = page_config.get("fontsize", 10)

    # 根据格式生成 content 表达式
    if fmt == "1":
        content = "counter(page)"
    elif fmt == "第 1 页":
        content = '"第 " counter(page) " 页"'
    elif fmt == "第 1 页 / 共 N 页":
        content = '"第 " counter(page) " 页 / 共 " counter(pages) " 页"'
    elif fmt == "1 / N":
        content = 'counter(page) " / " counter(pages)'
    elif fmt == "Page 1":
        content = '"Page " counter(page)'
    elif fmt == "Page 1 of N":
        content = '"Page " counter(page) " of " counter(pages)'
    else:
        content = "counter(page)"

    return f"""
<style>
@page {{
    @{pos} {{
        content: {content};
        font-size: {fs}pt;
        color: #666;
    }}
}}
</style>
"""