# beeoffice/plugins/beewrite_plugin.py
"""
蜜写插件：将 BeeWriteEditor 包装为符合 Plugin 基类的插件

v5.0.1 修复：
  - P0-9：generate_toc 方法名从 _generate_toc 改为 _insert_toc
          （BeeWriteEditor 实际方法名为 _insert_toc，原实现恒走
           "当前编辑器不支持生成目录" 分支）
  - P1-15：ai_continue / ai_polish / ai_summarize 三个 fallback 方法
           改用 editor._get_active_editor() 定位当前活动编辑器，
           修复原实现直接访问 editor.editor（始终返回 markdown_editor）
           导致富文本模式下 AI 功能作用在错误的控件上
"""
import logging
from datetime import datetime

from PySide6.QtWidgets import QWidget, QMessageBox, QFileDialog

from beeoffice.plugin_base import Plugin


class BeeWritePlugin(Plugin):
    """蜜写插件"""

    name = "蜜写 BeeWrite"
    version = "1.0"
    description = "Markdown 编辑与 Word/PDF/HTML 导出"
    author = "TomJerryGit"

    def __init__(self, parent=None):
        super().__init__(parent)

    # ---------- 创建控件 ----------
    def create_widget(self, parent=None) -> QWidget:
        """创建蜜写编辑器实例"""
        from beeoffice.plugins.beewrite import BeeWriteEditor
        return BeeWriteEditor(parent or self.parent)

    # ---------- 命令注册 ----------
    def register_commands(self, palette):
        """注册蜜写相关命令到命令面板"""
        palette.register_command(
            "蜜写：新建文档",
            "创建一个新的蜜写 Markdown 文档",
            self.new_document
        )
        palette.register_command(
            "蜜写：新建 Word 文档",
            "创建一个默认的 Word 文档",
            self.new_word_document
        )
        palette.register_command(
            "蜜写：导出 DOCX",
            "将当前蜜写文档导出为 Word",
            self.export_docx
        )
        palette.register_command(
            "蜜写：导出 PDF",
            "将当前蜜写文档导出为 PDF",
            self.export_pdf
        )
        palette.register_command(
            "蜜写：导出 HTML",
            "将当前蜜写文档导出为 HTML",
            self.export_html
        )
        palette.register_command(
            "蜜写：插入目录",
            "根据标题自动生成目录",
            self.generate_toc
        )
        palette.register_command(
            "蜜写：AI 续写",
            "基于当前文本续写内容",
            self.ai_continue
        )
        palette.register_command(
            "蜜写：AI 润色",
            "润色选中文本",
            self.ai_polish
        )
        palette.register_command(
            "蜜写：AI 总结",
            "总结当前文档",
            self.ai_summarize
        )

    # ---------- 新建文档 ----------
    def new_document(self) -> QWidget:
        """新建一个蜜写文档并添加为标签页"""
        editor = self.create_widget()
        timestamp = datetime.now().strftime("%H%M")
        self.parent.tab_manager.addTab(editor, f"📝 蜜写-{timestamp}")
        self.parent.tab_manager.setCurrentWidget(editor)
        return editor

    def new_word_document(self) -> QWidget:
        """新建一个默认内容的 Word 文档"""
        editor = self.create_widget()
        if hasattr(editor, "set_content"):
            editor.set_content("# 新建文档\n\n在此输入内容...")
        # 如果编辑器支持富文本模式
        if hasattr(editor, "_switch_mode"):
            try:
                editor._switch_mode("rich_text")
            except Exception as e:
                logging.warning(f"切换到富文本模式失败: {e}")
        timestamp = datetime.now().strftime("%H%M")
        self.parent.tab_manager.addTab(editor, f"📝 Word-{timestamp}")
        self.parent.tab_manager.setCurrentWidget(editor)
        if hasattr(self.parent, "set_global_status"):
            self.parent.set_global_status("Word 文档已创建", 5000)
        return editor

    # ---------- 获取当前编辑器 ----------
    def _current_editor(self):
        """返回当前标签页的蜜写编辑器（若非蜜写则返回 None）"""
        widget = self.parent.tab_manager.currentWidget()
        if widget is None:
            return None
        # 通过类名判断是否为 BeeWriteEditor
        from beeoffice.plugins.beewrite import BeeWriteEditor
        if isinstance(widget, BeeWriteEditor):
            return widget
        return None

    # ---------- 导出 ----------
    def export_docx(self):
        """导出当前蜜写文档为 DOCX"""
        editor = self._current_editor()
        if not editor:
            self._warn("请先打开一个蜜写文档")
            return
        if hasattr(editor, "export_docx"):
            editor.export_docx()
        else:
            self._warn("当前编辑器不支持导出 DOCX")

    def export_pdf(self):
        """导出当前蜜写文档为 PDF"""
        editor = self._current_editor()
        if not editor:
            self._warn("请先打开一个蜜写文档")
            return
        if hasattr(editor, "export_pdf"):
            editor.export_pdf()
        else:
            self._warn("当前编辑器不支持导出 PDF")

    def export_html(self):
        """导出当前蜜写文档为 HTML"""
        editor = self._current_editor()
        if not editor:
            self._warn("请先打开一个蜜写文档")
            return
        if hasattr(editor, "export_html"):
            editor.export_html()
        else:
            self._warn("当前编辑器不支持导出 HTML")

    # ---------- 目录（P0-9 修复） ----------
    def generate_toc(self):
        """
        生成目录

        P0-9 修复：
          BeeWriteEditor 的实际方法名是 `_insert_toc`（插入到光标处），
          而非 `_generate_toc`。原实现恒走 else 分支，永远提示
          "当前编辑器不支持生成目录"。
        """
        editor = self._current_editor()
        if not editor:
            self._warn("请先打开一个蜜写文档")
            return

        # 蜜写主编辑器的方法名是 _insert_toc（不是 _generate_toc）
        if hasattr(editor, "_insert_toc"):
            try:
                editor._insert_toc()
            except Exception as e:
                logging.error(f"插入目录失败: {e}")
                QMessageBox.warning(
                    self.parent, "插入目录失败", str(e)
                )
        else:
            self._warn("当前编辑器不支持生成目录")

    # ---------- AI 辅助 ----------
    def ai_continue(self):
        """
        AI 续写

        P1-15：fallback 用 _get_active_editor 定位活动编辑器
                （避免在富文本模式下把内容写进 Markdown 编辑器）
        """
        editor = self._current_editor()
        if not editor:
            self._warn("请先打开一个蜜写文档")
            return
        if hasattr(editor, "_ai_continue"):
            editor._ai_continue()
            return
        # 内置实现（如果编辑器未提供）
        from beeoffice.plugins.ai_assist import AIAssist
        try:
            # P1-15：优先用 _get_active_editor 取当前活动编辑器
            if hasattr(editor, "_get_active_editor"):
                active = editor._get_active_editor()
            else:
                # 兜底：旧版编辑器没有 _get_active_editor 时
                active = editor.editor

            cursor = active.textCursor()
            pos = cursor.position()
            context = active.toPlainText()[:pos][-100:]
            result = AIAssist.continue_text(context)
            addition = (
                result[len(context):]
                if result.startswith(context)
                else result
            )
            cursor.insertText(addition)
        except Exception as e:
            logging.error(f"AI 续写失败: {e}")
            self._warn(f"AI 续写失败: {e}")

    def ai_polish(self):
        """
        AI 润色

        P1-15：fallback 用 _get_active_editor 定位活动编辑器
        """
        editor = self._current_editor()
        if not editor:
            self._warn("请先打开一个蜜写文档")
            return
        if hasattr(editor, "_ai_polish"):
            editor._ai_polish()
            return
        # 内置实现
        from beeoffice.plugins.ai_assist import AIAssist
        from PySide6.QtWidgets import QMessageBox as _QMB
        try:
            # P1-15：用 _get_active_editor
            if hasattr(editor, "_get_active_editor"):
                active = editor._get_active_editor()
            else:
                active = editor.editor

            cursor = active.textCursor()
            if not cursor.hasSelection():
                _QMB.information(
                    self.parent, "提示", "请先选中要润色的文本"
                )
                return
            polished = AIAssist.polish_text(cursor.selectedText())
            cursor.insertText(polished)
        except Exception as e:
            logging.error(f"AI 润色失败: {e}")
            self._warn(f"AI 润色失败: {e}")

    def ai_summarize(self):
        """
        AI 总结

        P1-15：fallback 用 _get_active_editor 定位活动编辑器，
               同时用 editor.content() 获取完整文档内容
        """
        editor = self._current_editor()
        if not editor:
            self._warn("请先打开一个蜜写文档")
            return
        if hasattr(editor, "_ai_summarize"):
            editor._ai_summarize()
            return
        # 内置实现
        from beeoffice.plugins.ai_assist import AIAssist
        from PySide6.QtWidgets import QMessageBox as _QMB
        try:
            # P1-15：用 content() 获取完整文档（不区分模式）
            text = (editor.content()
                    if hasattr(editor, "content")
                    else "")
            if len(text) < 100:
                _QMB.information(
                    self.parent, "提示", "文本太短，无需总结"
                )
                return
            summary = AIAssist.summarize_text(text)

            # P1-15：在活动编辑器里追加
            if hasattr(editor, "_get_active_editor"):
                active = editor._get_active_editor()
            else:
                active = editor.editor
            active.append("\n\n## AI 总结\n\n" + summary)
        except Exception as e:
            logging.error(f"AI 总结失败: {e}")
            self._warn(f"AI 总结失败: {e}")

    # ---------- 辅助 ----------
    def _warn(self, message: str):
        """统一提示"""
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self.parent, "提示", message)

    # ---------- 生命周期 ----------
    def on_close(self):
        """插件关闭时清理"""
        super().on_close()
        logging.info(f"蜜写插件已卸载")