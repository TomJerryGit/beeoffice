# beeoffice/plugins/beewrite_link_mixin.py
"""
蜜写链接 / 交叉引用 / 插入对象 Mixin

职责：
  - 超链接
    * _insert_hyperlink           : 插入超链接（Markdown 模式 / 富文本模式均支持）
    * _show_hyperlink_manager     : 超链接管理对话框
  - 交叉引用
    * _show_crossref_dialog       : 引用文档中的标题
  - 插入图片
    * _insert_image               : 打开图片编辑对话框 + 插入
  - 插入数学公式
    * _insert_formula             : 打开公式编辑对话框 + 插入
  - 插入文本框
    * _insert_textbox             : 插入带背景色的静态文本框

依赖：
  - PySide6（QMessageBox / QDialog / QVBoxLayout / QFormLayout /
             QComboBox / QListWidget / QListWidgetItem / QHBoxLayout /
             QPushButton / QLabel / QTextCursor / QTextCharFormat /
             QColor / QImage / QTextImageFormat）
  - beewrite_hyperlink（HyperlinkDialog / HyperlinkManagerDialog）
  - beewrite_image（ImageEditorDialog）
  - beewrite_formula（FormulaDialog）
  - beewrite_textbox（TextBoxDialog / insert_textbox）

说明：
  - 本 Mixin 处理「插入外部对象」的全部入口。
  - 图片 / 公式以临时文件形式保存后通过 QTextImageFormat 插入。
  - 不导入其他 beewrite_* Mixin，避免循环依赖。
"""
import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QMessageBox,
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QComboBox,
    QListWidget,
    QListWidgetItem,
    QHBoxLayout,
    QPushButton,
    QLabel,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QColor,
    QImage,
    QTextCursor,
    QTextCharFormat,
    QTextImageFormat,
)

from beeoffice.plugins.beewrite_hyperlink import (
    HyperlinkDialog,
    HyperlinkManagerDialog,
)
from beeoffice.plugins.beewrite_image import ImageEditorDialog
from beeoffice.plugins.beewrite_formula import FormulaDialog
from beeoffice.plugins.beewrite_textbox import TextBoxDialog, insert_textbox
from beeoffice.i18n import tr


