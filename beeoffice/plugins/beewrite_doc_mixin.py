from beeoffice.theme import Theme


def _t():
    return Theme.tokens()

# beeoffice/plugins/beewrite_doc_mixin.py
"""
蜜写文档级操作 Mixin

职责：
  - 页眉 / 页脚
    * _insert_header / _insert_footer
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
from PySide6.QtGui import QTextCursor

from beeoffice.plugins.beewrite_page_extras import (
    WatermarkDialog,
    PageNumberDialog,
)
from beeoffice.i18n import tr


# ==================== DocMixin ====================
class DocMixin:
    """蜜写文档级操作 Mixin"""

    # ==================================================================
    # 页眉 / 页脚
    # ==================================================================
    def _insert_header(self):
        """
        设置页眉（导出 Word 时写入 section.header）。

        修复：原实现把 `<!-- header: ... -->` 直接插进正文，在编辑器里
        就是一行可见的注释文字，而且全仓没有任何地方解析它——
        既难看又不生效。现在只记在内存里，导出时交给 python-docx。
        """
        if self._edit_mode != "rich_text":
            return
        from PySide6.QtWidgets import QInputDialog

        text, ok = QInputDialog.getText(
            self, tr("auto.beewrite_doc_mixin.a666b4dc", "页眉"), tr("auto.beewrite_doc_mixin.3b0cbf26", "请输入页眉文字:"),
            text=getattr(self, "_header_text", ""),
        )
        if ok:
            self._header_text = text.strip()
            self._set_status(
                tr("auto.beewrite_doc_mixin.cfc15eab", "页眉已设置：{0}（导出 Word 时生效）").format(self._header_text or '（空）'),
                3000,
            )

    def _insert_footer(self):
        """设置页脚（导出 Word 时写入 section.footer）。"""
        if self._edit_mode != "rich_text":
            return
        from PySide6.QtWidgets import QInputDialog

        text, ok = QInputDialog.getText(
            self, tr("auto.beewrite_doc_mixin.d1511155", "页脚"), tr("auto.beewrite_doc_mixin.c14713dc", "请输入页脚文字:"),
            text=getattr(self, "_footer_text", ""),
        )
        if ok:
            self._footer_text = text.strip()
            self._set_status(
                tr("auto.beewrite_doc_mixin.26197cf4", "页脚已设置：{0}（导出 Word 时生效）").format(self._footer_text or '（空）'),
                3000,
            )

    def _apply_header_footer(self, doc):
        """
        把内存里的页眉/页脚写入 python-docx 文档的节。

        :param doc: python-docx Document
        :return: 是否实际写入
        """
        header_text = getattr(self, "_header_text", "") or ""
        footer_text = getattr(self, "_footer_text", "") or ""
        if not header_text and not footer_text:
            return False
        try:
            from docx.enum.text import WD_ALIGN_PARAGRAPH
        except Exception:
            return False

        try:
            section = doc.sections[0]
            if header_text:
                para = section.header.paragraphs[0]
                para.text = header_text
                para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            if footer_text:
                para = section.footer.paragraphs[0]
                para.text = footer_text
                para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            return True
        except Exception as e:
            logging.error(f"写入页眉/页脚失败: {e}")
            return False

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
            QMessageBox.warning(self, tr("auto.beewrite_doc_mixin.3e3c8068", "失败"), tr("auto.beewrite_doc_mixin.8831e02a", "生成目录失败：\n{e}").format(e=e))
            return

        md = self.content()
        toc = generate_toc(md)
        self.rich_editor.textCursor().insertBlock()
        self.rich_editor.textCursor().insertText(toc + "\n")
        self._set_status(tr("auto.beewrite_doc_mixin.ce1d16eb", "目录已生成"), 3000)

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
                tr("auto.beewrite_doc_mixin.4fa4c532", "✅ 水印已设置：「{0}」（导出 PDF 生效）").format(config['text']),
                3000,
            )
        else:
            self._set_status(tr("auto.beewrite_doc_mixin.5be9561b", "水印已清除"), 2000)

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
                tr("auto.beewrite_doc_mixin.052ec4d2", "✅ 页码已启用（{0}，导出 PDF 生效）").format(config['position']),
                3000,
            )
        else:
            self._set_status(tr("auto.beewrite_doc_mixin.cce4b227", "页码已关闭"), 2000)

    # ==================================================================
    # 页面设置
    # ==================================================================
    def _show_page_setup_dialog(self):
        """页面设置对话框（纸张 / 方向 / 页边距）"""
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("auto.beewrite_doc_mixin.4638ca51", "📄 页面设置"))
        dlg.resize(440, 520)
        layout = QVBoxLayout(dlg)

        # ---------- 纸张 ----------
        paper_group = QGroupBox(tr("auto.beewrite_doc_mixin.59b908f4", "纸张"))
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
        margin_group = QGroupBox(tr("auto.beewrite_doc_mixin.addcb77e", "页边距（厘米）"))
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
            tr("auto.beewrite_doc_mixin.e2861613", "💡 页面设置会保存到当前文档，导出 PDF 时自动应用。")
        )
        tip.setStyleSheet(
            f"QLabel{{color:{_t()['muted']};font-size:12px;padding:8px;"
            f"background:{_t()['accent_light']};border-radius:4px;}}"
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
                tr("auto.beewrite_doc_mixin.0d812700", "✅ 页面设置已更新（{0}）").format(paper_combo.currentText()), 3000
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
                self, tr("auto.beewrite_doc_mixin.ab3656a9", "提示"), tr("auto.beewrite_doc_mixin.b12475c6", "当前环境不支持打印功能")
            )
            return

        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageSize(QPrinter.A4)

        preview = QPrintPreviewDialog(printer, self)
        preview.setWindowTitle(tr("auto.beewrite_doc_mixin.b1d3e566", "📄 打印预览"))
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
            QMessageBox.warning(self, tr("auto.beewrite_doc_mixin.3e3c8068", "失败"), tr("auto.beewrite_doc_mixin.84e66f8d", "文档对比失败：\n{e}").format(e=e))
            return

        path = self._get_associated_path()
        if not path:
            QMessageBox.information(
                self, tr("auto.beewrite_doc_mixin.ab3656a9", "提示"), tr("auto.beewrite_doc_mixin.2b1c1ff4", "请先保存文档后再对比")
            )
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                original = f.read()
            result = compare_documents(original, self.content())

            dlg = QDialog(self)
            dlg.setWindowTitle(tr("auto.beewrite_doc_mixin.1bb6ea3e", "📊 文档对比"))
            dlg.resize(600, 400)
            layout = QVBoxLayout(dlg)
            layout.addWidget(QLabel(
                tr("auto.beewrite_doc_mixin.9188260b", "新增: {0} 行 | 删除: {1} 行 | 变更: {2} 处").format(result['additions'], result['deletions'], result['total_changes'])
            ))
            diff_view = QTextEdit()
            diff_view.setReadOnly(True)
            diff_view.setPlainText(result["diff"])
            layout.addWidget(diff_view)
            dlg.exec()
        except Exception as e:
            QMessageBox.warning(self, tr("auto.beewrite_doc_mixin.3a7c4883", "对比失败"), str(e))

    def _get_associated_path(self):
        """获取当前文档关联的磁盘文件路径（若未保存返回空字符串）"""
        p = self
        while p:
            if hasattr(p, "_tab_file_paths"):
                return p._tab_file_paths.get(id(self), "")
            p = p.parent()
        return ""
    def _page_view_payload(self):
        """返回 (文档, 页面设置, 页眉, 页脚, 页码配置) 供页面视图刷新。"""
        from beeoffice.plugins.beewrite_page_view import build_page_document

        if self._edit_mode == "rich_text":
            doc = self.rich_editor.document().clone()
        else:
            doc = build_page_document(markdown_text=self.content())
        return (
            doc,
            dict(self._page_settings),
            getattr(self, "_header_text", "") or "",
            getattr(self, "_footer_text", "") or "",
            dict(self._page_number_config or {}),
        )

    def _open_page_view(self):
        """打开只读纸张页面视图。"""
        from beeoffice.plugins.beewrite_page_view import PageViewDialog

        doc, settings, header, footer, page_number = self._page_view_payload()
        dialog = PageViewDialog(
            doc, settings, self,
            header_text=header, footer_text=footer,
            page_number_config=page_number,
            provider=self._page_view_payload,
        )
        dialog.position_clicked.connect(self._on_page_view_position)
        dialog.edit_requested.connect(self._on_page_view_edit)
        dialog.document_edited.connect(self._apply_page_edit)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        self._page_view_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return dialog

    def _apply_page_edit(self, document):
        """M2 原型：把单页编辑后的文档写回蜜写富文本。

        用一次 QTextCursor 编辑块替换全文，保留原有撤销栈：
        页面编辑只产生一个可撤销动作，而不是清空历史。
        """
        if self._edit_mode != "rich_text":
            self._switch_mode("rich_text")
        editor = self.rich_editor
        cursor = editor.textCursor()
        cursor.beginEditBlock()
        try:
            cursor.select(QTextCursor.Document)
            cursor.insertHtml(document.toHtml())
        finally:
            cursor.endEditBlock()
        editor.setTextCursor(cursor)
        self._update_status_bar()

    def _on_page_view_edit(self, position: int):
        """双击页面 → 关闭页面视图并回到编辑区定位（可编辑流程起点）。"""
        dialog = getattr(self, "_page_view_dialog", None)
        if dialog is not None:
            dialog.close()
        self._on_page_view_position(position)

    def _on_page_view_position(self, position: int):
        """页面视图点击 → 在编辑区定位。"""
        if self._edit_mode != "rich_text":
            try:
                self._switch_mode("rich_text")
            except Exception:
                pass
        editor = self.rich_editor
        cursor = editor.textCursor()
        max_pos = max(0, editor.document().characterCount() - 1)
        cursor.setPosition(max(0, min(int(position), max_pos)))
        editor.setTextCursor(cursor)
        editor.ensureCursorVisible()
        editor.setFocus()
