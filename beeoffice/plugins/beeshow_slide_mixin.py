# beeoffice/plugins/beeshow_slide_mixin.py
"""
蜜演幻灯片解析与渲染 Mixin

职责：
  - _on_editor_changed        : 编辑器内容变化（防抖 150ms）
  - _update_preview           : 重新解析 _editor 为幻灯片结构
  - _md_to_html               : Markdown → HTML（含所有 v5.1 扩展）
  - _update_thumbnails        : 刷新右侧缩略图列表
  - _on_thumb_clicked         : 缩略图单击切换
  - _on_thumb_double_clicked  : 缩略图双击重命名
  - _on_slides_reordered      : 拖拽排序（P1-13：保留 Markdown 源）
  - _add_slide / _delete_slide
  - add_slide / delete_slide（插件别名）
  - _show_slide               : 渲染指定页到预览（注入所有 JS）
  - _on_theme_changed         : 主题切换（任务 4.3：广播）
  - _on_notes_changed         : 备注编辑器内容变化同步
  - _customize_background     : 自定义背景色
  - _on_element_edit_applied  : 元素编辑回调（任务 2.2）
  - _on_image_edit_applied    : 图片编辑回调（任务 2.3）

v5.1 增量汇总：
  - 任务 2.1：_md_to_html 支持 md_in_html；_show_slide 拼入版式 CSS
  - 任务 4.1：_update_preview 末尾自动保存快照
  - 任务 2.2：_md_to_html 应用样式覆盖；_show_slide 注入编辑器 JS；
              _on_element_edit_applied 回调
  - 任务 2.3：_md_to_html 应用图片信息；_show_slide 注入图片编辑 JS；
              _on_image_edit_applied 回调
  - 任务 5.1：_md_to_html 处理动态数字；_show_slide 注入动态数字 JS
  - 任务 5.3：_md_to_html 处理视频嵌入
  - 任务 5.2：_md_to_html 处理 morph id；_show_slide 通过 PlayMixin 注入
  - 任务 4.2：_update_preview 加载评论；剥离 comments 注释
  - 任务 4.3：_show_slide / _on_theme_changed 广播

v5.1.1 修复：
  - QTimer 从 PySide6.QtWidgets 改为 PySide6.QtCore
    （QTimer 属于 QtCore，不在 QtWidgets；原 import 会抛 ImportError）

依赖：
  - re / markdown（延迟 import）
  - PySide6.QtWidgets（QListWidgetItem / QInputDialog / QColorDialog /
                      QMessageBox）
  - PySide6.QtCore（QTimer）
  - beeshow_constants.SLIDE_THEMES

说明：
  - _slides_md 是 P1-13 引入的额外状态：保留每页 Markdown 源
  - 拖拽排序调整 4 个平行列表：
      _slides_html / _slides_md / _speaker_notes / _slide_titles
  - 不导入其他 beeshow_* Mixin，避免循环依赖
"""

import re
import logging

from PySide6.QtWidgets import (
    QListWidgetItem, QInputDialog, QColorDialog, QMessageBox,
)
from PySide6.QtCore import QTimer

from beeoffice.plugins.beeshow_constants import SLIDE_THEMES
from beeoffice.i18n import tr


