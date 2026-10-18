# beeoffice/plugins/beewrite_ai_mixin.py
"""
蜜写 AI 辅助 Mixin

职责：
  - _show_ai_menu      : 弹出 AI 菜单（续写 / 润色 / 总结 / 关键词）
  - _ai_continue       : 基于光标前文继续写作
  - _ai_polish         : 润色选中的文字
  - _ai_summarize      : 总结当前文档并插入到文末
  - _ai_keywords       : 提取关键词并插入到文末

依赖：
  - PySide6（QMenu / QMessageBox）
  - beeoffice.plugins.ai_assist（延迟 import：AIAssist）

说明：
  - 所有 AI 功能基于规则实现（无外部 API 依赖），详见 ai_assist.py
  - 支持 Markdown 模式与富文本模式，两种模式下均通过 _get_active_editor
    定位到当前活动编辑器
  - 不导入其他 beewrite_* Mixin，避免循环依赖
"""
import logging

from PySide6.QtWidgets import QMenu, QMessageBox


# ==================== AIMixin ====================
class AIMixin:
    """蜜写 AI 辅助 Mixin"""

    # ==================================================================
    # AI 菜单
    # ==================================================================
    def _show_ai_menu(self):
        """弹出 AI 辅助菜单"""
        menu = QMenu(self)
        menu.addAction("✍️ 续写").triggered.connect(self._ai_continue)
        menu.addAction("✨ 润色").triggered.connect(self._ai_polish)
        menu.addAction("📝 总结").triggered.connect(self._ai_summarize)
        menu.addAction("🔑 提取关键词").triggered.connect(self._ai_keywords)
        menu.exec(self._ai_btn.mapToGlobal(
            self._ai_btn.rect().bottomLeft()
        ))

    # ==================================================================
    # AI 续写
    # ==================================================================
    @staticmethod
    def _strip_echoed_context(context: str, result: str) -> str:
        """
        从 AI 返回结果里剥掉被回显的上下文。

        修复（P1-28）：原实现只判断 `result.startswith(context)`。
        上下文是从**句子中间**截取的（末尾 200 字），模型往往会回显
        包含这句的完整句子，于是 startswith 判断失败，
        整段（含已有的上下文）被原样插入 —— 表现为"续写把原文又贴了一遍"。

        现在改为找 context 后缀与 result 前缀的**最长重叠**并剥掉。
        """
        if not result:
            return ""
        if context and result.startswith(context):
            return result[len(context):]
        if context:
            limit = min(len(context), len(result))
            for k in range(limit, 0, -1):
                if context.endswith(result[:k]):
                    return result[k:]
        return result

    def _ai_continue(self):
        """
        AI 续写：基于光标前的 200 个字符作为上下文，
        生成续写内容并插入到光标位置。
        """
        from beeoffice.plugins.ai_assist import AIAssist

        try:
            if self._edit_mode == "rich_text":
                target = self.rich_editor
            else:
                target = self.markdown_editor

            cursor = target.textCursor()
            pos = cursor.position()
            context = target.toPlainText()[:pos][-200:]

            result = AIAssist.continue_text(context)
            addition = self._strip_echoed_context(context, result)
            cursor.insertText(addition)

            self._set_status("✅ AI 续写完成", 3000)
        except Exception as e:
            logging.error(f"AI 续写失败: {e}")
            QMessageBox.warning(self, "AI 续写失败", str(e))

    # ==================================================================
    # AI 润色
    # ==================================================================
    def _ai_polish(self):
        """
        AI 润色：对当前选中的文字应用同义词替换、
        清理口语化词汇、统一标点。
        """
        from beeoffice.plugins.ai_assist import AIAssist

        try:
            if self._edit_mode == "rich_text":
                cursor = self.rich_editor.textCursor()
                if not cursor.hasSelection():
                    QMessageBox.information(
                        self, "提示", "请先选中要润色的文本"
                    )
                    return
                selected = cursor.selectedText()
                polished = AIAssist.polish_text(selected)
                cursor.insertText(polished)
            else:
                cursor = self.markdown_editor.textCursor()
                if not cursor.hasSelection():
                    QMessageBox.information(
                        self, "提示", "请先选中要润色的文本"
                    )
                    return
                selected = cursor.selectedText()
                polished = AIAssist.polish_text(selected)
                cursor.insertText(polished)

            self._set_status("✅ AI 润色完成", 3000)
        except Exception as e:
            logging.error(f"AI 润色失败: {e}")
            QMessageBox.warning(self, "AI 润色失败", str(e))

    # ==================================================================
    # AI 总结
    # ==================================================================
    def _ai_summarize(self):
        """
        AI 总结：提取式摘要（按句子长度排序取前 3 句），
        追加到文档末尾。
        """
        from beeoffice.plugins.ai_assist import AIAssist

        try:
            text = self.content()
            if len(text) < 100:
                QMessageBox.information(
                    self, "提示", "文本太短，无需总结"
                )
                return

            summary = AIAssist.summarize_text(text, max_sentences=3)
            if not summary:
                self._set_status("⚠️ 无法生成摘要", 3000)
                return

            summary_md = f"\n\n## AI 总结\n\n{summary}\n"
            if self._edit_mode == "rich_text":
                self.rich_editor.append(summary_md)
            else:
                self.markdown_editor.appendPlainText(summary_md)

            self._set_status("✅ AI 总结已插入文末", 3000)
        except Exception as e:
            logging.error(f"AI 总结失败: {e}")
            QMessageBox.warning(self, "AI 总结失败", str(e))

    # ==================================================================
    # AI 关键词提取
    # ==================================================================
    def _ai_keywords(self):
        """
        AI 关键词提取：按词频统计，过滤停用词，
        取前 5 个关键词追加到文档末尾。
        """
        from beeoffice.plugins.ai_assist import AIAssist

        try:
            text = self.content()
            if len(text) < 50:
                QMessageBox.information(
                    self, "提示", "文本太短，无法提取关键词"
                )
                return

            keywords = AIAssist.extract_keywords(text, top_n=5)
            if not keywords:
                self._set_status("⚠️ 未提取到关键词", 3000)
                return

            kw_md = "\n\n## 关键词\n\n" + "、".join(keywords) + "\n"
            if self._edit_mode == "rich_text":
                self.rich_editor.append(kw_md)
            else:
                self.markdown_editor.appendPlainText(kw_md)

            self._set_status(
                f"✅ 已提取 {len(keywords)} 个关键词", 3000
            )
        except Exception as e:
            logging.error(f"AI 关键词提取失败: {e}")
            QMessageBox.warning(self, "AI 关键词提取失败", str(e))