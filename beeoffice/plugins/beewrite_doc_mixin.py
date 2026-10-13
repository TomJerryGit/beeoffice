# beeoffice/plugins/beewrite_doc_mixin.py
"""
蜜写文档级操作 Mixin

职责：
  - 目录
    * _insert_toc
  - 水印
    * _set_watermark
  - 页码
    * _set_page_number
  - 页面设置
    * _show_page_setup_dialog
    * get_page_settings
  - 打印预览
    * _print_preview
  - 文档对比
    * _compare_with_original
    * _get_associated_path

依赖：
  - PySide6（QDialog / QVBoxLayout / QHBoxLayout / QFormLayout / QGroupBox /
             QLabel / QLineEdit / QComboBox / QDoubleSpinBox / QDialogButtonBox /
             QMessageBox / QTextEdit / QFileDialog / Qt）
  - beewrite_page_extras（WatermarkDialog / PageNumberDialog）

说明：
  - 本 Mixin 处理「文档级」设置（页面 / 水印 / 页码 / 页眉页脚 / 目录 / 对比 / 打印）
  - 水印、页码的配置保存到 self._watermark_config / self._page_number_config，
    在导出 PDF 时由 ExportMixin 通过 _build_export_extras 注入
  - 不导入其他 beewrite_* Mixin，避免循环依赖
"""
import logging

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QComboBox,
    QDoubleSpinBox,
    QDialogButtonBox,
    QMessageBox,
    QTextEdit,
)
from PySide6.QtCore import Qt

from beeoffice.plugins.beewrite_page_extras import (
    WatermarkDialog,
    PageNumberDialog,
)


