# beeoffice/plugins/beewrite_ai_mixin.py
"""
蜜写 AI 辅助 Mixin

职责：
  - _show_ai_menu      : 弹出 AI 菜单（续写 / 润色 / 总结 / 关键词）
  - _ai_continue       : 基于光标前文继续写作
  - _ai_polish         : 润色选中的文字
  - _ai_summarize      : 总结当前文档并插入到文末
  - _ai_keywords       : 提取关键词并插入到文末

## 2026-10-14 改造（重要）
改造前这三个功能**完全不联网**：`ai_assist.py` 只有 `re/random/logging/typing`，
「AI 续写」是 `random.choice(12 条硬编码句库)` —— **与上下文无关的模板句**，
而提示写的是"✅ AI 续写完成"。用户会把模板句当成 AI 生成的内容用。

现在：
  1. **优先走真 LLM**（`ai_client.AIClient`，配置来自「帮助 → 🤖 AI 设置」，
     即 `ai_api_key` / `ai_api_base` / `ai_model`）；
  2. 调用**走后台线程**（`AsyncTaskManager`）—— 生成要几秒，不能卡界面；
  3. **没有可用 AI 或调用失败时，绝不静默插模板**：
     先弹框说明原因并**征求同意**（默认「否」），同意后才用本地规则，
     且状态栏明确写"**已插入本地模板句（不是 AI 生成）**"；
  4. 成功时状态栏写明来源（`AI 生成（deepseek-chat）`）。

依赖：
  - PySide6（QMenu / QMessageBox）
  - beeoffice.plugins.ai_client（延迟 import）
  - beeoffice.plugins.ai_assist（本地规则兜底，延迟 import）
"""
import logging

from PySide6.QtWidgets import QMenu, QMessageBox

from beeoffice.async_task import AsyncTaskManager

