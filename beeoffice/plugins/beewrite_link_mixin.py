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
  - 图片 / 公式由各自对话框渲染成图片文件后，经 `_persist_media_to_document()`
    落到"文档旁边"的稳定目录，再用 QTextImageFormat 插入
    （优化规划 §2.6：此前直接使用 %TEMP% 路径，见该方法说明）。
  - 不导入其他 beewrite_* Mixin，避免循环依赖。
"""
import logging
import shutil
import uuid
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
    QTextCharFormat,
    QTextImageFormat,
)

from beeoffice.plugins.beewrite_hyperlink import (
    HyperlinkDialog,
    HyperlinkManagerDialog,
)
from beeoffice.plugins.beewrite_image import (
    ImageEditorDialog,
    IMAGE_WRAP_PROPERTY,
)
from beeoffice.plugins.beewrite_formula import FormulaDialog
from beeoffice.plugins.beewrite_textbox import TextBoxDialog, insert_textbox


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
                self, "提示", "请先切换到所见即所得模式"
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
                self, "提示", "请先切换到所见即所得模式"
            )
            return

        # 扫描当前文档标题
        try:
            headings = self._crossref_manager.scan_headings(
                self.rich_editor
            )
        except Exception as e:
            logging.error(f"扫描标题失败: {e}")
            QMessageBox.warning(self, "失败", f"扫描标题失败：\n{e}")
            return

        if not headings:
            QMessageBox.information(
                self,
                "提示",
                "文档中没有标题。\n"
                "请先用「样式」下拉框把段落设为标题。",
            )
            return

        # ---------- 对话框 ----------
        dlg = QDialog(self)
        dlg.setWindowTitle("🔢 交叉引用")
        dlg.resize(480, 420)

        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("选择要引用的标题："))

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
        btn_insert = QPushButton("插入引用")
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
                    dlg, "提示", "请先选择一个标题"
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
            self._set_status(f"✅ 已插入引用：{text}", 2000)
            dlg.accept()

        btn_insert.clicked.connect(do_insert)
        bl.addWidget(btn_insert)

        # ---------- 刷新 ----------
        btn_refresh = QPushButton("🔄 刷新标题列表")

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
            self._set_status("✅ 已刷新标题列表", 2000)

        btn_refresh.clicked.connect(do_refresh)
        bl.addWidget(btn_refresh)

        bl.addStretch()

        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(dlg.reject)
        bl.addWidget(btn_close)

        layout.addLayout(bl)
        dlg.exec()

    # ==================================================================
    # 媒体落盘（优化规划 §2.6）
    # ==================================================================
    def _persist_media_to_document(self, temp_path: str) -> str:
        """
        把临时目录里的图片 / 公式图片搬进"文档旁边"的稳定目录。

        原缺陷（数据丢失）：插入图片与插入公式都只把渲染结果写到系统临时目录
        （`%TEMP%/beeoffice_images/`、`%TEMP%/beeoffice_formulas/`），然后把那个
        **绝对临时路径**写进文档。后果：
          - `%TEMP%` 会被系统清理（存储感知 / 磁盘清理 / 重启），文档里的图片
            之后就永久失效；
          - 临时路径只在本机有效，文档拷到别的电脑上图片全部打不开。
        而 `import_from_docx` 导入图片时已经是"导出到 <文档名>_media/ 并用相对
        路径引用"，两条路径行为不一致。

        现在统一为：
          - 文档已保存 → `<文档目录>/<文档名>_media/`
          - 文档尚未保存 → 应用数据目录 `media/<随机 8 位>/`
            （比 %TEMP% 稳定得多，但仍建议尽快保存文档以获得可随文档分发的路径）

        采用**复制**而非移动，避免影响对话框自身的结果文件。

        :return: 可安全写入文档的新路径；无法落盘时返回原路径
        """
        src = Path(temp_path) if temp_path else None
        if src is None or not src.exists():
            return temp_path
        try:
            doc_path = getattr(self, "_current_file_path", None)
            if doc_path:
                target_dir = (
                    Path(doc_path).parent / f"{Path(doc_path).stem}_media"
                )
            else:
                from beeoffice.utils import get_app_data_dir
                target_dir = (
                    Path(get_app_data_dir()) / "media" / uuid.uuid4().hex[:8]
                )

            target_dir.mkdir(parents=True, exist_ok=True)
            dst = target_dir / src.name
            # 同名但内容不同时另起名字，避免覆盖用户已有的同名图片
            suffix = 1
            while dst.exists() and dst.stat().st_size != src.stat().st_size:
                dst = target_dir / f"{src.stem}_{suffix}{src.suffix}"
                suffix += 1
            if not dst.exists():
                shutil.copy2(src, dst)
            logging.info(f"媒体已落盘到文档目录: {dst}")
            return str(dst)
        except Exception as e:
            logging.warning(f"媒体文件落盘失败，仍使用临时路径: {e}")
            return temp_path

    # ==================================================================
    # 插入图片
    # ==================================================================
    def _insert_image(self):
        """打开图片编辑对话框，将处理后的图片插入文档"""
        if self._edit_mode != "rich_text":
            QMessageBox.information(
                self, "提示", "请先切换到所见即所得模式"
            )
            return

        # ---------- 打开编辑对话框 ----------
        dlg = ImageEditorDialog(parent=self)
        if dlg.exec() != QDialog.Accepted:
            return

        result_path = self._persist_media_to_document(dlg.get_result_path())
        if not result_path or not Path(result_path).exists():
            return

        # ---------- 插入 ----------
        try:
            img = QImage(result_path)
            if img.isNull():
                QMessageBox.warning(self, "失败", "无法加载图片")
                return

            cursor = self.rich_editor.textCursor()
            cursor.insertBlock()

            fmt = QTextImageFormat()
            fmt.setName(result_path)
            fmt.setProperty(IMAGE_WRAP_PROPERTY, dlg.wrap_mode())
            # 宽度超过 600px 时按比例缩小
            if img.width() > 600:
                ratio = 600 / img.width()
                fmt.setWidth(int(img.width() * ratio))
                fmt.setHeight(int(img.height() * ratio))

            cursor.insertImage(fmt)
            cursor.insertBlock()

            self._set_status(
                f"✅ 已插入图片（{img.width()}×{img.height()}）", 3000
            )
        except Exception as e:
            logging.error(f"插入图片失败: {e}")
            QMessageBox.warning(self, "插入失败", str(e))

    # ==================================================================
    # 插入数学公式
    # ==================================================================
    def _insert_formula(self):
        """打开公式编辑对话框，将渲染后的公式图片插入文档"""
        if self._edit_mode != "rich_text":
            QMessageBox.information(
                self, "提示", "请先切换到所见即所得模式"
            )
            return

        dlg = FormulaDialog(parent=self)
        if dlg.exec() != QDialog.Accepted:
            return

        result_path = self._persist_media_to_document(dlg.get_result_path())
        if not result_path or not Path(result_path).exists():
            return

        try:
            img = QImage(result_path)
            if img.isNull():
                QMessageBox.warning(self, "失败", "无法加载公式图片")
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

            self._set_status("✅ 已插入公式", 2000)
        except Exception as e:
            logging.error(f"插入公式失败: {e}")
            QMessageBox.warning(self, "插入失败", str(e))

    # ==================================================================
    # 插入文本框
    # ==================================================================
    def _insert_textbox(self):
        """插入带背景色的静态文本框（基于 QTextFrame）"""
        if self._edit_mode != "rich_text":
            QMessageBox.information(
                self, "提示", "请先切换到所见即所得模式"
            )
            return
        dlg = TextBoxDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            insert_textbox(self.rich_editor, dlg.get_config())
            self._set_status("✅ 已插入文本框", 2000)
        except Exception as e:
            logging.error(f"插入文本框失败: {e}")
            QMessageBox.warning(self, "插入失败", str(e))