# beeoffice/plugins/beeshow_notes_mixin.py
"""
蜜演演讲备注 Mixin

职责：
  - edit_current_notes    : 弹出对话框编辑当前页备注
  - add_speaker_notes     : 写入备注并同步到编辑器
  - _sync_notes_to_editor : 把 _speaker_notes 写回 _editor 的 <!-- --> 注释
  - _set_status           : 状态栏消息（向上查找主窗口）
  - _ai_generate_notes    : AI 为当前页生成演讲稿（任务 1.2）
  - _ai_generate_all_notes: AI 为所有页批量生成演讲稿（任务 1.2）

v5.1 增量汇总：
  - 任务 1.2：新增 _ai_generate_notes / _ai_generate_all_notes

依赖：
  - re / logging
  - PySide6（QInputDialog / QMessageBox）

说明：
  - _set_status 被 PlayMixin / NotesMixin / ExportMixin / HistoryMixin
    等多处调用
  - 备注存储在 _speaker_notes 平行列表中，与 _slides_md 一一对应
  - 备注在编辑器里以 `<!-- 备注内容 -->` HTML 注释形式保存，
    这样切换幻灯片 / 重新解析时不会丢失
  - 不导入其他 beeshow_* Mixin，避免循环依赖

注意：
  - 与 CommentMixin 的 comments 注释区分：
      <!-- 备注 -->                ← 本模块（演讲备注）
      <!-- comments: [...] -->     ← CommentMixin（页评论）
      <!-- beeoffice-style: ... --> ← ElementEditorMixin（样式覆盖）
      <!-- beeoffice-image: ... --> ← ImageEditorMixin（图片位置）
      <!-- morph-id: xxx -->        ← MorphMixin（平滑动画标记）
"""

import re
import logging

from PySide6.QtWidgets import QInputDialog, QMessageBox
from beeoffice.i18n import tr


