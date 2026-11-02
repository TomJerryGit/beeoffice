# beeoffice/plugins/pdf_toolbox_dialog.py
"""PDF 工具箱 GUI（S1，复用 beecmd v0.5.0 / pdf_tools）。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


# name: (title, multi_input, output_is_dir, pages, password, watermark)
OPERATIONS = {
    "merge": ("合并 PDF", True, False, False, False, False),
    "split": ("拆分 PDF", False, True, True, False, False),
    "extract": ("提取指定页", False, False, True, False, False),
    "delete": ("删除指定页", False, False, True, False, False),
    "encrypt": ("加密 PDF", False, False, False, True, False),
    "watermark": ("添加水印", False, False, True, False, True),
    "text": ("提取文本", False, False, True, False, False),
    "images": ("提取图片", False, True, True, False, False),
    "bookmark": ("添加书签", False, False, True, False, True),
    "sign": ("图片签名/图章", False, False, True, False, True),
}


class PdfToolboxDialog(QDialog):
    """WPS PDF 页面工具的本地 GUI 壳。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🧰 PDF 工具箱")
        self.resize(640, 520)

        self.op_combo = QComboBox()
        for key, (title, *_rest) in OPERATIONS.items():
            self.op_combo.addItem(title, key)
        self.op_combo.currentIndexChanged.connect(self._on_op_changed)

        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("选择 PDF；合并时可多个，用 ; 分隔")
        self.input_btn = QPushButton("浏览…")
        self.input_btn.clicked.connect(self._browse_input)
        input_row = QHBoxLayout()
        input_row.addWidget(self.input_edit, 1)
        input_row.addWidget(self.input_btn)

        self.output_edit = QLineEdit()
        self.output_btn = QPushButton("浏览…")
        self.output_btn.clicked.connect(self._browse_output)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_edit, 1)
        output_row.addWidget(self.output_btn)

        self.pages_edit = QLineEdit()
        self.pages_edit.setPlaceholderText("可选，如 1-3,5,7-；留空=全部")
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.watermark_edit = QLineEdit()
        self.watermark_edit.setPlaceholderText("水印文字，如：内部资料")
        self.allow_print = QCheckBox("允许打印")
        self.allow_print.setChecked(True)
        self.allow_copy = QCheckBox("允许复制")
        self.allow_copy.setChecked(True)
        self.x_spin = QDoubleSpinBox()
        self.x_spin.setRange(0, 100)
        self.x_spin.setValue(60)
        self.x_spin.setSuffix(" %")
        self.y_spin = QDoubleSpinBox()
        self.y_spin.setRange(0, 100)
        self.y_spin.setValue(65)
        self.y_spin.setSuffix(" %")
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(5, 80)
        self.width_spin.setValue(25)
        self.width_spin.setSuffix(" %")
        self.opacity_spin = QDoubleSpinBox()
        self.opacity_spin.setRange(0.1, 1.0)
        self.opacity_spin.setSingleStep(0.1)
        self.opacity_spin.setValue(1.0)

        form = QFormLayout()
        form.addRow("操作：", self.op_combo)
        form.addRow("输入 PDF：", input_row)
        form.addRow("输出：", output_row)
        form.addRow("页码范围：", self.pages_edit)
        form.addRow("打开密码：", self.password_edit)
        form.addRow("水印文字：", self.watermark_edit)
        form.addRow("权限：", self.allow_print)
        form.addRow("", self.allow_copy)
        form.addRow("签名 X：", self.x_spin)
        form.addRow("签名 Y：", self.y_spin)
        form.addRow("签名宽度：", self.width_spin)
        form.addRow("签名透明度：", self.opacity_spin)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("操作结果会显示在这里")
        self.run_btn = QPushButton("▶ 执行")
        self.run_btn.clicked.connect(self._run)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        bookmark_mgr_btn = QPushButton("书签管理…")
        bookmark_mgr_btn.clicked.connect(self._open_bookmark_manager)
        buttons.addWidget(bookmark_mgr_btn)
        buttons.addStretch()
        buttons.addWidget(self.run_btn)
        buttons.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.log, 1)
        layout.addLayout(buttons)
        self._on_op_changed()

    # ---------- UI helpers ----------
    def _op(self) -> str:
        return self.op_combo.currentData()

    def _page_text(self) -> str | None:
        text = self.pages_edit.text().strip()
        return text or None

    def _on_op_changed(self):
        key = self._op()
        _title, multi, out_dir, needs_pages, needs_pwd, needs_wm = OPERATIONS[key]
        self.pages_edit.setVisible(needs_pages)
        self.password_edit.setVisible(needs_pwd)
        self.watermark_edit.setVisible(needs_wm)
        if key in ("bookmark", "sign"):
            self.watermark_edit.setPlaceholderText(
                "书签标题" if key == "bookmark" else "签名/图章图片路径"
            )
        self.allow_print.setVisible(needs_pwd)
        self.allow_copy.setVisible(needs_pwd)
        sign_mode = key == "sign"
        for widget in (self.x_spin, self.y_spin,
                       self.width_spin, self.opacity_spin):
            widget.setVisible(sign_mode)
        self.input_edit.setPlaceholderText(
            "选择多个 PDF，用 ; 分隔" if multi else "选择 PDF"
        )
        self.output_edit.setPlaceholderText(
            "输出目录" if out_dir else "输出 PDF 路径"
        )

    def _browse_input(self):
        if OPERATIONS[self._op()][1]:
            files, _ = QFileDialog.getOpenFileNames(
                self, "选择 PDF", "", "PDF (*.pdf)"
            )
            if files:
                self.input_edit.setText(";".join(files))
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, "选择 PDF", "", "PDF (*.pdf)"
            )
            if path:
                self.input_edit.setText(path)

    def _browse_output(self):
        if OPERATIONS[self._op()][2]:
            path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, "输出文件", "", "PDF (*.pdf);;文本 (*.txt)"
            )
        if path:
            self.output_edit.setText(path)

    def _append(self, text: str):
        self.log.append(text)

    def _validate(self) -> list[str] | None:
        key = self._op()
        _title, multi, out_dir, _pages, needs_pwd, needs_wm = OPERATIONS[key]
        raw = self.input_edit.text().strip()
        files = [x.strip() for x in raw.split(";") if x.strip()]
        if not files:
            self._append("✗ 请先选择输入 PDF")
            return None
        if not multi and len(files) != 1:
            self._append("✗ 该操作只接受一个 PDF")
            return None
        for f in files:
            if not Path(f).is_file():
                self._append(f"✗ 文件不存在: {f}")
                return None
        out = self.output_edit.text().strip()
        if not out:
            self._append("✗ 请设置输出路径/目录")
            return None
        if needs_pwd and not self.password_edit.text():
            self._append("✗ 加密需要打开密码")
            return None
        if key == "delete" and not self._page_text():
            self._append("✗ 删除页面必须填写页码范围")
            return None
        if needs_wm and not self.watermark_edit.text().strip():
            self._append("✗ 水印文字不能为空")
            return None
        return files + [out]

    def _open_bookmark_manager(self):
        path = self.input_edit.text().strip().split(";")[0].strip()
        if not path or not Path(path).is_file():
            self._append("✗ 请先选择一个 PDF")
            return
        out = self.output_edit.text().strip() or None
        from beeoffice.plugins.bookmark_manager_dialog import (
            BookmarkManagerDialog,
        )

        BookmarkManagerDialog(path, out, self).exec()

    # ---------- execution ----------
    def _run(self):
        args = self._validate()
        if not args:
            return
        files, out = args[:-1], args[-1]
        key = self._op()
        self.run_btn.setEnabled(False)
        try:
            from beeoffice import pdf_tools

            if key == "merge":
                info = pdf_tools.merge_pdfs(files, out)
            elif key == "split":
                info = pdf_tools.split_pdf(files[0], out, self._page_text())
            elif key == "extract":
                info = pdf_tools.extract_pages(files[0], out, self._page_text())
            elif key == "delete":
                info = pdf_tools.delete_pages(
                    files[0], out, self._page_text() or ""
                )
            elif key == "encrypt":
                info = pdf_tools.encrypt_pdf(
                    files[0], out, self.password_edit.text(),
                    allow_print=self.allow_print.isChecked(),
                    allow_copy=self.allow_copy.isChecked(),
                )
            elif key == "watermark":
                info = pdf_tools.add_watermark(
                    files[0], out, self.watermark_edit.text().strip(),
                    pages=self._page_text(),
                )
            elif key == "text":
                info = pdf_tools.extract_text(files[0], out, self._page_text())
            elif key == "images":
                info = pdf_tools.extract_images(files[0], out, self._page_text())
            elif key == "bookmark":
                page = int((self._page_text() or "1").split("-")[0] or 1)
                info = pdf_tools.add_bookmark(
                    files[0], out, self.watermark_edit.text().strip(), page
                )
            elif key == "sign":
                page = int((self._page_text() or "1").split("-")[0] or 1)
                info = pdf_tools.stamp_image(
                    files[0], out, self.watermark_edit.text().strip(), page,
                    x=self.x_spin.value() / 100.0,
                    y=self.y_spin.value() / 100.0,
                    width_ratio=self.width_spin.value() / 100.0,
                    opacity=self.opacity_spin.value(),
                )
            else:
                raise ValueError(f"未知操作: {key}")
            self._append(f"✅ 完成：{info}")
        except Exception as e:  # noqa: BLE001 - GUI 需展示所有错误
            self._append(f"✗ 失败：{type(e).__name__}: {e}")
        finally:
            self.run_btn.setEnabled(True)