# ==================== LinkMixin ====================
class LinkMixin:
    """蜜写链接 / 交叉引用 / 插入对象 Mixin"""

    # ==================================================================
    # 超链接：插入
    # ==================================================================
    def _insert_hyperlink(self):
        """
        插入超链接：
          - Markdown 模式：插入 `[文本](URL)` 语法
          - 富文本模式：使用 QTextCharFormat 应用锚点格式
        """
        if self._edit_mode == "markdown":
            # Markdown 模式：直接插入语法
            selected = self.markdown_editor.textCursor().selectedText()
            dlg = HyperlinkDialog(self, initial_text=selected or "")
            if dlg.exec() != QDialog.Accepted:
                return
            text = dlg.get_text() or dlg.get_url()
            url = dlg.get_url()
            self.markdown_editor.insertPlainText(f"[{text}]({url})")
        else:
            # 富文本模式：使用锚点格式
            selected = self.rich_editor.textCursor().selectedText()
            dlg = HyperlinkDialog(self, initial_text=selected or "")
            if dlg.exec() != QDialog.Accepted:
                return
            text = dlg.get_text() or dlg.get_url()
            url = dlg.get_url()
            cursor = self.rich_editor.textCursor()
            fmt = QTextCharFormat()
            fmt.setAnchor(True)
            fmt.setAnchorHref(url)
            fmt.setForeground(QColor("#1565C0"))
            fmt.setFontUnderline(True)
            cursor.insertText(text, fmt)

    # ==================================================================
    # 超链接：管理
    # ==================================================================
    def _show_hyperlink_manager(self):
        """打开超链接管理对话框（列出 / 跳转 / 编辑 / 移除）"""
        if self._edit_mode != "rich_text":
            QMessageBox.information(
                self, tr("auto.beewrite_link_mixin.ab3656a9", "提示"), tr("auto.beewrite_link_mixin.09b3badd", "请先切换到所见即所得模式")
            )
            return
        dlg = HyperlinkManagerDialog(self.rich_editor, self)
        dlg.exec()

    # ==================================================================
    # 交叉引用
    # ==================================================================
    def _show_crossref_dialog(self):
        """打开交叉引用对话框（引用文档中的标题）"""
        if self._edit_mode != "rich_text":
            QMessageBox.information(
                self, tr("auto.beewrite_link_mixin.ab3656a9", "提示"), tr("auto.beewrite_link_mixin.09b3badd", "请先切换到所见即所得模式")
            )
            return

        # 扫描当前文档标题
        try:
            headings = self._crossref_manager.scan_headings(
                self.rich_editor
            )
        except Exception as e:
            logging.error(f"扫描标题失败: {e}")
            QMessageBox.warning(self, tr("auto.beewrite_link_mixin.3e3c8068", "失败"), tr("auto.beewrite_link_mixin.172771ca", "扫描标题失败：\n{e}").format(e=e))
            return

        if not headings:
            QMessageBox.information(
                self,
                tr("auto.beewrite_link_mixin.ab3656a9", "提示"),
                "文档中没有标题。\n"
                "请先用「样式」下拉框把段落设为标题。",
            )
            return

        # ---------- 对话框 ----------
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("auto.beewrite_link_mixin.7d7a59b5", "🔢 交叉引用"))
        dlg.resize(480, 420)

        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel(tr("auto.beewrite_link_mixin.c7dd965f", "选择要引用的标题：")))

        # ---------- 标题列表 ----------
        lst = QListWidget()
        lst.setStyleSheet(
            "QListWidget{border:1px solid #DDD;border-radius:4px;}"
            "QListWidget::item{padding:6px;}"
            "QListWidget::item:selected{background:#FFF3E0;}"
        )
        for h in headings:
            indent = "  " * (h["level"] - 1)
            item_text = f"{indent}{h['number']}  {h['text']}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, h)
            lst.addItem(item)
        layout.addWidget(lst, 1)

        # ---------- 引用方式 ----------
        form = QFormLayout()
        mode_combo = QComboBox()
        mode_combo.addItems([
            "编号（如 1.1）",
            "标题文字（如 研究背景）",
            "编号+标题（如 1.1 研究背景）",
        ])
        form.addRow("引用方式:", mode_combo)
        layout.addLayout(form)

        # ---------- 按钮栏 ----------
        bl = QHBoxLayout()
        btn_insert = QPushButton(tr("auto.beewrite_link_mixin.7fa8aacd", "插入引用"))
        btn_insert.setStyleSheet(
            "QPushButton{background:#FFB300;color:#000;"
            "padding:6px 16px;border:none;border-radius:4px;"
            "font-weight:bold;}"
            "QPushButton:hover{background:#FFA000;}"
        )

        def do_insert():
            item = lst.currentItem()
            if not item:
                QMessageBox.information(
                    dlg, tr("auto.beewrite_link_mixin.ab3656a9", "提示"), tr("auto.beewrite_link_mixin.25f5613d", "请先选择一个标题")
                )
                return
            h = item.data(Qt.UserRole)

            mode = mode_combo.currentText()
            if mode.startswith("编号（"):
                text = h["number"]
            elif mode.startswith("标题文字"):
                text = h["text"]
            else:
                text = f"{h['number']} {h['text']}"

            cursor = self.rich_editor.textCursor()
            cursor.insertText(text)
            self._set_status(tr("auto.beewrite_link_mixin.ae044aca", "✅ 已插入引用：{text}").format(text=text), 2000)
            dlg.accept()

        btn_insert.clicked.connect(do_insert)
        bl.addWidget(btn_insert)

        # ---------- 刷新 ----------
        btn_refresh = QPushButton(tr("auto.beewrite_link_mixin.97f2d6e4", "🔄 刷新标题列表"))

        def do_refresh():
            new_headings = self._crossref_manager.scan_headings(
                self.rich_editor
            )
            lst.clear()
            for h in new_headings:
                indent = "  " * (h["level"] - 1)
                item = QListWidgetItem(
                    f"{indent}{h['number']}  {h['text']}"
                )
                item.setData(Qt.UserRole, h)
                lst.addItem(item)
            self._set_status(tr("auto.beewrite_link_mixin.f4f7d36a", "✅ 已刷新标题列表"), 2000)

        btn_refresh.clicked.connect(do_refresh)
        bl.addWidget(btn_refresh)

        bl.addStretch()

        btn_close = QPushButton(tr("auto.beewrite_link_mixin.6c14bd7f", "关闭"))
        btn_close.clicked.connect(dlg.reject)
        bl.addWidget(btn_close)

        layout.addLayout(bl)
        dlg.exec()

    # ==================================================================
    # 插入图片
    # ==================================================================
    def _insert_image(self):
        """打开图片编辑对话框，将处理后的图片插入文档"""
        if self._edit_mode != "rich_text":
            QMessageBox.information(
                self, tr("auto.beewrite_link_mixin.ab3656a9", "提示"), tr("auto.beewrite_link_mixin.09b3badd", "请先切换到所见即所得模式")
            )
            return

        # ---------- 打开编辑对话框 ----------
        dlg = ImageEditorDialog(parent=self)
        if dlg.exec() != QDialog.Accepted:
            return

        result_path = dlg.get_result_path()
        if not result_path or not Path(result_path).exists():
            return

        # ---------- 插入 ----------
        try:
            img = QImage(result_path)
            if img.isNull():
                QMessageBox.warning(self, tr("auto.beewrite_link_mixin.3e3c8068", "失败"), tr("auto.beewrite_link_mixin.cf3d2153", "无法加载图片"))
                return

            cursor = self.rich_editor.textCursor()
            cursor.insertBlock()

            fmt = QTextImageFormat()
            fmt.setName(result_path)
            # 宽度超过 600px 时按比例缩小
            if img.width() > 600:
                ratio = 600 / img.width()
                fmt.setWidth(int(img.width() * ratio))
                fmt.setHeight(int(img.height() * ratio))

            cursor.insertImage(fmt)
            cursor.insertBlock()

            self._set_status(
                tr("auto.beewrite_link_mixin.a89305f0", "✅ 已插入图片（{0}×{1}）").format(img.width(), img.height()), 3000
            )
        except Exception as e:
            logging.error(f"插入图片失败: {e}")
            QMessageBox.warning(self, tr("auto.beewrite_link_mixin.4620fab0", "插入失败"), str(e))

    # ==================================================================
    # 插入数学公式
    # ==================================================================
    def _insert_formula(self):
        """打开公式编辑对话框，将渲染后的公式图片插入文档"""
        if self._edit_mode != "rich_text":
            QMessageBox.information(
                self, tr("auto.beewrite_link_mixin.ab3656a9", "提示"), tr("auto.beewrite_link_mixin.09b3badd", "请先切换到所见即所得模式")
            )
            return

        dlg = FormulaDialog(parent=self)
        if dlg.exec() != QDialog.Accepted:
            return

        result_path = dlg.get_result_path()
        if not result_path or not Path(result_path).exists():
            return

        try:
            img = QImage(result_path)
            if img.isNull():
                QMessageBox.warning(self, tr("auto.beewrite_link_mixin.3e3c8068", "失败"), tr("auto.beewrite_link_mixin.f288af53", "无法加载公式图片"))
                return

            cursor = self.rich_editor.textCursor()
            fmt = QTextImageFormat()
            fmt.setName(result_path)
            # 高度超过 100px 时按比例缩小
            if img.height() > 100:
                ratio = 100 / img.height()
                fmt.setWidth(int(img.width() * ratio))
                fmt.setHeight(100)
            cursor.insertImage(fmt)

            self._set_status(tr("auto.beewrite_link_mixin.40cf58c0", "✅ 已插入公式"), 2000)
        except Exception as e:
            logging.error(f"插入公式失败: {e}")
            QMessageBox.warning(self, tr("auto.beewrite_link_mixin.4620fab0", "插入失败"), str(e))

    # ==================================================================
    # 插入文本框
    # ==================================================================
    def _insert_textbox(self):
        """插入带背景色的静态文本框（基于 QTextFrame）"""
        if self._edit_mode != "rich_text":
            QMessageBox.information(
                self, tr("auto.beewrite_link_mixin.ab3656a9", "提示"), tr("auto.beewrite_link_mixin.09b3badd", "请先切换到所见即所得模式")
            )
            return
        dlg = TextBoxDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            insert_textbox(self.rich_editor, dlg.get_config())
            self._set_status(tr("auto.beewrite_link_mixin.ca378b18", "✅ 已插入文本框"), 2000)
        except Exception as e:
            logging.error(f"插入文本框失败: {e}")
            QMessageBox.warning(self, tr("auto.beewrite_link_mixin.4620fab0", "插入失败"), str(e))