#: 续写时取光标前多少字符当上下文（送模型）
CONTINUE_CONTEXT_CHARS = 1500
#: 总结/关键词时送模型的最大字符数（ai_client 内还会再截一次）
DOC_CHARS_FOR_AI = 4000


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
        menu.addAction("⚙️ AI 设置…").triggered.connect(self._open_ai_settings)
        menu.exec(self._ai_btn.mapToGlobal(
            self._ai_btn.rect().bottomLeft()
        ))

    def _open_ai_settings(self):
        """从写作场景直接跳去配置 AI（否则用户不知道去哪填 Key）。"""
        from beeoffice.ai_settings import show_ai_settings

        try:
            from beeoffice.settings import AppSettings

            saved = show_ai_settings(self, settings=AppSettings())
        except Exception as e:  # noqa: BLE001
            logging.error(f"打开 AI 设置失败: {e}")
            QMessageBox.warning(self, "打不开 AI 设置", str(e))
            return
        self._ai_client = None          # 配置可能变了，下次重新构造
        self._set_status(
            "✅ AI 配置已更新" if saved else "未修改 AI 配置", 3000
        )

    # ==================================================================
    # 取活动编辑器 / 插入工具
    # ==================================================================
    def _ai_editor(self):
        """当前可见的编辑器（富文本优先，与既有实现一致）。"""
        if getattr(self, "_edit_mode", "") == "rich_text":
            return self.rich_editor
        return getattr(self, "markdown_editor", None) or self.rich_editor

    def _ai_cursor_position(self):
        try:
            return self._ai_editor().textCursor().position()
        except Exception:  # noqa: BLE001
            return 0

    def _ai_insert_at(self, position, text):
        """把文本插入到**记录下来的位置**（异步回来后光标可能已变）。"""

        editor = self._ai_editor()
        cursor = editor.textCursor()
        cursor.setPosition(max(0, min(position, len(editor.toPlainText()))))
        cursor.insertText(text)

    def _ai_append(self, text):
        """追加到文末（总结/关键词用）。"""
        if getattr(self, "_edit_mode", "") == "rich_text":
            self.rich_editor.append(text)
        else:
            editor = getattr(self, "markdown_editor", None)
            if editor is not None:
                editor.appendPlainText(text)
            else:
                self.rich_editor.append(text)

    # ==================================================================
    # 统一的"AI 优先 + 本地规则兜底"流程
    # ==================================================================
    def _get_ai_client(self):
        """取（并缓存）AI 客户端；配置变更后由 `_open_ai_settings` 置空重取。"""
        client = getattr(self, "_ai_client", None)
        if client is None:
            from beeoffice.plugins.ai_client import AIClient

            try:
                from beeoffice.settings import AppSettings

                client = AIClient.from_settings(AppSettings())
            except Exception as e:  # noqa: BLE001 - 读不到设置就当未配置
                logging.debug(f"[AI] 构造客户端失败: {e}")
                client = AIClient({})
            self._ai_client = client
        return client

    def _ask_use_local(self, action: str, reason: str) -> bool:
        """
        没有可用 AI 时，问用户是否改用**本地规则**（默认「否」）。

        **这一步是本次改造的重点**：以前是静默插入模板句，用户以为那是 AI。
        """
        reply = QMessageBox.question(
            self,
            f"{action}：没有可用的 AI",
            f"{reason}\n\n"
            f"是否改用**本地规则**做{action}？\n"
            "· 本地规则不联网、数据不出本机\n"
            "· 但质量有限：续写会插入**模板句**（与你的上下文无关），"
            "总结是**提取式**（挑原句）\n\n"
            "想真正用 AI，请到「帮助 → 🤖 AI 设置」填写服务商与 API Key。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return reply == QMessageBox.Yes

    def _run_ai_action(self, action, prompt, insert_ai, build_local,
                       min_chars_hint=""):
        """
        统一流程：真 LLM 优先 → 失败/未配置则征得同意后用本地规则。

        :param action: 中文动作名（"续写"），用于提示与状态栏
        :param prompt: 送给模型的提示词
        :param insert_ai: 拿到 AI 文本后如何插入：callable(text)
        :param build_local: 本地规则兜底：callable() -> (文本, 说明)
        :param min_chars_hint: 文本太短时的提示（空串表示不校验）
        """
        client = self._get_ai_client()

        if not client.available:
            reason = client.unavailable_reason()
            self._fallback_or_prompt(action, reason, build_local)
            return

        self._set_status(f"⏳ AI {action}中…", 0)

        def on_result(result):
            ok, text = result
            if ok:
                try:
                    insert_ai(text)
                except Exception as e:  # noqa: BLE001
                    logging.error(f"AI {action}插入失败: {e}")
                    QMessageBox.warning(self, f"AI {action}失败", str(e))
                    return
                self._set_status(
                    f"✅ AI {action}完成（{client.describe_source()}）", 4000
                )
            else:
                logging.warning(f"[AI] {action}降级：{text}")
                self._fallback_or_prompt(action, text, build_local)

        def on_error(error):
            logging.error(f"AI {action}任务异常: {error}")
            self._fallback_or_prompt(action, f"调用出错：{error}", build_local)

        AsyncTaskManager.run(
            client.chat, prompt, on_result=on_result, on_error=on_error,
        )

    def _fallback_or_prompt(self, action, reason, build_local):
        """降级路径：先问用户，同意了才插本地内容，并**如实标注**。"""
        if build_local is None:
            self._set_status(f"⚠️ AI {action}不可用：{reason}", 6000)
            QMessageBox.information(self, f"{action}不可用", reason)
            return
        if not self._ask_use_local(action, reason):
            self._set_status(f"已取消（AI {action}不可用）", 4000)
            return
        try:
            text, note = build_local()
        except Exception as e:  # noqa: BLE001
            logging.error(f"本地{action}失败: {e}")
            QMessageBox.warning(self, f"本地{action}失败", str(e))
            return
        if not text:
            self._set_status(f"⚠️ 本地{action}没有产出内容", 4000)
            return
        # 注意：`build_local()` 内部**已经完成插入**（各功能插入位置不同），
        # 这里只负责提示，不能再插一次。
        self._set_status(note, 6000)

    # ==================================================================
    # AI 续写
    # ==================================================================
    def _ai_continue(self):
        """AI 续写：光标前文当上下文，优先真 LLM。"""
        from beeoffice.plugins.ai_client import build_continue_prompt

        try:
            editor = self._ai_editor()
            position = self._ai_cursor_position()
            context = editor.toPlainText()[:position][-CONTINUE_CONTEXT_CHARS:]
            if len(context.strip()) < 10:
                QMessageBox.information(
                    self, "提示", "光标前的文字太少，先写几句再续写。"
                )
                return

            self._run_ai_action(
                "续写",
                build_continue_prompt(context),
                insert_ai=lambda text: self._ai_insert_at(position, text),
                build_local=lambda: self._local_continue(context, position),
            )
        except Exception as e:  # noqa: BLE001
            logging.error(f"AI 续写失败: {e}")
            QMessageBox.warning(self, "AI 续写失败", str(e))

    def _local_continue(self, context, position):
        """本地规则续写（**模板句**）——仅在用户同意后使用。"""
        from beeoffice.plugins.ai_assist import AIAssist

        result = AIAssist.continue_text(context)
        addition = (
            result[len(context):] if result.startswith(context) else result
        )
        self._ai_insert_at(position, addition)
        return addition, "✅ 已插入**本地模板句**（不是 AI 生成，内容与你的上下文无关）"

    # ==================================================================
    # AI 润色
    # ==================================================================
    def _ai_polish(self):
        """AI 润色：优先真 LLM；本地兜底是同义词替换。"""
        from beeoffice.plugins.ai_client import build_polish_prompt

        try:
            editor = self._ai_editor()
            cursor = editor.textCursor()
            if not cursor.hasSelection():
                QMessageBox.information(self, "提示", "请先选中要润色的文本")
                return
            selected = cursor.selectedText()
            if not selected.strip():
                QMessageBox.information(self, "提示", "选中的是空白内容")
                return

            start, end = cursor.selectionStart(), cursor.selectionEnd()

            def insert_ai(text):
                self._replace_range(start, end, text)

            def build_local():
                from beeoffice.plugins.ai_assist import AIAssist

                polished = AIAssist.polish_text(selected)
                self._replace_range(start, end, polished)
                return polished, "✅ 已用**本地同义词替换**润色（不是 AI 生成）"

            self._run_ai_action(
                "润色", build_polish_prompt(selected),
                insert_ai=insert_ai, build_local=build_local,
            )
        except Exception as e:  # noqa: BLE001
            logging.error(f"AI 润色失败: {e}")
            QMessageBox.warning(self, "AI 润色失败", str(e))

    def _replace_range(self, start, end, text):
        """替换文档中 [start, end) 的内容（异步回来后可安全调用）。"""
        editor = self._ai_editor()
        from PySide6.QtGui import QTextCursor

        cursor = editor.textCursor()
        cursor.setPosition(max(0, start))
        cursor.setPosition(max(0, end), QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(text)

    # ==================================================================
    # AI 总结
    # ==================================================================
    def _ai_summarize(self):
        """AI 总结：优先真 LLM（要点式、必须压缩）；本地兜底是提取式摘要。"""
        from beeoffice.plugins.ai_client import build_summarize_prompt

        try:
            text = self.content()
            if len(text) < 100:
                QMessageBox.information(self, "提示", "文本太短，无需总结")
                return

            def insert_ai(result):
                self._ai_append(f"\n\n## AI 总结\n\n{result}\n")

            def build_local():
                from beeoffice.plugins.ai_assist import AIAssist

                summary = AIAssist.summarize_text(text, max_sentences=3)
                if summary:
                    self._ai_append(f"\n\n## 摘要（本地提取）\n\n{summary}\n")
                return summary, "✅ 已插入**本地提取式摘要**（挑原句，不是 AI 生成）"

            self._run_ai_action(
                "总结", build_summarize_prompt(text[:DOC_CHARS_FOR_AI]),
                insert_ai=insert_ai, build_local=build_local,
            )
        except Exception as e:  # noqa: BLE001
            logging.error(f"AI 总结失败: {e}")
            QMessageBox.warning(self, "AI 总结失败", str(e))

    # ==================================================================
    # AI 关键词提取
    # ==================================================================
    def _ai_keywords(self):
        """AI 关键词：优先真 LLM；本地兜底是词频统计。"""
        from beeoffice.plugins.ai_client import build_keywords_prompt

        try:
            text = self.content()
            if len(text) < 50:
                QMessageBox.information(
                    self, "提示", "文本太短，无法提取关键词"
                )
                return

            def insert_ai(result):
                self._ai_append(f"\n\n## 关键词\n\n{result}\n")

            def build_local():
                from beeoffice.plugins.ai_assist import AIAssist

                keywords = AIAssist.extract_keywords(text, top_n=5)
                if keywords:
                    self._ai_append(
                        "\n\n## 关键词（本地词频）\n\n"
                        + "、".join(keywords) + "\n"
                    )
                return keywords, (
                    f"✅ 已插入 **本地词频统计**的 {len(keywords)} 个关键词"
                    "（不是 AI 生成）"
                )

            self._run_ai_action(
                "关键词提取", build_keywords_prompt(text[:DOC_CHARS_FOR_AI]),
                insert_ai=insert_ai, build_local=build_local,
            )
        except Exception as e:  # noqa: BLE001
            logging.error(f"AI 关键词提取失败: {e}")
            QMessageBox.warning(self, "AI 关键词提取失败", str(e))
