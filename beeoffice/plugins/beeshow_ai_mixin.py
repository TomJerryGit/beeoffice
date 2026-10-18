# beeoffice/plugins/beeshow_ai_mixin.py
"""
蜜演辅助功能 Mixin（图标 / 模板 / AI 大纲 / AI 配图 / 导入 / 二维码）

职责：
  - _show_icon_picker       : 图标库对话框，点击插入到编辑器
  - _show_template_menu     : 模板菜单（工作汇报 / 项目路演 / 学术答辩）
  - _apply_template_content : 应用模板内容（同步解析，避免 150ms 空白）
  - _ai_generate_outline    : 调用 LLM 生成演示大纲（任务 1.1）
  - _show_image_suggester   : 根据当前页内容推荐配图（任务 1.3）
  - _show_image_picker_dialog : 展示配图候选，用户选择后插入（任务 1.3）
  - _insert_image_url       : 把图片 URL 插入到当前页（任务 1.3）
  - _import_markdown        : 导入 .md 文件
  - _generate_qrcode        : 二维码分享（占位）

v5.1 增量汇总：
  - 任务 1.1：_ai_generate_outline 从硬编码模板升级为真实 LLM 调用
  - 任务 1.3：新增 _show_image_suggester / _show_image_picker_dialog /
             _insert_image_url

v5.2.1 修复：
  - _show_icon_picker 里 `btn.clicked.connect(lambda checked, ...)`
    的 checked 没默认值 → PySide6 点击时抛 TypeError。
    修复：改为 `lambda checked=False, ...`。
  - _show_template_menu 里 `action.triggered.connect(lambda checked, ...)`
    同样问题，同样修复。
  - _show_template_menu 改为通过 _apply_template_content 应用模板，
    加 blockSignals + 主动 _update_preview，避免 150ms 空白。

依赖：
  - re / logging / datetime
  - PySide6（QDialog / QVBoxLayout / QHBoxLayout / QLabel / QPushButton /
             QMenu / QInputDialog / QMessageBox / QFileDialog）
  - beeshow_constants（ICON_LIBRARY / TEMPLATE_LIBRARY）
  - beeshow_ai_service（延迟 import，任务 1.1）
  - beeshow_image_suggest（延迟 import，任务 1.3）
  - beeshow_image_suggester_dialog（延迟 import，任务 1.3）

修复记录：
  - _show_template_menu：`self.sender()` 可能为 None
    （从命令面板 / 快捷键调用时没有发送者），
    增加 sender 判空：None 时在窗口中心弹出菜单。

注意：
  - 不导入其他 beeshow_* Mixin，避免循环依赖
  - 图标 / 模板 / AI 大纲 / AI 配图都是"纯本地 + 可选 LLM"
"""

import re
import logging
from datetime import datetime

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMenu, QInputDialog, QMessageBox, QFileDialog,
)

from beeoffice.plugins.beeshow_constants import (
    ICON_LIBRARY, TEMPLATE_LIBRARY,
)
from beeoffice.i18n import tr


