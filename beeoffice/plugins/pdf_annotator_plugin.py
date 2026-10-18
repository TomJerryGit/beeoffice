# beeoffice/plugins/pdf_annotator_plugin.py
"""
PDF 批注插件：将 PDFAnnotator 包装为符合 Plugin 基类的插件
"""
import logging
from pathlib import Path

from PySide6.QtWidgets import QWidget, QMessageBox, QFileDialog
from PySide6.QtCore import Qt

from beeoffice.plugin_base import Plugin
from beeoffice.i18n import tr


class PDFAnnotatorPlugin(Plugin):
    """PDF 批注插件"""

    name = "PDF 批注"
    version = "1.0"
    description = "打开 PDF 文件进行批注、高亮、注释"
    author = "TomJerryGit"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._annotators = []  # 跟踪打开的批注窗口实例

    # ---------- 创建控件 ----------
    def create_widget(self, parent=None) -> QWidget:
        """
        创建 PDF 批注窗口实例。
        注意：PDFAnnotator 通常是独立窗口而非标签页控件，
        此处返回一个新创建的批注窗口，但不会被添加到标签页。
        """
        from beeoffice.plugins.pdf_annotator import PDFAnnotator
        annotator = PDFAnnotator(parent or self.parent)
        # 独立窗口，关闭时自动销毁
        annotator.setAttribute(Qt.WA_DeleteOnClose)
        # 跟踪实例
        annotator.destroyed.connect(
            lambda obj=None, a=annotator: self._remove_annotator(a)
        )
        self._annotators.append(annotator)
        return annotator

    def _remove_annotator(self, annotator):
        """从跟踪列表中移除已销毁的批注窗口"""
        try:
            if annotator in self._annotators:
                self._annotators.remove(annotator)
        except Exception:
            pass

    # ---------- 命令注册 ----------
    def register_commands(self, palette):
        """注册 PDF 批注相关命令到命令面板"""
        palette.register_command(
            tr("auto.pdf_annotator_plugin.b83ed594", "PDF：打开并批注"),
            tr("auto.pdf_annotator_plugin.3141ac58", "选择 PDF 文件并打开批注工具"),
            self.open_pdf_dialog
        )
        palette.register_command(
            tr("auto.pdf_annotator_plugin.b1ab16ef", "PDF：打开最近的批注"),
            tr("auto.pdf_annotator_plugin.4a11fe5b", "重新打开最近一次编辑的 PDF"),
            self.reopen_last_pdf
        )
        palette.register_command(
            tr("auto.pdf_annotator_plugin.66a730d6", "PDF：关闭全部批注窗口"),
            tr("auto.pdf_annotator_plugin.a75e982f", "关闭所有已打开的 PDF 批注窗口"),
            self.close_all_annotators
        )

    # ---------- 打开 PDF ----------
    def open_pdf_dialog(self):
        """弹出文件对话框，选择 PDF 后打开批注器"""
        path, _ = QFileDialog.getOpenFileName(
            self.parent,
            tr("auto.pdf_annotator_plugin.b977bc33", "打开 PDF 文件"),
            "",
            tr("auto.pdf_annotator_plugin.2a20c779", "PDF 文件 (*.pdf);;所有文件 (*)")
        )
        if not path:
            return
        self.open_pdf(path)

    def open_pdf(self, filepath: str):
        """
        打开指定路径的 PDF 文件进行批注
        :param filepath: PDF 文件路径
        """
        # 校验文件
        if not filepath:
            self._warn("未指定 PDF 文件")
            return
        if not Path(filepath).exists():
            self._warn(f"文件不存在：\n{filepath}")
            return
        if not filepath.lower().endswith(".pdf"):
            self._warn("仅支持 PDF 格式文件")
            return

        # 创建批注窗口
        try:
            from beeoffice.plugins.pdf_annotator import PDFAnnotator
            annotator = PDFAnnotator()
            annotator.setAttribute(Qt.WA_DeleteOnClose)
            annotator.open_pdf(filepath)

            # 跟踪实例
            annotator.destroyed.connect(
                lambda obj=None, a=annotator: self._remove_annotator(a)
            )
            self._annotators.append(annotator)

            # 显示窗口
            annotator.show()
            annotator.raise_()
            annotator.activateWindow()

            # 记录到最近文件列表
            if hasattr(self.parent, "settings"):
                try:
                    self.parent.settings.add_recent_file(filepath)
                    if hasattr(self.parent, "_update_recent_menu"):
                        self.parent._update_recent_menu()
                except Exception as e:
                    logging.warning(tr("auto.pdf_annotator_plugin.5769ad88", "更新最近文件失败: {e}").format(e=e))

            # 状态栏提示
            if hasattr(self.parent, "set_global_status"):
                self.parent.set_global_status(
                    tr("auto.pdf_annotator_plugin.4b543708", "已打开 PDF: {0}").format(Path(filepath).name), 3000
                )

            logging.info(f"已打开 PDF 批注: {filepath}")
        except ImportError as e:
            logging.error(f"PDF 批注模块不可用: {e}")
            QMessageBox.warning(
                self.parent, tr("auto.pdf_annotator_plugin.c804173e", "无法打开"),
                tr("auto.pdf_annotator_plugin.45aea6aa", "PDF 批注模块不可用：\n{e}\n\n请确认已安装 PyMuPDF 依赖。").format(e=e)
            )
        except Exception as e:
            logging.error(f"打开 PDF 失败: {e}")
            QMessageBox.warning(self.parent, tr("auto.pdf_annotator_plugin.e1ae8ece", "打开失败"), str(e))

    # ---------- 重新打开最近的 PDF ----------
    def reopen_last_pdf(self):
        """重新打开最近一次编辑的 PDF"""
        recent_pdf = self._find_last_pdf()
        if not recent_pdf:
            self._warn("没有最近打开的 PDF 文件")
            return
        if not Path(recent_pdf).exists():
            self._warn(f"最近的文件已不存在：\n{recent_pdf}")
            return
        self.open_pdf(recent_pdf)

    def _find_last_pdf(self):
        """从最近文件列表中查找最新的 PDF"""
        if not hasattr(self.parent, "settings"):
            return None
        for path in getattr(self.parent.settings, "recent_files", []):
            if path.lower().endswith(".pdf") and Path(path).exists():
                return path
        return None

    # ---------- 关闭所有批注窗口 ----------
    def close_all_annotators(self):
        """关闭所有已打开的 PDF 批注窗口"""
        if not self._annotators:
            self._warn("没有已打开的 PDF 批注窗口")
            return

        count = len(self._annotators)
        for annotator in list(self._annotators):
            try:
                annotator.close()
            except Exception as e:
                logging.warning(tr("auto.pdf_annotator_plugin.5865f3e5", "关闭批注窗口失败: {e}").format(e=e))
        self._annotators.clear()
        if hasattr(self.parent, "set_global_status"):
            self.parent.set_global_status(tr("auto.pdf_annotator_plugin.ccab2adc", "已关闭 {count} 个批注窗口").format(count=count), 2000)

    # ---------- 当前活动批注窗口 ----------
    def _get_active_annotator(self):
        """返回当前活动（可见且激活）的批注窗口"""
        for annotator in self._annotators:
            try:
                if annotator.isVisible() and annotator.isActiveWindow():
                    return annotator
            except Exception:
                continue
        return None

    def get_open_count(self) -> int:
        """返回当前打开的批注窗口数"""
        return len(self._annotators)

    # ---------- 辅助 ----------
    def _warn(self, message: str):
        """统一提示"""
        QMessageBox.information(self.parent, tr("auto.pdf_annotator_plugin.ab3656a9", "提示"), message)

    # ---------- 生命周期 ----------
    def on_close(self):
        """插件关闭时清理所有批注窗口"""
        try:
            for annotator in list(self._annotators):
                try:
                    annotator.close()
                except Exception:
                    pass
            self._annotators.clear()
        except Exception as e:
            logging.error(f"清理批注窗口失败: {e}")
        super().on_close()
        logging.info("PDF 批注插件已卸载")