class NotesMixin:
    """蜜演演讲备注 Mixin"""

    # ==================== 编辑备注 ====================
    def edit_current_notes(self):
        """
        编辑当前幻灯片的演讲备注。

        流程：
          1. 无幻灯片时提示
          2. 读取当前页已有备注作为对话框默认值
          3. 弹出多行文本输入框
          4. 用户确认后调 add_speaker_notes 写入
        """
        if not self._slides_html:
            QMessageBox.information(self, tr("auto.beeshow_notes_mixin.ab3656a9", "提示"), tr("auto.beeshow_notes_mixin.63565334", "请先编写幻灯片内容"))
            return

        current_notes = ""
        if 0 <= self._current_slide < len(self._speaker_notes):
            current_notes = self._speaker_notes[self._current_slide]

        text, ok = QInputDialog.getMultiLineText(
            self, "📝 演讲备注",
            f"第 {self._current_slide + 1} 页备注：",
            current_notes
        )
        if ok:
            self.add_speaker_notes(text)

    def add_speaker_notes(self, text):
        """
        为当前幻灯片添加 / 更新备注。

        写入策略：
          - 当前页在 _speaker_notes 范围内 → 覆盖
          - 当前页正好是末尾 + 1 → append
          - 其他情况 → 忽略（越界保护）

        副作用：
          - 同步更新 _notes_editor（blockSignals 防止反向写回）
          - 调 _sync_notes_to_editor 写回 _editor
        """
        if 0 <= self._current_slide < len(self._speaker_notes):
            # 覆盖已有备注
            self._speaker_notes[self._current_slide] = text
        elif self._current_slide == len(self._speaker_notes):
            # 追加到末尾
            self._speaker_notes.append(text)
        else:
            # 越界（一般不会发生），忽略
            return

        # 同步备注编辑器（blockSignals 避免触发 _on_notes_changed 反向覆盖）
        self._notes_editor.blockSignals(True)
        self._notes_editor.setPlainText(text)
        self._notes_editor.blockSignals(False)

        # 写回 _editor
        self._sync_notes_to_editor()
        self._set_status(tr("auto.beeshow_notes_mixin.c51339a2", "📝 备注已更新"), 2000)

    def _sync_notes_to_editor(self):
        """
        将 _speaker_notes 同步回 _editor 的 HTML 注释格式。

        每一页格式：
          {Markdown 内容}
          <!-- 备注内容 -->

        无备注时只保留 Markdown 内容，不加注释。
        """
        text = self._editor.toPlainText()
        parts = re.split(r'\n---', text)
        new_parts = []

        for i, part in enumerate(parts):
            # 先移除旧备注注释
            # 注意：只移除不带前缀的 <!-- ... -->（演讲备注）
            # 不影响 <!-- comments: --> / <!-- beeoffice-style: --> /
            # <!-- beeoffice-image: --> / <!-- morph-id: -->
            part = self._remove_plain_comment(part).strip()

            # 追加新备注注释（若有）
            note = (
                self._speaker_notes[i]
                if i < len(self._speaker_notes)
                else ""
            )
            if note:
                part = part + f"\n<!-- {note} -->"

            new_parts.append(part)

        # blockSignals 避免 setPlainText 触发 textChanged → 递归 _update_preview
        self._editor.blockSignals(True)
        self._editor.setPlainText('\n---\n'.join(new_parts))
        self._editor.blockSignals(False)

    @staticmethod
    def _remove_plain_comment(part: str) -> str:
        """
        仅移除「普通 HTML 注释」（演讲备注），保留带前缀的特殊注释。

        区分：
          <!-- 备注内容 -->               ← 移除（本模块）
          <!-- comments: [...] -->        ← 保留
          <!-- beeoffice-style: ... -->   ← 保留
          <!-- beeoffice-image: ... -->   ← 保留
          <!-- morph-id: xxx -->          ← 保留

        :param part: Markdown 片段
        :return: 移除普通注释后的片段
        """
        # 匹配 <!-- ... --> 但排除带前缀的
        # 简化策略：先移除带前缀的（占位），处理后再还原
        placeholders = {}
        counter = [0]

        def save_special(m):
            key = f"__BEEOFFICE_PLACEHOLDER_{counter[0]}__"
            counter[0] += 1
            placeholders[key] = m.group(0)
            return key

        # 保存特殊注释
        special_pattern = re.compile(
            r'<!--\s*(comments:|beeoffice-style:|beeoffice-image:|'
            r'morph-id:).*?-->',
            re.DOTALL,
        )
        temp = special_pattern.sub(save_special, part)

        # 移除普通注释
        temp = re.sub(r'<!--.*?-->', '', temp, flags=re.DOTALL)

        # 还原特殊注释
        for key, value in placeholders.items():
            temp = temp.replace(key, value)

        return temp

    # ==================== AI 演讲稿（任务 1.2） ====================
    def _ai_generate_notes(self):
        """
        调用 LLM 为当前页生成演讲稿（任务 1.2）。

        流程：
          1. 检查当前页是否有内容
          2. 从 _slides_md 取当前页 Markdown 源
          3. 调用 BeeshowAIService.generate_notes
          4. 写入 _speaker_notes 并同步到编辑器

        降级：
          - 无 API Key 时提示用户先配置
          - LLM 调用失败时保留原备注不变
        """
        from beeoffice.plugins.beeshow_ai_service import (
            create_service_from_settings,
        )

        if not self._slides_md:
            QMessageBox.information(self, tr("auto.beeshow_notes_mixin.ab3656a9", "提示"), tr("auto.beeshow_notes_mixin.63565334", "请先编写幻灯片内容"))
            return

        if not (0 <= self._current_slide < len(self._slides_md)):
            QMessageBox.information(self, tr("auto.beeshow_notes_mixin.ab3656a9", "提示"), tr("auto.beeshow_notes_mixin.6f02da31", "当前页索引无效"))
            return

        # 取当前页标题与内容
        slide_title = (
            self._slide_titles[self._current_slide]
            if self._current_slide < len(self._slide_titles)
            else f"第 {self._current_slide + 1} 页"
        )
        slide_content = self._slides_md[self._current_slide]

        # 询问期望演讲时长
        duration_sec, ok = QInputDialog.getInt(
            self, "🤖 AI 讲稿",
            f"为「{slide_title}」生成演讲稿\n期望时长（秒）:",
            30, 10, 300, 5,
        )
        if not ok:
            return

        self._set_status(tr("auto.beeshow_notes_mixin.836b176d", "🤖 正在生成演讲稿..."), 0)
        try:
            service = create_service_from_settings()
            notes = service.generate_notes(
                slide_title=slide_title,
                slide_content=slide_content,
                duration_sec=duration_sec,
            )
        except Exception as e:
            logging.error(f"AI 生成演讲稿失败：{e}")
            QMessageBox.warning(self, tr("auto.beeshow_notes_mixin.64ba75d9", "生成失败"), str(e))
            self._set_status(tr("auto.beeshow_notes_mixin.b017c717", "❌ 生成失败"), 3000)
            return

        if not notes:
            QMessageBox.information(
                self, tr("auto.beeshow_notes_mixin.ab3656a9", "提示"),
                "AI 未返回演讲稿。\n\n"
                "可能原因：\n"
                "• 未配置 AI API Key（设置 → AI 服务）\n"
                "• API 调用失败\n\n"
                "可在 ~/.beeoffice_settings.json 中配置 "
                "ai_api_key 后重试。"
            )
            self._set_status(tr("auto.beeshow_notes_mixin.fe019d54", "⚠️ 未生成演讲稿"), 3000)
            return

        # 写入备注
        self.add_speaker_notes(notes)
        self._set_status(
            tr("auto.beeshow_notes_mixin.fada6e21", "✅ 已生成演讲稿（{0} 字）").format(len(notes)), 3000
        )

    def _ai_generate_all_notes(self):
        """
        为所有幻灯片批量生成演讲稿（任务 1.2 扩展）。

        流程：
          1. 遍历所有页面
          2. 逐页调用 generate_notes
          3. 汇总结果写入 _speaker_notes
        """
        from beeoffice.plugins.beeshow_ai_service import (
            create_service_from_settings,
        )

        if not self._slides_md:
            QMessageBox.information(self, tr("auto.beeshow_notes_mixin.ab3656a9", "提示"), tr("auto.beeshow_notes_mixin.63565334", "请先编写幻灯片内容"))
            return

        total = len(self._slides_md)
        reply = QMessageBox.question(
            self, tr("auto.beeshow_notes_mixin.a140f197", "🤖 批量生成演讲稿"),
            f"将为 {total} 页生成演讲稿，"
            f"预计耗时 {total * 3}~{total * 5} 秒。\n\n"
            f"是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return

        service = create_service_from_settings()
        if not service.api_key:
            QMessageBox.information(
                self, tr("auto.beeshow_notes_mixin.ab3656a9", "提示"),
                "未配置 AI API Key。\n\n"
                "请在 ~/.beeoffice_settings.json 中配置 "
                "ai_api_key 后重试。"
            )
            return

        success = 0
        fail = 0
        for i in range(total):
            slide_title = (
                self._slide_titles[i]
                if i < len(self._slide_titles)
                else f"第 {i + 1} 页"
            )
            self._set_status(
                tr("auto.beeshow_notes_mixin.63e0d4dc", "🤖 正在生成第 {0}/{1} 页...").format(i + 1, total), 0
            )
            try:
                notes = service.generate_notes(
                    slide_title=slide_title,
                    slide_content=self._slides_md[i],
                    duration_sec=30,
                )
                if notes:
                    # 直接写入 _speaker_notes（不调 add_speaker_notes，
                    # 避免每页都触发 _sync_notes_to_editor）
                    while len(self._speaker_notes) <= i:
                        self._speaker_notes.append("")
                    self._speaker_notes[i] = notes
                    success += 1
                else:
                    fail += 1
            except Exception as e:
                logging.error(f"第 {i + 1} 页生成失败：{e}")
                fail += 1

        # 统一同步回编辑器
        self._sync_notes_to_editor()
        self._set_status(
            tr("auto.beeshow_notes_mixin.4718777f", "✅ 批量完成：成功 {success} 页，失败 {fail} 页").format(success=success, fail=fail), 5000
        )

    # ==================== 状态栏 ====================
    def _set_status(self, msg, timeout=0):
        """
        显示状态消息。

        向上查找主窗口（带 set_global_status 的对象），
        找到则调用之；找不到则静默忽略。

        参数：
          msg     : 消息文本
          timeout : 超时清空毫秒数（0 表示不自动清空）
        """
        p = self
        while p:
            if hasattr(p, 'set_global_status'):
                p.set_global_status(msg, timeout)
                return
            p = p.parent()