class AIMixin:
    """蜜演辅助功能 Mixin"""

    # ==================== 图标库 ====================
    def _show_icon_picker(self):
        """
        弹出图标库对话框。

        按分类（常用 / 箭头 / 商务 / 表情）分组显示按钮，
        点击任意图标：插入到编辑器光标处，并关闭对话框。

        v5.2.1 修复：
          lambda 的 checked 参数加默认值 False，
          否则 PySide6 点击时抛 TypeError。
        """
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("auto.beeshow_ai_mixin.04e71a43", "🎭 图标库"))
        layout = QVBoxLayout(dlg)

        for cat, icons in ICON_LIBRARY.items():
            layout.addWidget(QLabel(f"<b>{cat}</b>"))
            row = QHBoxLayout()
            for icon in icons:
                btn = QPushButton(icon)
                btn.setStyleSheet("font-size:24px;padding:4px;")
                # v5.2.1：checked 必须有默认值
                btn.clicked.connect(
                    lambda checked=False, i=icon: [
                        self._editor.insertPlainText(i),
                        dlg.accept(),
                    ]
                )
                row.addWidget(btn)
            layout.addLayout(row)

        dlg.exec()

    # ==================== 模板 ====================
    def _show_template_menu(self):
        """
        弹出模板菜单。

        每个模板把 {date} 替换为当天日期后写入编辑器。

        v5.2.1 修复：
          - lambda 的 checked 参数加默认值 False
          - 改用 _apply_template_content 应用模板，
            加 blockSignals + 主动 _update_preview，避免 150ms 空白

        修复：sender() 可能为 None（命令面板 / 快捷键调用时），
              此时在窗口中心弹出菜单。
        """
        menu = QMenu(self)

        for name, content in TEMPLATE_LIBRARY.items():
            action = menu.addAction(name)
            # v5.2.1：checked 必须有默认值
            action.triggered.connect(
                lambda checked=False, c=content:
                    self._apply_template_content(c)
            )

        # 修复：sender() 可能为 None
        sender = self.sender()
        if sender is not None:
            menu.exec(sender.mapToGlobal(sender.rect().bottomLeft()))
        else:
            menu.exec(self.mapToGlobal(self.rect().center()))

    def _apply_template_content(self, content: str):
        """
        应用模板内容到编辑器（v5.2.1 新增）。

        处理流程：
          1. 替换 {date} 占位符
          2. blockSignals 避免触发 150ms 防抖
          3. 立即调 _update_preview 同步解析

        :param content: 模板原文（含 {date} 占位符）
        """
        try:
            text = content.replace(
                "{date}",
                datetime.now().strftime("%Y年%m月%d日")
            )
            self._editor.blockSignals(True)
            self._editor.setPlainText(text)
            self._editor.blockSignals(False)

            # 立即同步解析（不依赖 150ms 防抖）
            self._current_slide = 0
            self._update_preview()
            self._set_status(tr("auto.beeshow_ai_mixin.f2ecb669", "✅ 模板已应用"), 2000)
        except Exception as e:
            logging.error(f"应用模板失败：{e}")
            QMessageBox.warning(self, tr("auto.beeshow_ai_mixin.1797e8c2", "应用失败"), str(e))

    # ==================== AI 大纲（任务 1.1） ====================
    def _ai_generate_outline(self):
        """
        调用 LLM 生成演示大纲（任务 1.1）。

        流程：
          1. 询问用户主题、受众、时长、页数
          2. 调用 BeeshowAIService.generate_outline
          3. 把 SlideOutline 列表转为 Markdown 幻灯片
          4. 写入编辑器并刷新预览

        降级：
          - 无 API Key 时自动使用本地模板
          - LLM 调用失败时降级
        """
        from beeoffice.plugins.beeshow_ai_service import (
            create_service_from_settings,
        )

        # 1. 询问主题
        topic, ok = QInputDialog.getText(
            self, tr("auto.beeshow_ai_mixin.a0567b07", "🤖 AI 生成大纲"), tr("auto.beeshow_ai_mixin.139a0d9c", "请输入演示主题:")
        )
        if not ok or not topic.strip():
            return

        # 2. 询问受众
        audience, ok = QInputDialog.getItem(
            self, tr("auto.beeshow_ai_mixin.a0567b07", "🤖 AI 生成大纲"), tr("auto.beeshow_ai_mixin.9e2e234d", "目标受众:"),
            ["普通听众", "技术团队", "管理层", "客户", "学生"],
            0, False,
        )
        if not ok:
            return

        # 3. 询问时长
        duration, ok = QInputDialog.getInt(
            self, "🤖 AI 生成大纲", "演示时长（分钟）:",
            10, 3, 120, 1,
        )
        if not ok:
            return

        # 4. 询问页数
        page_count, ok = QInputDialog.getInt(
            self, "🤖 AI 生成大纲", "期望页数:",
            8, 3, 30, 1,
        )
        if not ok:
            return

        # 5. 调用 AI 服务
        self._set_status(tr("auto.beeshow_ai_mixin.bf1f3cef", "🤖 正在生成大纲..."), 0)
        try:
            service = create_service_from_settings()
            outlines = service.generate_outline(
                topic=topic.strip(),
                audience=audience,
                duration=duration,
                page_count=page_count,
            )
        except Exception as e:
            logging.error(f"AI 生成大纲失败：{e}")
            QMessageBox.warning(self, tr("auto.beeshow_ai_mixin.64ba75d9", "生成失败"), str(e))
            self._set_status(tr("auto.beeshow_ai_mixin.b017c717", "❌ 生成失败"), 3000)
            return

        if not outlines:
            QMessageBox.warning(self, tr("auto.beeshow_ai_mixin.64ba75d9", "生成失败"), tr("auto.beeshow_ai_mixin.eeeb70c1", "AI 未返回有效大纲"))
            self._set_status(tr("auto.beeshow_ai_mixin.b017c717", "❌ 生成失败"), 3000)
            return

        # 6. 渲染为 Markdown 幻灯片
        md_parts = []
        for outline in outlines:
            md_parts.append(outline.to_markdown())
        full_md = "\n---\n".join(md_parts)

        self._editor.blockSignals(True)
        self._editor.setPlainText(full_md)
        self._editor.blockSignals(False)

        self._current_slide = 0
        self._update_preview()
        self._set_status(
            tr("auto.beeshow_ai_mixin.f640eb0a", "✅ 已生成 {0} 页大纲").format(len(outlines)), 3000
        )

    # ==================== AI 配图建议（任务 1.3） ====================
    def _show_image_suggester(self):
        """
        为当前页推荐配图。

        流程：
          1. 取当前页 Markdown 文本
          2. 调 ImageSuggester.suggest
          3. 弹窗展示 3-5 张候选图
          4. 用户点击某张 → 插入到编辑器
        """
        from beeoffice.plugins.beeshow_image_suggest import (
            create_suggester_from_settings,
        )

        if not self._slides_md:
            QMessageBox.information(
                self, tr("auto.beeshow_ai_mixin.ab3656a9", "提示"), tr("auto.beeshow_ai_mixin.63565334", "请先编写幻灯片内容")
            )
            return

        if not (0 <= self._current_slide < len(self._slides_md)):
            return

        text = self._slides_md[self._current_slide]
        if not text.strip():
            QMessageBox.information(self, tr("auto.beeshow_ai_mixin.ab3656a9", "提示"), tr("auto.beeshow_ai_mixin.5874e0a0", "当前页内容为空"))
            return

        self._set_status(tr("auto.beeshow_ai_mixin.c426fe77", "🖼️ 正在搜索配图..."), 0)

        try:
            suggester = create_suggester_from_settings()
            results = suggester.suggest(text, count=6)
        except Exception as e:
            logging.error(f"搜索配图失败：{e}")
            QMessageBox.warning(self, tr("auto.beeshow_ai_mixin.b9786d51", "搜索失败"), str(e))
            self._set_status(tr("auto.beeshow_ai_mixin.0cb80b7f", "❌ 搜索失败"), 3000)
            return

        if not results:
            QMessageBox.information(
                self, tr("auto.beeshow_ai_mixin.ab3656a9", "提示"),
                "未找到合适的配图。\n\n"
                "可在设置中配置 Unsplash / Pexels API Key 以获取更好的结果。"
            )
            self._set_status(tr("auto.beeshow_ai_mixin.bc9ce8ad", "⚠️ 未找到配图"), 3000)
            return

        # 弹窗展示候选图
        self._show_image_picker_dialog(results)
        self._set_status(
            tr("auto.beeshow_ai_mixin.200963ea", "✅ 已找到 {0} 张候选图").format(len(results)), 2000
        )

    def _show_image_picker_dialog(self, results: list):
        """
        展示配图选择对话框。

        :param results: 图片列表
        """
        from beeoffice.plugins.beeshow_image_suggester_dialog import (
            ImageSuggesterDialog,
        )
        dlg = ImageSuggesterDialog(results, self)
        if dlg.exec() == QDialog.Accepted:
            selected = dlg.get_selected()
            if selected:
                self._insert_image_url(selected["url"])

    def _insert_image_url(self, url: str):
        """
        把图片 URL 插入到当前页。

        :param url: 图片 URL
        """
        try:
            text = self._editor.toPlainText()
            parts = re.split(r'\n---', text)
            if not (0 <= self._current_slide < len(parts)):
                return

            # 在页末尾插入 ![](url)
            parts[self._current_slide] = (
                parts[self._current_slide].rstrip()
                + f"\n\n![]({url})\n"
            )

            self._editor.blockSignals(True)
            self._editor.setPlainText('\n---\n'.join(parts))
            self._editor.blockSignals(False)
            self._update_preview()
            self._set_status(tr("auto.beeshow_ai_mixin.741b114e", "✅ 图片已插入"), 2000)
        except Exception as e:
            logging.error(f"插入图片失败：{e}")
            QMessageBox.warning(self, tr("auto.beeshow_ai_mixin.4620fab0", "插入失败"), str(e))

    # ==================== 导入 ====================
    def _import_markdown(self):
        """
        导入 .md 文件到编辑器。

        读取成功后写入 _editor 并触发 _update_preview。
        读取失败（编码 / 权限）弹 QMessageBox 提示。
        """
        path, _ = QFileDialog.getOpenFileName(
            self, tr("auto.beeshow_ai_mixin.75c25bbc", "导入 Markdown"), "", "Markdown (*.md)"
        )
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    self._editor.setPlainText(f.read())
                self._update_preview()
            except Exception as e:
                QMessageBox.warning(self, tr("auto.beeshow_ai_mixin.a01a8d53", "导入失败"), str(e))

    # ==================== 二维码（占位） ====================
    def _generate_qrcode(self):
        """
        二维码分享（占位）。

        真正实现需要：
          - 联网生成二维码（如调用 qrcode 库 + 短链接服务）
          - 或本地生成二维码后让用户扫码访问导出 HTML
        当前先以提示代替。
        """
        QMessageBox.information(
            self,
            tr("auto.beeshow_ai_mixin.2b65c7a1", "二维码分享"),
            "此功能需要联网生成。\n"
            "可以将导出HTML上传到服务器后生成二维码。"
        )