class SlideMixin:
    """蜜演幻灯片解析与渲染 Mixin"""

    # ==================== 编辑器变化 ====================
    def _on_editor_changed(self):
        """
        编辑器内容变化：防抖 150ms 后触发 _update_preview。

        频繁敲键时避免每字符都重新解析（markdown 渲染 + 缩略图刷新）。
        """
        QTimer.singleShot(150, self._update_preview)

    # ==================== 核心解析 ====================
    def _update_preview(self):
        """
        重新解析 _editor 内容为幻灯片结构。

        处理流程：
          1. 按 `\\n---` 切分为多张幻灯片
          2. 每张里提取 <!-- 备注 -->（若有）
          3. 剥离 comments / beeoffice-style / beeoffice-image 注释
          4. Markdown → HTML（含动态数字 / 视频 / morph id）
          5. 记录标题（从 <h1~h3> 中提取）
          6. 刷新缩略图列表
          7. 显示当前页
          8. 保存版本快照（任务 4.1）

        v5.1 增量：
          - 任务 4.2：先加载评论，再解析内容
          - 任务 4.1：末尾保存快照
        """
        text = self._editor.toPlainText()

        # 任务 4.2：从编辑器解析评论（在解析幻灯片之前）
        try:
            self._load_comments_from_editor(text)
            self._refresh_comment_panel()
        except AttributeError:
            pass

        raw_parts = re.split(r'\n---', text)

        # 只丢弃文件末尾的空段（结尾的 "---"），**保留中间空段**。
        # 若把所有空段都丢掉，_slides_html 的下标就与 Markdown 的分页号对不上，
        # 备注/评论写入时会整体错位。
        while len(raw_parts) > 1 and not raw_parts[-1].strip():
            raw_parts.pop()

        self._slides_html = []
        self._slides_md = []           # P1-13：同步清空
        self._speaker_notes = []
        self._slide_titles = []

        for part in raw_parts:
            part = part.strip()
            note = ""

            # 提取 <!-- 备注 -->
            nm = re.search(r'<!--\s*(.*?)\s*-->', part, re.DOTALL)
            if nm:
                note = nm.group(1).strip()
                part = part.replace(nm.group(0), '').strip()

            # 任务 4.2：剥离 comments 注释
            part = re.sub(
                r'<!--\s*comments:.*?-->',
                '',
                part,
                flags=re.DOTALL,
            ).strip()

            # 任务 2.2 / 2.3：剥离 beeoffice-style / beeoffice-image 注释
            part = re.sub(
                r'<!--\s*beeoffice-(style|image):.*?-->',
                '',
                part,
                flags=re.DOTALL,
            ).strip()

            # 关键：备注与幻灯片必须**一一对应**。
            # 原实现先 append 备注、再判断 part 是否为空，
            # 一个"只有注释"的分页会让两者错位，备注从此写到别的页上。
            self._speaker_notes.append(note)

            html = self._md_to_html(part) if part else ""
            self._slides_html.append(html)
            self._slides_md.append(part)      # P1-13：保留源文本

            title_match = re.search(
                r'<h[1-3][^>]*>(.*?)</h[1-3]>', html
            )
            self._slide_titles.append(
                title_match.group(1) if title_match
                else f"幻灯片 {len(self._slides_html)}"
            )

        self._update_thumbnails()
        if self._slides_html:
            self._show_slide(
                min(self._current_slide, len(self._slides_html) - 1)
            )
        self._slide_label.setText(f"幻灯片: {len(self._slides_html)} 页")

        # 任务 4.1：自动保存版本快照
        # 用 try/except 保护：HistoryMixin 未挂载时不影响主流程
        try:
            self._save_snapshot()
        except AttributeError:
            pass

    def _md_to_html(self, md_text: str) -> str:
        """
        Markdown → HTML 片段。

        处理流程：
          1. 保存原始 Markdown（用于提取图片信息）
          2. 任务 5.1：处理 {{number: ...}} 动态数字
          3. 任务 5.3：处理 {{video: ...}} 视频嵌入
          4. 任务 5.2：处理 {#id} morph 标记
          5. 任务 2.2：提取样式覆盖
          6. markdown 渲染（fenced_code / tables / md_in_html）
          7. 任务 2.2：应用样式覆盖到 HTML
          8. 任务 2.3：应用图片信息到 HTML
          9. 任务 5.2：应用 morph id 到 HTML

        支持扩展：
          - fenced_code   : ``` 代码块
          - tables        : | 表格 |
          - md_in_html    : HTML 块内继续解析 Markdown（任务 2.1）
        """
        # 保存原始 Markdown（用于提取图片信息）
        original_md_text = md_text

        # 任务 5.1：动态数字
        try:
            md_text = self._process_dynamic_numbers(md_text)
        except AttributeError:
            pass

        # 任务 5.3：视频嵌入
        try:
            md_text = self._process_videos(md_text)
        except AttributeError:
            pass

        # 任务 5.2：处理 morph id
        try:
            md_text = self._process_morph_ids(md_text)
        except AttributeError:
            pass

        # 任务 2.2：提取样式覆盖
        styles_map = {}
        try:
            from beeoffice.plugins.beeshow_element_editor import (
                MarkdownStylePatcher,
            )
            styles_map = MarkdownStylePatcher.extract_styles(md_text)
            # 从 md_text 移除样式注释（避免污染渲染）
            md_text = re.sub(
                r'<!--\s*beeoffice-style:.*?-->',
                '',
                md_text,
                flags=re.DOTALL,
            )
        except Exception:
            pass

        import markdown
        html = markdown.markdown(
            md_text,
            extensions=['fenced_code', 'tables', 'md_in_html'],
        )

        # 任务 2.2：应用样式覆盖
        if styles_map:
            try:
                from beeoffice.plugins.beeshow_element_editor import (
                    MarkdownStylePatcher,
                )
                html = MarkdownStylePatcher.apply_styles_to_html(
                    html, styles_map
                )
            except Exception as e:
                logging.warning(f"应用元素样式失败：{e}")

        # 任务 2.3：应用图片信息
        images_map = {}
        try:
            from beeoffice.plugins.beeshow_image_editor import (
                MarkdownImagePatcher,
            )
            images_map = MarkdownImagePatcher.extract_images(
                original_md_text
            )
            if images_map:
                html = MarkdownImagePatcher.apply_images_to_html(
                    html, images_map
                )
        except Exception as e:
            logging.warning(f"应用图片样式失败：{e}")

        # 任务 5.2：应用 morph id
        try:
            html = self._apply_morph_ids_to_html(html)
        except AttributeError:
            pass

        return html

    # ==================== 缩略图 ====================
    def _update_thumbnails(self):
        """刷新右侧缩略图列表，选中当前页"""
        self._thumb_list.clear()
        for i, title in enumerate(self._slide_titles):
            item = QListWidgetItem(f"{i+1}. {title[:25]}")
            if i == self._current_slide:
                item.setSelected(True)
            self._thumb_list.addItem(item)

    def _on_thumb_clicked(self, item):
        """缩略图单击：切换当前页"""
        idx = self._thumb_list.row(item)
        if 0 <= idx < len(self._slides_html):
            self._show_slide(idx)

    def _on_thumb_double_clicked(self, item):
        """缩略图双击：重命名标题"""
        idx = self._thumb_list.row(item)
        if not (0 <= idx < len(self._slide_titles)):
            return
        new_title, ok = QInputDialog.getText(
            self, tr("auto.beeshow_slide_mixin.1cd80fd7", "重命名"), tr("auto.beeshow_slide_mixin.cc35063f", "幻灯片标题:"), text=self._slide_titles[idx]
        )
        if ok and new_title.strip():
            self._slide_titles[idx] = new_title.strip()
            self._update_thumbnails()

    # ==================== 拖拽排序（P1-13） ====================
    def _on_slides_reordered(self, parent, start, end, dest, dest_row):
        """
        拖拽排序幻灯片（P1-13：保留 Markdown 源，不丢失 # 标题）。

        原实现用 re.sub(r'<[^>]+>', '', html) 反推 Markdown，
        会丢失 # 标题标记。改为直接调整 _slides_md 列表。

        参数含义由 Qt QListWidget rowsMoved 信号提供：
          parent   : 父 QModelIndex（此处忽略）
          start    : 起始行
          end      : 结束行
          dest     : 目标父（此处忽略）
          dest_row : 插入位置
        """
        # 同步调整 4 个平行列表
        for lst in [
            self._slides_html,
            self._slides_md,
            self._speaker_notes,
            self._slide_titles,
        ]:
            if start < len(lst):
                item = lst.pop(start)
                insert_at = dest_row if dest_row <= len(lst) else len(lst)
                lst.insert(insert_at, item)

        # 用保留的 Markdown 源重建编辑器内容
        parts = []
        for i, md in enumerate(self._slides_md):
            note = ""
            if i < len(self._speaker_notes) and self._speaker_notes[i]:
                note = f"\n<!-- {self._speaker_notes[i]} -->"
            parts.append(md + note)

        # blockSignals 避免 setPlainText 触发 textChanged → 递归 _update_preview
        self._editor.blockSignals(True)
        self._editor.setPlainText('\n---\n'.join(parts))
        self._editor.blockSignals(False)
        self._update_preview()

    # ==================== 增删 ====================
    def _add_slide(self):
        """在光标处插入新幻灯片（--- 分隔 + 默认标题）"""
        self._editor.textCursor().insertText("\n\n---\n\n## 新幻灯片")
        self._update_preview()

    def _delete_slide(self):
        """删除当前幻灯片（至少保留一张）"""
        if len(self._slides_html) <= 1:
            return
        text = self._editor.toPlainText()
        parts = re.split(r'\n---', text)
        if self._current_slide < len(parts):
            parts.pop(self._current_slide)
            self._editor.setPlainText('\n---'.join(parts))
            # P1-13：删除后必须刷新预览，重建 _slides_md
            self._update_preview()

    # ==================== 插件兼容别名 ====================
    def add_slide(self):
        """添加幻灯片（供插件调用）"""
        self._add_slide()

    def delete_slide(self):
        """删除幻灯片（供插件调用）"""
        self._delete_slide()

    # ==================== 渲染预览 ====================
    def _show_slide(self, index: int):
        """
        渲染指定页到 _preview（QWebEngineView）。

        注入的 JS（按顺序）：
          - dynamic_js  : 任务 5.1 动态数字
          - editor_js   : 任务 2.2 元素编辑器
          - image_js    : 任务 2.3 图片编辑器

        同步：
          - _current_slide
          - 缩略图选中态
          - _notes_editor 内容
          - 广播翻页（任务 4.3）
        """
        if 0 <= index < len(self._slides_html):
            self._current_slide = index
            theme = SLIDE_THEMES[self._current_theme]
            bg = self._custom_bg or theme.get("bg", "#FFF")

            # 任务 5.1：动态数字 JS
            dynamic_js = ""
            try:
                dynamic_js = self._get_dynamic_number_js()
            except AttributeError:
                pass

            # 任务 2.2：元素编辑器 JS
            editor_js = ""
            try:
                from beeoffice.plugins.beeshow_element_editor import (
                    get_element_editor_js,
                )
                editor_js = get_element_editor_js()
            except Exception:
                pass

            # 任务 2.3：图片编辑器 JS
            image_js = ""
            try:
                from beeoffice.plugins.beeshow_image_editor import (
                    get_image_editor_js,
                )
                image_js = get_image_editor_js()
            except Exception:
                pass

            # 任务 2.1：拼入版式 CSS
            full_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
            <style>{theme['css']}{self._get_layout_css()} body {{ background: {bg}; }}</style></head>
            <body><div class="slide">{self._slides_html[index]}</div>
            <div class="slide-number">{index+1}/{len(self._slides_html)}</div>{dynamic_js}{editor_js}{image_js}</body></html>"""

            self._preview.setHtml(full_html)
            self._update_thumbnails()

            # 同步备注编辑器（blockSignals 避免反向写回）
            if index < len(self._speaker_notes):
                self._notes_editor.blockSignals(True)
                self._notes_editor.setPlainText(self._speaker_notes[index])
                self._notes_editor.blockSignals(False)

            # 预加载标记
            if (index + 1 < len(self._slides_html)
                    and index + 1 not in self._preloaded_slides):
                self._preloaded_slides.add(index + 1)

            # 任务 4.3：广播翻页
            try:
                self._broadcast_slide()
            except AttributeError:
                pass

    # ==================== 主题 / 备注 / 背景 ====================
    def _on_theme_changed(self, theme: str):
        """主题切换：清缓存并重渲染当前页"""
        self._current_theme = theme
        self._css_cache.clear()
        self._preloaded_slides.clear()
        if self._slides_html:
            self._show_slide(self._current_slide)

        # 任务 4.3：广播主题
        try:
            self._broadcast_theme(theme)
        except AttributeError:
            pass

    def _on_notes_changed(self):
        """备注编辑器内容变化：同步回 _speaker_notes 平行列表"""
        if 0 <= self._current_slide < len(self._speaker_notes):
            self._speaker_notes[self._current_slide] = (
                self._notes_editor.toPlainText()
            )

    def _customize_background(self):
        """弹出颜色选择器，设置自定义背景色"""
        col = QColorDialog.getColor()
        if col.isValid():
            self._custom_bg = col.name()
            if self._slides_html:
                self._show_slide(self._current_slide)

    # ==================== 元素编辑回调（任务 2.2） ====================
    def _on_element_edit_applied(self, data: dict):
        """
        接收元素编辑回调，更新 Markdown 源。

        :param data: {"path": ..., "text": ..., "styles": {...}}
        """
        try:
            from beeoffice.plugins.beeshow_element_editor import (
                MarkdownStylePatcher,
            )

            path = data.get("path", "")
            styles = data.get("styles", {})
            if not path or not styles:
                return

            # 取当前页 Markdown
            if not (0 <= self._current_slide < len(self._slides_md)):
                return
            current_md = self._slides_md[self._current_slide]

            # 更新样式
            new_md = MarkdownStylePatcher.upsert_style(
                current_md, path, styles
            )

            # 写回编辑器
            text = self._editor.toPlainText()
            parts = re.split(r'\n---', text)
            if self._current_slide < len(parts):
                parts[self._current_slide] = new_md
                self._editor.blockSignals(True)
                self._editor.setPlainText('\n---\n'.join(parts))
                self._editor.blockSignals(False)
                self._update_preview()
                self._set_status(tr("auto.beeshow_slide_mixin.a3a83ca4", "✅ 样式已应用"), 2000)

        except Exception as e:
            logging.error(f"应用元素编辑失败：{e}")
            self._set_status(f"❌ 应用失败：{e}", 3000)

    # ==================== 图片编辑回调（任务 2.3） ====================
    def _on_image_edit_applied(self, data: dict):
        """
        接收图片拖拽编辑回调（任务 2.3）。

        :param data: {"path", "x", "y", "w", "h", "align"}
        """
        try:
            from beeoffice.plugins.beeshow_image_editor import (
                MarkdownImagePatcher,
            )

            path = data.get("path", "")
            if not path:
                return

            image_info = {
                "x": data.get("x"),
                "y": data.get("y"),
                "w": data.get("w"),
                "h": data.get("h"),
                "align": data.get("align", "left"),
            }

            if not (0 <= self._current_slide < len(self._slides_md)):
                return
            current_md = self._slides_md[self._current_slide]

            new_md = MarkdownImagePatcher.upsert_image(
                current_md, path, image_info
            )

            text = self._editor.toPlainText()
            parts = re.split(r'\n---', text)
            if self._current_slide < len(parts):
                parts[self._current_slide] = new_md
                self._editor.blockSignals(True)
                self._editor.setPlainText('\n---\n'.join(parts))
                self._editor.blockSignals(False)
                self._update_preview()
                self._set_status(tr("auto.beeshow_slide_mixin.4f66081e", "✅ 图片样式已应用"), 2000)

        except Exception as e:
            logging.error(f"应用图片编辑失败：{e}")
            self._set_status(f"❌ 应用失败：{e}", 3000)