# ==================== DocMixin ====================
class DocMixin:
    """蜜写文档级操作 Mixin"""

    # ==================================================================
    # 目录
    # ==================================================================
    def _insert_toc(self):
        """根据当前文档标题生成目录并插入到光标处"""
        if self._edit_mode != "rich_text":
            return
        try:
            from beeoffice.plugins.bee_export import generate_toc
        except Exception as e:
            logging.error(f"导入 generate_toc 失败: {e}")
            QMessageBox.warning(self, "失败", f"生成目录失败：\n{e}")
            return

        md = self.content()
        toc = generate_toc(md)
        self.rich_editor.textCursor().insertBlock()
        self.rich_editor.textCursor().insertText(toc + "\n")
        self._set_status("目录已生成", 3000)

    # ==================================================================
    # 水印
    # ==================================================================
    def _set_watermark(self):
        """打开水印设置对话框，保存配置（导出 PDF 时生效）"""
        dlg = WatermarkDialog(self._watermark_config, self)
        if dlg.exec() != QDialog.Accepted:
            return
        config = dlg.get_config()
        self._watermark_config = config
        if config:
            self._set_status(
                f"✅ 水印已设置：「{config['text']}」（导出 PDF 生效）",
                3000,
            )
        else:
            self._set_status("水印已清除", 2000)

    # ==================================================================
    # 页码
    # ==================================================================
    def _set_page_number(self):
        """打开页码设置对话框，保存配置（导出 PDF 时生效）"""
        dlg = PageNumberDialog(self._page_number_config, self)
        if dlg.exec() != QDialog.Accepted:
            return
        config = dlg.get_config()
        self._page_number_config = config
        if config.get("enabled"):
            self._set_status(
                f"✅ 页码已启用（{config['position']}，导出 PDF 生效）",
                3000,
            )
        else:
            self._set_status("页码已关闭", 2000)

    # ==================================================================
    # 页面设置
    # ==================================================================
    def _show_page_setup_dialog(self):
        """页面设置对话框（纸张 / 方向 / 页边距）"""
        dlg = QDialog(self)
        dlg.setWindowTitle("📄 页面设置")
        dlg.resize(440, 520)
        layout = QVBoxLayout(dlg)

        # ---------- 纸张 ----------
        paper_group = QGroupBox("纸张")
        paper_form = QFormLayout(paper_group)

        paper_combo = QComboBox()
        paper_combo.addItems([
            "A4 (210×297mm)",
            "A3 (297×420mm)",
            "A5 (148×210mm)",
            "Letter (216×279mm)",
            "Legal (216×356mm)",
        ])
        # 恢复当前选择
        current_paper = self._page_settings.get("paper", "A4")
        paper_display_map = {
            "A4": "A4 (210×297mm)",
            "A3": "A3 (297×420mm)",
            "A5": "A5 (148×210mm)",
            "Letter": "Letter (216×279mm)",
            "Legal": "Legal (216×356mm)",
        }
        paper_combo.setCurrentText(
            paper_display_map.get(current_paper, "A4 (210×297mm)")
        )
        paper_form.addRow("纸张大小:", paper_combo)

        orientation_combo = QComboBox()
        orientation_combo.addItems(["纵向", "横向"])
        if self._page_settings.get("orientation") == "landscape":
            orientation_combo.setCurrentText("横向")
        paper_form.addRow("方向:", orientation_combo)
        layout.addWidget(paper_group)

        # ---------- 页边距 ----------
        margin_group = QGroupBox("页边距（厘米）")
        margin_form = QFormLayout(margin_group)

        top_spin = QDoubleSpinBox()
        top_spin.setRange(0, 10)
        top_spin.setSingleStep(0.1)
        top_spin.setValue(self._page_settings["margin_top"] / 10)
        top_spin.setDecimals(2)
        margin_form.addRow("上:", top_spin)

        bottom_spin = QDoubleSpinBox()
        bottom_spin.setRange(0, 10)
        bottom_spin.setSingleStep(0.1)
        bottom_spin.setValue(self._page_settings["margin_bottom"] / 10)
        bottom_spin.setDecimals(2)
        margin_form.addRow("下:", bottom_spin)

        left_spin = QDoubleSpinBox()
        left_spin.setRange(0, 10)
        left_spin.setSingleStep(0.1)
        left_spin.setValue(self._page_settings["margin_left"] / 10)
        left_spin.setDecimals(2)
        margin_form.addRow("左:", left_spin)

        right_spin = QDoubleSpinBox()
        right_spin.setRange(0, 10)
        right_spin.setSingleStep(0.1)
        right_spin.setValue(self._page_settings["margin_right"] / 10)
        right_spin.setDecimals(2)
        margin_form.addRow("右:", right_spin)
        layout.addWidget(margin_group)

        # ---------- 提示 ----------
        tip = QLabel(
            "💡 页面设置会保存到当前文档，导出 PDF 时自动应用。"
        )
        tip.setStyleSheet(
            "QLabel{color:#666;font-size:12px;padding:8px;"
            "background:#FFF8E1;border-radius:4px;}"
        )
        tip.setWordWrap(True)
        layout.addWidget(tip)

        layout.addStretch()

        # ---------- 按钮 ----------
        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )

        def on_ok():
            paper_map = {
                "A4 (210×297mm)": "A4",
                "A3 (297×420mm)": "A3",
                "A5 (148×210mm)": "A5",
                "Letter (216×279mm)": "Letter",
                "Legal (216×356mm)": "Legal",
            }
            self._page_settings["paper"] = paper_map.get(
                paper_combo.currentText(), "A4"
            )
            self._page_settings["orientation"] = (
                "portrait"
                if orientation_combo.currentText() == "纵向"
                else "landscape"
            )
            self._page_settings["margin_top"] = top_spin.value() * 10
            self._page_settings["margin_bottom"] = bottom_spin.value() * 10
            self._page_settings["margin_left"] = left_spin.value() * 10
            self._page_settings["margin_right"] = right_spin.value() * 10

            self._set_status(
                f"✅ 页面设置已更新（{paper_combo.currentText()}）", 3000
            )
            dlg.accept()

        btns.accepted.connect(on_ok)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        dlg.exec()

    def get_page_settings(self):
        """返回当前页面设置（供 ExportMixin 使用）"""
        return dict(self._page_settings)

    # ==================================================================
    # DOCX 扩展信息（保真度阶段 A）
    # ==================================================================
    def apply_docx_extras(self, extras):
        """
        导入 DOCX 时保存**Markdown 表达不了**的信息。

        为什么需要：`import_from_docx()` 只返回 Markdown 字符串，而 Markdown
        没有"页面设置/页眉页脚"的概念 —— 实测往返后页边距变成默认 1 英寸、
        页眉页脚部件直接消失。这些信息必须在 Markdown **之外**随文档保留，
        导出时再写回。

        :param extras: `bee_export.read_docx_extras()` 的返回值
        :return: 实际应用了多少项（便于调用方决定是否提示用户）
        """
        if not extras:
            return 0

        applied = 0

        # 页面设置：只覆盖解析得到的项，其余保持编辑器当前值
        page_keys = (
            "paper", "orientation", "margin_top", "margin_bottom",
            "margin_left", "margin_right",
            "page_width_mm", "page_height_mm",
        )
        for key in page_keys:
            if key in extras and extras[key] not in ("", None):
                self._page_settings[key] = extras[key]
                applied += 1

        # 页眉页脚文字：另存，导出时由 export_to_docx 写入
        for key in ("header_text", "footer_text"):
            if key in extras:
                setattr(self, f"_docx_{key}", extras[key] or "")
                applied += 1

        # 表格合并信息（Markdown 表格语法表达不了，故绕开 Markdown 传递）
        if extras.get("table_merges"):
            self._docx_table_merges = list(extras["table_merges"])
            applied += 1

        # 分节信息（多分节文档，例如第二节横向）
        if extras.get("sections"):
            self._docx_sections = list(extras["sections"])
            applied += 1

        # 书签（Markdown 无书签语法；实测 5/7 份真实文档带书签）
        if extras.get("bookmarks"):
            self._docx_bookmarks = list(extras["bookmarks"])
            applied += 1

        return applied

    def get_docx_extras(self):
        """返回需要在导出时写回的 DOCX 扩展信息（供 ExportMixin 使用）。"""
        return {
            "header_text": getattr(self, "_docx_header_text", ""),
            "footer_text": getattr(self, "_docx_footer_text", ""),
            "table_merges": getattr(self, "_docx_table_merges", []),
            "sections": getattr(self, "_docx_sections", []),
            "bookmarks": getattr(self, "_docx_bookmarks", []),
        }

    # ==================================================================
    # 打印预览
    # ==================================================================
    def _print_preview(self):
        """打开打印预览对话框"""
        try:
            from PySide6.QtPrintSupport import (
                QPrinter,
                QPrintPreviewDialog,
            )
        except ImportError:
            QMessageBox.warning(
                self, "提示", "当前环境不支持打印功能"
            )
            return

        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageSize(QPrinter.A4)

        preview = QPrintPreviewDialog(printer, self)
        preview.setWindowTitle("📄 打印预览")
        preview.resize(900, 700)

        def render(p):
            """渲染当前文档到打印设备"""
            if self._edit_mode == "rich_text":
                self.rich_editor.document().print_(p)
            else:
                md = self.content()
                try:
                    import markdown
                    html = markdown.markdown(
                        md,
                        extensions=["tables", "fenced_code"],
                    )
                except Exception:
                    html = f"<pre>{md}</pre>"
                from PySide6.QtGui import QTextDocument
                doc = QTextDocument()
                doc.setHtml(html)
                doc.print_(p)

        preview.paintRequested.connect(render)
        preview.exec()

    # ==================================================================
    # 文档对比
    # ==================================================================
    def _compare_with_original(self):
        """与磁盘上的原始文件对比差异"""
        try:
            from beeoffice.plugins.bee_export import compare_documents
        except Exception as e:
            logging.error(f"导入 compare_documents 失败: {e}")
            QMessageBox.warning(self, "失败", f"文档对比失败：\n{e}")
            return

        path = self._get_associated_path()
        if not path:
            QMessageBox.information(
                self, "提示", "请先保存文档后再对比"
            )
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                original = f.read()
            result = compare_documents(original, self.content())

            dlg = QDialog(self)
            dlg.setWindowTitle("📊 文档对比")
            dlg.resize(600, 400)
            layout = QVBoxLayout(dlg)
            layout.addWidget(QLabel(
                f"新增: {result['additions']} 行 | "
                f"删除: {result['deletions']} 行 | "
                f"变更: {result['total_changes']} 处"
            ))
            diff_view = QTextEdit()
            diff_view.setReadOnly(True)
            diff_view.setPlainText(result["diff"])
            layout.addWidget(diff_view)
            dlg.exec()
        except Exception as e:
            QMessageBox.warning(self, "对比失败", str(e))

    def _get_associated_path(self):
        """获取当前文档关联的磁盘文件路径（若未保存返回空字符串）"""
        p = self
        while p:
            if hasattr(p, "_tab_file_paths"):
                return p._tab_file_paths.get(id(self), "")
            p = p.parent()
        return ""