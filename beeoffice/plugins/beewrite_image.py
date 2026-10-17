# beeoffice/plugins/beewrite_image.py
"""
蜜写图片编辑：打开、缩放、旋转、滤镜（简化版）
用 PIL 处理图片，无需 Qt 图形交互

v5.0.1 修复（P1-11）：
  - 文件头注释拼写修正：beewrite_image.py → beewrite_image.py
    （原文件名本身就是 beewrite_，仅注释少了一个 e）
"""

import io
import os
import logging
import tempfile
import time
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QPushButton, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox,
    QDialogButtonBox, QFileDialog, QMessageBox, QSlider,
    QGroupBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QImage
from beeoffice.i18n import tr

try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class ImageEditorDialog(QDialog):
    """图片编辑对话框"""

    def __init__(self, image_path=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("auto.beewrite_image.81f9f77c", "🖼️ 图片编辑"))
        self.resize(760, 620)
        self._image_path = image_path
        self._pil_image = None
        self._original_image = None
        self._rotation = 0
        self._flip_h = False
        self._flip_v = False
        self._grayscale = False
        self._invert = False
        self._brightness = 1.0
        self._blur = 0
        self._result_path = None  # 处理后的图片路径

        if not HAS_PIL:
            QMessageBox.warning(
                self, tr("auto.beewrite_image.1f393593", "缺少依赖"),
                "图片编辑需要 Pillow 库：\n"
                "pip install Pillow"
            )
            return

        self._build_ui()

        if image_path:
            self._load_image(image_path)

    # ==================== UI ====================
    def _build_ui(self):
        layout = QVBoxLayout(self)

        # 预览区
        self._preview_label = QLabel(tr("auto.beewrite_image.f2b6257d", "（暂无图片）"))
        self._preview_label.setAlignment(Qt.AlignCenter)
        self._preview_label.setMinimumHeight(300)
        self._preview_label.setStyleSheet(
            "QLabel{background:#F5F5F5;border:1px solid #DDD;"
            "border-radius:4px;color:#999;}"
        )
        layout.addWidget(self._preview_label, 1)

        # 操作栏
        op_row = QHBoxLayout()

        btn_open = QPushButton(tr("auto.beewrite_image.d455f525", "📂 打开图片"))
        btn_open.clicked.connect(self._open_image)
        op_row.addWidget(btn_open)

        btn_reset = QPushButton(tr("auto.beewrite_image.1b758b77", "🔄 重置"))
        btn_reset.clicked.connect(self._reset)
        op_row.addWidget(btn_reset)

        op_row.addStretch()
        layout.addLayout(op_row)

        # 参数区
        params_group = QGroupBox(tr("auto.beewrite_image.0a4d26e4", "调整"))
        params_layout = QFormLayout(params_group)

        # 缩放
        self._scale_combo = QComboBox()
        self._scale_combo.addItems([
            "原始大小", "50%", "75%", "150%", "200%", "自定义"
        ])
        self._scale_combo.currentTextChanged.connect(
            self._on_scale_changed
        )
        params_layout.addRow("缩放:", self._scale_combo)

        scale_row = QHBoxLayout()
        self._width_spin = QSpinBox()
        self._width_spin.setRange(1, 10000)
        self._width_spin.setSuffix(" px")
        self._width_spin.valueChanged.connect(self._on_size_changed)
        scale_row.addWidget(QLabel(tr("auto.beewrite_image.0091be5a", "宽:")))
        scale_row.addWidget(self._width_spin)

        self._height_spin = QSpinBox()
        self._height_spin.setRange(1, 10000)
        self._height_spin.setSuffix(" px")
        self._height_spin.valueChanged.connect(self._on_size_changed)
        scale_row.addWidget(QLabel(tr("auto.beewrite_image.592d7fb3", "高:")))
        scale_row.addWidget(self._height_spin)

        self._keep_ratio_check = QCheckBox(tr("auto.beewrite_image.dd71a7d1", "保持宽高比"))
        self._keep_ratio_check.setChecked(True)
        scale_row.addWidget(self._keep_ratio_check)

        params_layout.addRow("尺寸:", scale_row)

        # 旋转
        rot_row = QHBoxLayout()
        for label, angle in [("不旋转", 0), ("↻ 90°", 90),
                              ("↺ 180°", 180), ("↻ 270°", 270)]:
            btn = QPushButton(label)
            btn.clicked.connect(
                lambda checked=False, a=angle: self._set_rotation(a)
            )
            rot_row.addWidget(btn)
        params_layout.addRow("旋转:", rot_row)

        # 翻转
        flip_row = QHBoxLayout()
        self._flip_h_check = QCheckBox(tr("auto.beewrite_image.46ed1934", "水平翻转"))
        self._flip_h_check.stateChanged.connect(self._on_flip_changed)
        flip_row.addWidget(self._flip_h_check)

        self._flip_v_check = QCheckBox(tr("auto.beewrite_image.43c98626", "垂直翻转"))
        self._flip_v_check.stateChanged.connect(self._on_flip_changed)
        flip_row.addWidget(self._flip_v_check)

        params_layout.addRow("翻转:", flip_row)

        # 滤镜
        filter_row = QHBoxLayout()
        self._grayscale_check = QCheckBox(tr("auto.beewrite_image.cb706f24", "灰度"))
        self._grayscale_check.stateChanged.connect(
            self._on_filter_changed
        )
        filter_row.addWidget(self._grayscale_check)

        self._invert_check = QCheckBox(tr("auto.beewrite_image.f7ddef87", "反色"))
        self._invert_check.stateChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._invert_check)

        params_layout.addRow("滤镜:", filter_row)

        # 亮度
        bright_row = QHBoxLayout()
        self._brightness_slider = QSlider(Qt.Horizontal)
        self._brightness_slider.setRange(10, 300)
        self._brightness_slider.setValue(100)
        self._brightness_slider.valueChanged.connect(
            self._on_brightness_changed
        )
        bright_row.addWidget(self._brightness_slider)
        self._brightness_label = QLabel("100%")
        self._brightness_label.setMinimumWidth(50)
        bright_row.addWidget(self._brightness_label)
        params_layout.addRow("亮度:", bright_row)

        # 模糊
        blur_row = QHBoxLayout()
        self._blur_slider = QSlider(Qt.Horizontal)
        self._blur_slider.setRange(0, 20)
        self._blur_slider.setValue(0)
        self._blur_slider.valueChanged.connect(self._on_blur_changed)
        blur_row.addWidget(self._blur_slider)
        self._blur_label = QLabel("0")
        self._blur_label.setMinimumWidth(50)
        blur_row.addWidget(self._blur_label)
        params_layout.addRow("模糊:", blur_row)

        layout.addWidget(params_group)

        # 底部按钮
        btns = QDialogButtonBox()

        btn_save = QPushButton(tr("auto.beewrite_image.2859bc4b", "💾 保存为新文件"))
        btn_save.clicked.connect(self._save_as_file)
        btns.addButton(btn_save, QDialogButtonBox.ActionRole)

        btn_insert = QPushButton(tr("auto.beewrite_image.cf0e4ad4", "✅ 插入到文档"))
        btn_insert.setStyleSheet(
            "QPushButton{background:#FFB300;color:#000;"
            "padding:6px 16px;border:none;border-radius:4px;"
            "font-weight:bold;}"
            "QPushButton:hover{background:#FFA000;}"
        )
        btn_insert.clicked.connect(self._insert_to_document)
        btns.addButton(btn_insert, QDialogButtonBox.AcceptRole)

        btn_cancel = QPushButton(tr("auto.beewrite_image.4d0b4688", "取消"))
        btn_cancel.clicked.connect(self.reject)
        btns.addButton(btn_cancel, QDialogButtonBox.RejectRole)

        layout.addWidget(btns)

    # ==================== 图片加载 ====================
    def _open_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("auto.beewrite_image.18104edf", "选择图片"), "",
            tr("auto.beewrite_image.250c7d99", "图片 (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;所有 (*)")
        )
        if path:
            self._load_image(path)

    def _load_image(self, path):
        try:
            self._image_path = path
            img = Image.open(path)
            # 转换为 RGB（去除 alpha 通道）
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            self._original_image = img.copy()
            self._pil_image = img.copy()

            # 设置宽高
            self._width_spin.blockSignals(True)
            self._height_spin.blockSignals(True)
            self._width_spin.setValue(img.width)
            self._height_spin.setValue(img.height)
            self._width_spin.blockSignals(False)
            self._height_spin.blockSignals(False)

            self._refresh_preview()
        except Exception as e:
            QMessageBox.warning(self, tr("auto.beewrite_image.f6b7a41e", "加载失败"), str(e))

    # ==================== 参数变化 ====================
    def _on_scale_changed(self, text):
        if not self._original_image:
            return
        img = self._original_image
        scale_map = {
            "原始大小": 1.0,
            "50%": 0.5,
            "75%": 0.75,
            "150%": 1.5,
            "200%": 2.0,
        }
        if text in scale_map:
            s = scale_map[text]
            self._width_spin.blockSignals(True)
            self._height_spin.blockSignals(True)
            self._width_spin.setValue(int(img.width * s))
            self._height_spin.setValue(int(img.height * s))
            self._width_spin.blockSignals(False)
            self._height_spin.blockSignals(False)
        self._refresh_preview()

    def _on_size_changed(self):
        if not self._original_image:
            return
        if self._keep_ratio_check.isChecked():
            # 保持宽高比：以当前改动的为准
            if self.sender() == self._width_spin:
                ratio = self._original_image.height / self._original_image.width
                self._height_spin.blockSignals(True)
                self._height_spin.setValue(
                    int(self._width_spin.value() * ratio)
                )
                self._height_spin.blockSignals(False)
            else:
                ratio = self._original_image.width / self._original_image.height
                self._width_spin.blockSignals(True)
                self._width_spin.setValue(
                    int(self._height_spin.value() * ratio)
                )
                self._width_spin.blockSignals(False)
        self._refresh_preview()

    def _set_rotation(self, angle):
        self._rotation = angle
        self._refresh_preview()

    def _on_flip_changed(self):
        self._flip_h = self._flip_h_check.isChecked()
        self._flip_v = self._flip_v_check.isChecked()
        self._refresh_preview()

    def _on_filter_changed(self):
        self._grayscale = self._grayscale_check.isChecked()
        self._invert = self._invert_check.isChecked()
        self._refresh_preview()

    def _on_brightness_changed(self, value):
        self._brightness = value / 100.0
        self._brightness_label.setText(f"{value}%")
        self._refresh_preview()

    def _on_blur_changed(self, value):
        self._blur = value
        self._blur_label.setText(str(value))
        self._refresh_preview()

    # ==================== 处理与预览 ====================
    def _process_image(self):
        """应用所有调整，返回 PIL Image"""
        if not self._original_image:
            return None

        img = self._original_image.copy()

        # 缩放
        w = self._width_spin.value()
        h = self._height_spin.value()
        if w != img.width or h != img.height:
            img = img.resize((w, h), Image.LANCZOS)

        # 旋转
        if self._rotation:
            img = img.rotate(
                -self._rotation, expand=True, fillcolor="white"
            )

        # 翻转
        if self._flip_h:
            img = ImageOps.mirror(img)
        if self._flip_v:
            img = ImageOps.flip(img)

        # 灰度
        if self._grayscale:
            img = img.convert("L").convert("RGB")

        # 反色
        if self._invert:
            img = ImageOps.invert(img.convert("RGB"))

        # 亮度
        if self._brightness != 1.0:
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(self._brightness)

        # 模糊
        if self._blur > 0:
            img = img.filter(ImageFilter.GaussianBlur(radius=self._blur))

        return img

    def _refresh_preview(self):
        """刷新预览（生成缩略图）"""
        img = self._process_image()
        if img is None:
            return

        # 生成缩略图
        preview_max = 400
        ratio = min(
            preview_max / img.width, preview_max / img.height, 1.0
        )
        preview_img = img.resize(
            (int(img.width * ratio), int(img.height * ratio)),
            Image.LANCZOS
        )

        # PIL → QPixmap
        buf = io.BytesIO()
        preview_img.save(buf, format="PNG")
        qimg = QImage.fromData(buf.getvalue(), "PNG")
        pixmap = QPixmap.fromImage(qimg)

        self._preview_label.setPixmap(pixmap)
        self._preview_label.setText("")

    def _reset(self):
        """重置所有调整"""
        if self._original_image:
            self._pil_image = self._original_image.copy()
        self._rotation = 0
        self._flip_h = False
        self._flip_v = False
        self._grayscale = False
        self._invert = False
        self._brightness = 1.0
        self._blur = 0
        self._scale_combo.setCurrentText("原始大小")
        self._flip_h_check.setChecked(False)
        self._flip_v_check.setChecked(False)
        self._grayscale_check.setChecked(False)
        self._invert_check.setChecked(False)
        self._brightness_slider.setValue(100)
        self._blur_slider.setValue(0)
        if self._original_image:
            self._width_spin.setValue(self._original_image.width)
            self._height_spin.setValue(self._original_image.height)
        self._refresh_preview()

    # ==================== 保存/插入 ====================
    def _save_as_file(self):
        """保存处理后的图片为新文件"""
        if not self._original_image:
            QMessageBox.information(self, tr("auto.beewrite_image.ab3656a9", "提示"), tr("auto.beewrite_image.f8ca5da6", "请先打开图片"))
            return
        path, _ = QFileDialog.getSaveFileName(
            self, tr("auto.beewrite_image.a927c749", "保存图片"), "edited.png",
            tr("auto.beewrite_image.8b34bce0", "PNG (*.png);;JPEG (*.jpg);;所有 (*)")
        )
        if not path:
            return
        try:
            img = self._process_image()
            img.save(path)
            self._result_path = path
            QMessageBox.information(self, tr("auto.beewrite_image.51991a5d", "成功"), f"已保存：\n{path}")
        except Exception as e:
            QMessageBox.warning(self, tr("auto.beewrite_image.3e3c8068", "失败"), str(e))

    def _insert_to_document(self):
        """将处理后的图片插入到文档"""
        if not self._original_image:
            QMessageBox.information(self, tr("auto.beewrite_image.ab3656a9", "提示"), tr("auto.beewrite_image.f8ca5da6", "请先打开图片"))
            return
        try:
            img = self._process_image()
            # 保存到临时目录
            tmp_dir = Path(tempfile.gettempdir()) / "beeoffice_images"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = tmp_dir / f"edited_{int(time.time()*1000)}.png"
            img.save(str(tmp_path))
            self._result_path = str(tmp_path)
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, tr("auto.beewrite_image.3e3c8068", "失败"), str(e))

    def get_result_path(self):
        """获取处理后的图片路径"""
        return self._result_path