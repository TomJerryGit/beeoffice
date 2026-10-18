# -*- coding: utf-8 -*-
"""
PDF 页面工具对话框（阶段四 P0-1）

一个窗口覆盖五种操作：合并 / 提取 / 删除 / 旋转 / 拆分。
不做"每页缩略图拖拽排序"——那需要一整套缩略图渲染与拖放逻辑，
而按范围输入已经能覆盖绝大多数真实需求（"把 3-7 页单独拿出来"）。

操作在 GUI 线程同步执行：本地页面级操作通常 < 1 秒，
大文件合并会有短暂卡顿，v1 接受这个代价。
"""
import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from beeoffice.i18n import tr
from beeoffice.plugins import pdf_pages

MODES = ("merge", "extract", "delete", "rotate", "split")


class PdfPagesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("pdf.pages.title", "PDF 页面工具"))
        self.setMinimumWidth(620)
        self._build_ui()
        self._on_mode_changed()

    # ---------- UI ----------
    def _build_ui(self):
        root = QVBoxLayout(self)

        # 模式
        row_mode = QHBoxLayout()
        row_mode.addWidget(QLabel(tr("pdf.pages.mode", "操作：")))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem(tr("pdf.pages.mode.merge", "合并文件"), "merge")
        self.mode_combo.addItem(tr("pdf.pages.mode.extract", "提取页面"), "extract")
        self.mode_combo.addItem(tr("pdf.pages.mode.delete", "删除页面"), "delete")
        self.mode_combo.addItem(tr("pdf.pages.mode.rotate", "旋转页面"), "rotate")
        self.mode_combo.addItem(tr("pdf.pages.mode.split", "拆分文件"), "split")
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        row_mode.addWidget(self.mode_combo, 1)
        root.addLayout(row_mode)

        # 源文件（单文件模式）
        row_src = QHBoxLayout()
        row_src.addWidget(QLabel(tr("pdf.pages.source", "源文件：")))
        self.src_edit = QLineEdit()
        self.src_edit.setReadOnly(True)
        row_src.addWidget(self.src_edit, 1)
        self.src_btn = QPushButton(tr("pdf.pages.browse", "浏览…"))
        self.src_btn.clicked.connect(self._pick_source)
        row_src.addWidget(self.src_btn)
        self.count_label = QLabel("")
        row_src.addWidget(self.count_label)
        root.addLayout(row_src)

        # 合并文件列表
        self.list_label = QLabel(tr("pdf.pages.merge_list", "待合并文件（按顺序）："))
        root.addWidget(self.list_label)
        self.file_list = QListWidget()
        root.addWidget(self.file_list)
        row_list = QHBoxLayout()
        self.add_btn = QPushButton(tr("pdf.pages.add", "添加"))
        self.add_btn.clicked.connect(self._add_files)
        self.remove_btn = QPushButton(tr("pdf.pages.remove", "移除"))
        self.remove_btn.clicked.connect(self._remove_file)
        self.up_btn = QPushButton(tr("pdf.pages.up", "上移"))
        self.up_btn.clicked.connect(lambda: self._move_file(-1))
        self.down_btn = QPushButton(tr("pdf.pages.down", "下移"))
        self.down_btn.clicked.connect(lambda: self._move_file(1))
        for b in (self.add_btn, self.remove_btn, self.up_btn, self.down_btn):
            row_list.addWidget(b)
        row_list.addStretch(1)
        root.addLayout(row_list)

        # 页码范围
        row_range = QHBoxLayout()
        self.range_label = QLabel(tr("pdf.pages.range", "页码范围："))
        row_range.addWidget(self.range_label)
        self.range_edit = QLineEdit()
        self.range_edit.setPlaceholderText(
            tr("pdf.pages.range_hint", "例如 1-3,5,8-（留空表示全部）")
        )
        row_range.addWidget(self.range_edit, 1)
        root.addLayout(row_range)

        # 旋转角度
        row_angle = QHBoxLayout()
        self.angle_label = QLabel(tr("pdf.pages.angle", "旋转角度："))
        row_angle.addWidget(self.angle_label)
        self.angle_combo = QComboBox()
        self.angle_combo.addItem("90°", 90)
        self.angle_combo.addItem("180°", 180)
        self.angle_combo.addItem("270°", 270)
        row_angle.addWidget(self.angle_combo)
        row_angle.addStretch(1)
        root.addLayout(row_angle)

        # 拆分方式
        row_split = QHBoxLayout()
        self.split_label = QLabel(tr("pdf.pages.split_mode", "拆分方式："))
        row_split.addWidget(self.split_label)
        self.split_combo = QComboBox()
        self.split_combo.addItem(tr("pdf.pages.split.each", "每页一个文件"), "each")
        self.split_combo.addItem(
            tr("pdf.pages.split.every", "每 N 页一个文件"), "every"
        )
        self.split_combo.addItem(
            tr("pdf.pages.split.ranges", "按范围拆分"), "ranges"
        )
        self.split_combo.currentIndexChanged.connect(self._on_split_changed)
        row_split.addWidget(self.split_combo)
        self.every_label = QLabel(tr("pdf.pages.every_n", "每份页数："))
        self.every_spin = QSpinBox()
        self.every_spin.setRange(1, 9999)
        self.every_spin.setValue(10)
        row_split.addWidget(self.every_label)
        row_split.addWidget(self.every_spin)
        row_split.addStretch(1)
        root.addLayout(row_split)

        # 输出
        row_out = QHBoxLayout()
        row_out.addWidget(QLabel(tr("pdf.pages.output", "输出：")))
        self.out_edit = QLineEdit()
        row_out.addWidget(self.out_edit, 1)
        self.out_btn = QPushButton(tr("pdf.pages.browse", "浏览…"))
        self.out_btn.clicked.connect(self._pick_output)
        row_out.addWidget(self.out_btn)
        root.addLayout(row_out)

        # 状态
        self.status = QLabel("")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        # 按钮
        row_btn = QHBoxLayout()
        row_btn.addStretch(1)
        self.run_btn = QPushButton(tr("pdf.pages.run", "执行"))
        self.run_btn.setDefault(True)
        self.run_btn.clicked.connect(self._run)
        row_btn.addWidget(self.run_btn)
        self.close_btn = QPushButton(tr("pdf.pages.close", "关闭"))
        self.close_btn.clicked.connect(self.reject)
        row_btn.addWidget(self.close_btn)
        root.addLayout(row_btn)

    # ---------- 状态切换 ----------
    def current_mode(self) -> str:
        return self.mode_combo.currentData()

    def _on_mode_changed(self, *_):
        mode = self.current_mode()
        single = mode != "merge"
        for w in (self.src_edit, self.src_btn, self.count_label):
            w.setVisible(single)
        for w in (self.list_label, self.file_list):
            w.setVisible(not single)
        for w in (self.add_btn, self.remove_btn, self.up_btn, self.down_btn):
            w.setVisible(not single)

        need_range = mode in ("extract", "delete", "rotate")
        self.range_label.setVisible(need_range)
        self.range_edit.setVisible(need_range)

        need_angle = mode == "rotate"
        self.angle_label.setVisible(need_angle)
        self.angle_combo.setVisible(need_angle)

        is_split = mode == "split"
        self.split_label.setVisible(is_split)
        self.split_combo.setVisible(is_split)
        self._on_split_changed()

    def _on_split_changed(self, *_):
        is_split = self.current_mode() == "split"
        kind = self.split_combo.currentData() if is_split else ""
        self.every_label.setVisible(is_split and kind == "every")
        self.every_spin.setVisible(is_split and kind == "every")
        # 按范围拆分时复用页码范围输入框，并允许多段用分号分隔
        if is_split and kind == "ranges":
            self.range_label.setVisible(True)
            self.range_edit.setVisible(True)
            self.range_edit.setPlaceholderText(
                tr("pdf.pages.ranges_hint", "多段用分号分隔，例如 1-3;5;8-")
            )
        elif self.current_mode() == "split":
            self.range_label.setVisible(False)
            self.range_edit.setVisible(False)

    # ---------- 选文件 ----------
    def _pick_source(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("pdf.pages.pick_source", "选择 PDF"), "", "PDF (*.pdf)"
        )
        if not path:
            return
        try:
            total = pdf_pages.page_count(path)
        except pdf_pages.PdfPageError as e:
            QMessageBox.warning(self, tr("pdf.pages.error", "无法打开"), str(e))
            return
        self.src_edit.setText(path)
        self.count_label.setText(
            tr("pdf.pages.pages_count", "共 {n} 页").format(n=total)
        )
        if not self.out_edit.text():
            p = Path(path)
            self.out_edit.setText(
                str(p.with_name(p.stem + tr("pdf.pages.out_suffix", "_已处理") + ".pdf"))
            )

    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("pdf.pages.add_files", "选择要合并的 PDF"), "", "PDF (*.pdf)"
        )
        for p in paths:
            self.file_list.addItem(p)
        if paths and not self.out_edit.text():
            first = Path(paths[0])
            self.out_edit.setText(
                str(first.with_name(first.stem + tr("pdf.pages.merged", "_合并") + ".pdf"))
            )

    def _remove_file(self):
        row = self.file_list.currentRow()
        if row >= 0:
            self.file_list.takeItem(row)

    def _move_file(self, delta):
        row = self.file_list.currentRow()
        target = row + delta
        if row < 0 or target < 0 or target >= self.file_list.count():
            return
        item = self.file_list.takeItem(row)
        self.file_list.insertItem(target, item)
        self.file_list.setCurrentRow(target)

    def _pick_output(self):
        mode = self.current_mode()
        if mode == "split":
            path = QFileDialog.getExistingDirectory(
                self, tr("pdf.pages.pick_dir", "选择输出文件夹")
            )
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, tr("pdf.pages.pick_output", "保存为"), "", "PDF (*.pdf)"
            )
        if path:
            self.out_edit.setText(path)

    def _collect_files(self) -> list:
        return [self.file_list.item(i).text() for i in range(self.file_list.count())]

    # ---------- 执行 ----------
    def _run(self):
        mode = self.current_mode()
        out = self.out_edit.text().strip()
        if not out:
            QMessageBox.warning(
                self,
                tr("pdf.pages.missing", "缺少信息"),
                tr("pdf.pages.need_output", "请先选择输出位置"),
            )
            return

        try:
            if mode == "merge":
                files = self._collect_files()
                if len(files) < 2:
                    raise pdf_pages.PdfPageError(
                        tr("pdf.pages.need_two", "请至少添加两个 PDF 文件")
                    )
                n = pdf_pages.merge_pdfs(files, out)
                self._done(tr("pdf.pages.done", "完成：{n} 页 → {path}")
                           .format(n=n, path=out))
            elif mode == "extract":
                src = self._require_source()
                n = pdf_pages.extract_pages(src, self.range_edit.text(), out)
                self._done(tr("pdf.pages.done", "完成：{n} 页 → {path}")
                           .format(n=n, path=out))
            elif mode == "delete":
                src = self._require_source()
                n = pdf_pages.delete_pages(src, self.range_edit.text(), out)
                self._done(tr("pdf.pages.remaining", "完成：剩余 {n} 页 → {path}")
                           .format(n=n, path=out))
            elif mode == "rotate":
                src = self._require_source()
                n = pdf_pages.rotate_pages(
                    src, self.range_edit.text(),
                    self.angle_combo.currentData(), out,
                )
                self._done(tr("pdf.pages.rotated", "完成：旋转 {n} 页 → {path}")
                           .format(n=n, path=out))
            else:
                src = self._require_source()
                kind = self.split_combo.currentData()
                if kind == "each":
                    files = pdf_pages.split_pages(src, out)
                elif kind == "every":
                    files = pdf_pages.split_every(src, self.every_spin.value(), out)
                else:
                    parts = [
                        s.strip()
                        for s in self.range_edit.text().replace(";", "；").split("；")
                        if s.strip()
                    ]
                    if not parts:
                        raise pdf_pages.PdfPageError(
                            tr("pdf.pages.need_ranges", "请填写拆分范围")
                        )
                    files = pdf_pages.split_ranges(src, parts, out)
                self._done(
                    tr("pdf.pages.done_multi", "完成：生成 {n} 个文件 → {path}")
                    .format(n=len(files), path=out)
                )
        except pdf_pages.PdfPageError as e:
            QMessageBox.warning(self, tr("pdf.pages.error", "无法打开"), str(e))
            self.status.setText(str(e))
        except Exception as e:  # 未预期错误：记日志并提示，不吞掉
            logging.error(f"PDF 页面操作失败: {e}")
            QMessageBox.warning(
                self,
                tr("pdf.pages.error", "无法打开"),
                tr("pdf.pages.failed", "处理失败：{e}").format(e=e),
            )

    def _require_source(self) -> str:
        src = self.src_edit.text().strip()
        if not src:
            raise pdf_pages.PdfPageError(
                tr("pdf.pages.need_source", "请先选择源文件")
            )
        return src

    def _done(self, text: str):
        self.status.setText(text)
        QMessageBox.information(self, tr("pdf.pages.finished", "完成"), text)
