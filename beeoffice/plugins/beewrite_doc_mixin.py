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
from pathlib import Path

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
    QLineEdit,
    QCheckBox,
    QSpinBox,
    QColorDialog,
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
    # 多节导入 / 每节独立设置
    # ==================================================================
    def _apply_imported_sections(self, sections):
        """保存导入的节设置，并把标记段落转为分节符。"""
        from beeoffice.plugins.bee_export import SECTION_BREAK_MARKER
        from PySide6.QtGui import QTextBlockFormat, QTextFormat, QTextCursor
        self._section_page_settings = [dict(s.get("settings", {})) for s in (sections or [])]
        if self._section_page_settings:
            first = self._section_page_settings[0]
            self._page_settings.update(first)
            self._header_text = first.get("header", getattr(self, "_header_text", ""))
            self._footer_text = first.get("footer", getattr(self, "_footer_text", ""))
            self._different_first_page = bool(first.get("different_first_page", getattr(self, "_different_first_page", False)))
            self._header_first_text = first.get("header_first", getattr(self, "_header_first_text", ""))
        block = self.rich_editor.document().begin()
        while block.isValid():
            if SECTION_BREAK_MARKER in block.text():
                cursor = QTextCursor(block)
                cursor.beginEditBlock()
                cursor.select(QTextCursor.BlockUnderCursor)
                cursor.removeSelectedText()
                bf = QTextBlockFormat()
                bf.setProperty(QTextFormat.UserProperty, 0xBEE2)
                cursor.setBlockFormat(bf)
                cursor.endEditBlock()
            block = block.next()

    def _show_section_settings_dialog(self):
        from PySide6.QtWidgets import QInputDialog
        secs = getattr(self, "_section_page_settings", [])
        if not secs:
            QMessageBox.information(self, "节设置", "当前文档没有多节信息。")
            return
        labels = [f"第 {i + 1} 节" for i in range(len(secs))]
        label, ok = QInputDialog.getItem(self, "节设置", "选择节：", labels, 0, False)
        if not ok:
            return
        idx = labels.index(label)
        cfg = secs[idx]
        from PySide6.QtWidgets import (
            QDialog, QFormLayout, QDoubleSpinBox, QSpinBox,
            QCheckBox, QDialogButtonBox,
        )
        dlg = QDialog(self); dlg.setWindowTitle(label)
        form = QFormLayout(dlg)
        top = QDoubleSpinBox(); top.setRange(0, 100); top.setValue(float(cfg.get("margin_top", 25.4))); form.addRow("上边距(mm)", top)
        bottom = QDoubleSpinBox(); bottom.setRange(0, 100); bottom.setValue(float(cfg.get("margin_bottom", 25.4))); form.addRow("下边距(mm)", bottom)
        left = QDoubleSpinBox(); left.setRange(0, 100); left.setValue(float(cfg.get("margin_left", 31.7))); form.addRow("左边距(mm)", left)
        right = QDoubleSpinBox(); right.setRange(0, 100); right.setValue(float(cfg.get("margin_right", 31.7))); form.addRow("右边距(mm)", right)
        cols = QSpinBox(); cols.setRange(1, 4); cols.setValue(int(cfg.get("columns", 1))); form.addRow("分栏", cols)
        border = QCheckBox("页面边框"); border.setChecked(bool(cfg.get("page_border", False))); form.addRow(border)
        from PySide6.QtWidgets import QLineEdit
        header = QLineEdit(str(cfg.get("header", ""))); form.addRow("页眉", header)
        footer = QLineEdit(str(cfg.get("footer", ""))); form.addRow("页脚", footer)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject); form.addRow(btns)
        if dlg.exec() != QDialog.Accepted:
            return
        cfg.update({"margin_top": top.value(), "margin_bottom": bottom.value(),
                    "margin_left": left.value(), "margin_right": right.value(),
                    "columns": cols.value(), "page_border": border.isChecked(),
                    "header": header.text(), "footer": footer.text()})
        self._section_page_settings[idx] = cfg
        if idx == 0:
            self._page_settings.update(cfg)
        self._set_status(f"{label} 设置已更新", 2000)

    # ==================================================================
    # P1：封面 / 页面背景
    # ==================================================================
    def _insert_cover_page(self):
        """在文档开头插入企业封面（标题/副标题/单位/日期）。"""
        from PySide6.QtWidgets import QInputDialog
        from PySide6.QtGui import QTextBlockFormat, QTextCharFormat, QTextCursor, QFont
        title, ok = QInputDialog.getText(self, "封面", "标题：", text="XX 公司")
        if not ok or not title.strip():
            return
        subtitle, _ = QInputDialog.getText(self, "封面", "副标题：")
        author, _ = QInputDialog.getText(self, "封面", "单位/作者：")
        cursor = self.rich_editor.textCursor()
        cursor.movePosition(QTextCursor.Start)
        cursor.beginEditBlock()
        try:
            for text, size, bold in (
                (title, 28, True),
                (subtitle, 16, False),
                (author, 14, False),
            ):
                if not text.strip():
                    continue
                cursor.insertBlock()
                bf = QTextBlockFormat()
                bf.setAlignment(Qt.AlignHCenter)
                cursor.setBlockFormat(bf)
                cf = QTextCharFormat()
                cf.setFontPointSize(size)
                cf.setFontWeight(QFont.Bold if bold else QFont.Normal)
                cursor.insertText(text, cf)
            # 封面后分页
            cursor.insertBlock()
            pb = QTextBlockFormat()
            pb.setPageBreakPolicy(QTextBlockFormat.PageBreak_AlwaysBefore)
            cursor.setBlockFormat(pb)
        finally:
            cursor.endEditBlock()
        self._set_status("已插入封面", 2000)

    def _set_page_background(self):
        from PySide6.QtGui import QColor
        color = QColorDialog.getColor(QColor("#FFFFFF"), self, "页面背景色")
        if not color.isValid():
            return
        self._page_background = color.name()
        self.rich_editor.setStyleSheet(
            f"QTextEdit{{background-color:{color.name()};}}"
        )
        self._set_status(f"页面背景色：{color.name()}", 2000)

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

    def _show_header_footer_dialog(self):
        """页眉页脚对话框：首页不同/奇偶页不同。"""
        dlg = QDialog(self)
        dlg.setWindowTitle("页眉页脚")
        form = QFormLayout(dlg)
        header = QLineEdit(getattr(self, "_header_text", ""))
        footer = QLineEdit(getattr(self, "_footer_text", ""))
        first_header = QLineEdit(getattr(self, "_header_first_text", ""))
        even_header = QLineEdit(getattr(self, "_header_even_text", ""))
        even_footer = QLineEdit(getattr(self, "_footer_even_text", ""))
        first_diff = QCheckBox("首页不同")
        first_diff.setChecked(bool(getattr(self, "_different_first_page", False)))
        odd_even = QCheckBox("奇偶页不同")
        odd_even.setChecked(bool(getattr(self, "_odd_even_pages", False)))
        form.addRow("页眉", header)
        form.addRow("页脚", footer)
        form.addRow(first_diff)
        form.addRow("首页页眉", first_header)
        form.addRow(odd_even)
        form.addRow("偶数页页眉", even_header)
        form.addRow("偶数页页脚", even_footer)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() != QDialog.Accepted:
            return
        self._header_text = header.text().strip()
        self._footer_text = footer.text().strip()
        self._header_first_text = first_header.text().strip()
        self._header_even_text = even_header.text().strip()
        self._footer_even_text = even_footer.text().strip()
        self._different_first_page = first_diff.isChecked()
        self._odd_even_pages = odd_even.isChecked()
        self._set_status("页眉页脚设置已更新（导出 Word/PDF 生效）", 3000)

    def _apply_header_footer_to_section(self, section, meta):
        """把单节页眉页脚设置写入指定 section。"""
        if not section or not meta:
            return
        header = meta.get("header", "")
        footer = meta.get("footer", "")
        if header:
            try:
                section.header.is_linked_to_previous = False
            except Exception:
                pass
            section.header.paragraphs[0].text = header
        if footer:
            try:
                section.footer.is_linked_to_previous = False
            except Exception:
                pass
            section.footer.paragraphs[0].text = footer
        if meta.get("header_images"):
            try:
                section.header.is_linked_to_previous = False
            except Exception:
                pass
        for img in meta.get("header_images", []) or []:
            try:
                if Path(img).is_file():
                    section.header.paragraphs[0].add_run().add_picture(img)
            except Exception:
                pass
        if meta.get("footer_images"):
            try:
                section.footer.is_linked_to_previous = False
            except Exception:
                pass
        for img in meta.get("footer_images", []) or []:
            try:
                if Path(img).is_file():
                    section.footer.paragraphs[0].add_run().add_picture(img)
            except Exception:
                pass
        if meta.get("different_first_page"):
            section.different_first_page_header_footer = True
            first = meta.get("header_first", "") or header
            if first:
                section.first_page_header.paragraphs[0].text = first

    def _apply_header_footer(self, doc):
        """
        把内存里的页眉/页脚写入 python-docx 文档的节。

        :param doc: python-docx Document
        :return: 是否实际写入
        """
        header_text = getattr(self, "_header_text", "") or ""
        footer_text = getattr(self, "_footer_text", "") or ""
        first_cfg = (getattr(self, "_section_page_settings", []) or [{}])[0]
        header_images = getattr(self, "_header_images", None) or first_cfg.get("header_images", [])
        footer_images = getattr(self, "_footer_images", None) or first_cfg.get("footer_images", [])
        if (not header_text and not footer_text
                and not header_images and not footer_images):
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
            for img in header_images or []:
                try:
                    if Path(img).is_file():
                        section.header.paragraphs[0].add_run().add_picture(img, width=None)
                except Exception:
                    pass
            if footer_text:
                para = section.footer.paragraphs[0]
                para.text = footer_text
                para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            if footer_images:
                try:
                    section.footer.is_linked_to_previous = False
                except Exception:
                    pass
            for img in footer_images or []:
                try:
                    if Path(img).is_file():
                        section.footer.paragraphs[0].add_run().add_picture(img)
                except Exception:
                    pass
            if getattr(self, "_different_first_page", False):
                section.different_first_page_header_footer = True
                first = getattr(self, "_header_first_text", "") or header_text
                if first:
                    section.first_page_header.paragraphs[0].text = first
            if getattr(self, "_odd_even_pages", False):
                try:
                    doc.settings.odd_and_even_pages_header_footer = True
                    even_h = getattr(self, "_header_even_text", "") or header_text
                    even_f = getattr(self, "_footer_even_text", "") or footer_text
                    if even_h:
                        section.even_page_header.paragraphs[0].text = even_h
                    if even_f:
                        section.even_page_footer.paragraphs[0].text = even_f
                except Exception as e:  # noqa: BLE001
                    logging.error(f"写入奇偶页页眉失败: {e}")
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

    def _insert_section_break(self):
        """插入分节符（下一页），导出 DOCX 时生成新 section。"""
        from PySide6.QtGui import QTextBlockFormat, QTextFormat, QTextCursor
        cursor = self.rich_editor.textCursor()
        cursor.beginEditBlock()
        try:
            cursor.insertBlock()
            bf = QTextBlockFormat()
            bf.setProperty(QTextFormat.UserProperty, 0xBEE2)
            cursor.setBlockFormat(bf)
        finally:
            cursor.endEditBlock()
        self._set_status("已插入分节符", 2000)

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

        # ---------- 版式 ----------
        layout_group = QGroupBox("版式")
        layout_form = QFormLayout(layout_group)
        columns_spin = QSpinBox()
        columns_spin.setRange(1, 4)
        columns_spin.setValue(int(self._page_settings.get("columns", 1)))
        layout_form.addRow("分栏:", columns_spin)
        line_numbers = QCheckBox("显示行号")
        line_numbers.setChecked(bool(self._page_settings.get("line_numbers", False)))
        layout_form.addRow(line_numbers)
        layout.addWidget(layout_group)

        # ---------- 页面边框 ----------
        border_group = QGroupBox("页面边框")
        border_form = QFormLayout(border_group)
        border_check = QCheckBox("显示页面边框")
        border_check.setChecked(bool(self._page_settings.get("page_border", False)))
        border_form.addRow(border_check)
        border_color = QLineEdit(self._page_settings.get("page_border_color", "#000000"))
        border_form.addRow("边框颜色:", border_color)
        border_width = QSpinBox()
        border_width.setRange(1, 12)
        border_width.setValue(int(self._page_settings.get("page_border_width", 4)))
        border_form.addRow("边框宽度:", border_width)
        layout.addWidget(border_group)

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
            self._page_settings["columns"] = columns_spin.value()
            self._page_settings["line_numbers"] = line_numbers.isChecked()
            self._page_settings["page_border"] = border_check.isChecked()
            self._page_settings["page_border_color"] = border_color.text().strip() or "#000000"
            self._page_settings["page_border_width"] = border_width.value()

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
