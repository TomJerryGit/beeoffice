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
import json
import logging

from beeoffice.plugins.beeshow_html import render_slide_html

from PySide6.QtWidgets import (
    QMenu,
    QDialog, QVBoxLayout, QFormLayout, QComboBox, QCheckBox, QDialogButtonBox,
    QListWidgetItem, QInputDialog, QColorDialog,
)
from PySide6.QtCore import QTimer
from PySide6.QtGui import QTextCursor

from beeoffice.plugins.beeshow_constants import SLIDE_THEMES
from beeoffice.plugins.beeshow_animation import TRANSITIONS


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

        try:
            from beeoffice.plugins.beeshow_master import parse_master
            self._master_config, _ = parse_master(text)
        except Exception:
            self._master_config = {}

        raw_parts = re.split(r'\n---', text)

        self._slides_html = []
        self._slides_md = []           # P1-13：同步清空
        self._slide_animations = []
        self._native_shapes = []
        self._native_charts = []
        self._native_tables = []
        self._table_styles = []
        self._speaker_notes = []
        self._slide_titles = []

        for part in raw_parts:
            part = part.strip()
            if not part:
                continue

            # 提取演讲备注：**只匹配普通注释**。
            # 优化规划 §2.7：原正则 `<!--\s*(.*?)\s*-->` 会匹配第一个注释而不看
            # 内容，于是 `<!-- beeoffice-style: {...} -->` 这类特殊标记会被当成
            # 演讲备注（备注里塞进一段 JSON），同时该标记也被删掉。
            # 负向前瞻放在 `<!--` 之后、`\s*` 之前，避免 `\s*` 回溯后又匹配上。
            nm = re.search(
                r'<!--(?!\s*(?:comments:|beeoffice-style:|beeoffice-image:'
                r'|morph-id:|beeoffice-shapes:|beeoffice-master:|beeoffice-chartobj:|beeoffice-tableobj:|beeoffice-table-style:))\s*(.*?)\s*-->',
                part,
                re.DOTALL,
            )
            if nm:
                self._speaker_notes.append(nm.group(1).strip())
                part = part.replace(nm.group(0), '', 1).strip()
            else:
                self._speaker_notes.append('')

            # 优化规划 §2.7：特殊标记必须**留在 _slides_md** 里。
            # `_on_slides_reordered()` 会用 _slides_md 重建整个编辑器文本，
            # 此前这里把三类标记全部剥掉，导致**任何一次拖动排序都会永久删除**
            # 该页的评论 / 样式覆盖 / 图片位置。
            # `beeshow_notes_mixin._remove_plain_comment()` 的 docstring 也明确
            # 写着这些前缀必须保留 —— 说明 _slides_md 的设计意图本就是保留标记。
            source = part
            from beeoffice.plugins.beeshow_native_shapes import parse_shapes
            native_shapes, cleaned_part = parse_shapes(part)
            from beeoffice.plugins.beeshow_native_chart import parse_charts
            native_charts, cleaned_part = parse_charts(cleaned_part)
            from beeoffice.plugins.beeshow_native_table import parse_tables
            native_tables, cleaned_part = parse_tables(cleaned_part)
            from beeoffice.plugins.beeshow_pptx_table_style import parse_table_style
            table_style, cleaned_part = parse_table_style(cleaned_part)
            from beeoffice.plugins.beeshow_animation import parse_animation
            anim_cfg, cleaned_part = parse_animation(cleaned_part)

            # 预览 HTML：只剥掉 comments（它就是一段 HTML 注释，留着不可见但没必要）；
            # beeoffice-style / beeoffice-image 必须**交给** _md_to_html ——
            # 它自己会先 extract_styles / 提取图片信息再剥离渲染。此前提前剥掉
            # 会让预览丢失用户的样式覆盖与图片位置。
            html_part = re.sub(
                r'<!--\s*comments:.*?-->',
                '',
                cleaned_part,
                flags=re.DOTALL,
            ).strip()

            if source:
                html = self._md_to_html(html_part)
                self._slides_html.append(html)
                self._slides_md.append(source)    # P1-13：保留源文本（含特殊标记）
                self._slide_animations.append(anim_cfg)
                self._native_shapes.append(native_shapes)
                self._native_charts.append(native_charts)
                self._native_tables.append(native_tables)
                self._table_styles.append(table_style)

                # 提取标题
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

    def _show_animation_panel(self):
        """打开动画面板，编辑当前页选择器动画/切换效果。"""
        from beeoffice.plugins.beeshow_animation_panel import (
            AnimationPanelDialog,
        )

        try:
            current = self._slide_animations[self._current_slide] or {}
        except (AttributeError, IndexError):
            current = {}
        dlg = AnimationPanelDialog(current, self)
        if dlg.exec() == dlg.Accepted:
            self._slide_animations[self._current_slide] = dlg.get_config()
            self._show_slide(self._current_slide)
            self._set_status("🎬 动画已更新", 2500)
            try:
                self.contentChanged.emit()
            except Exception:  # noqa: BLE001
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
            prefix = "[隐藏] " if i in getattr(self, "_slide_hidden", set()) else ""
            item = QListWidgetItem(f"{i+1}. {prefix}{title[:25]}")
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
            self, "重命名", "幻灯片标题:", text=self._slide_titles[idx]
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

    def _duplicate_slide(self):
        """复制当前幻灯片到下一页。"""
        if not getattr(self, "_slides_md", None):
            return
        idx = self._current_slide
        if not (0 <= idx < len(self._slides_md)):
            return
        self._slides_md.insert(idx + 1, self._slides_md[idx])
        self._slides_html.insert(idx + 1, self._slides_html[idx])
        title = self._slide_titles[idx] if idx < len(self._slide_titles) else "幻灯片"
        self._slide_titles.insert(idx + 1, title + " 副本")
        self._speaker_notes.insert(idx + 1, self._speaker_notes[idx] if idx < len(self._speaker_notes) else "")
        self._slide_animations.insert(idx + 1, self._slide_animations[idx] if idx < len(self._slide_animations) else {})
        parts = []
        for i, md in enumerate(self._slides_md):
            note = ""
            if i < len(self._speaker_notes) and self._speaker_notes[i]:
                note = f"\n<!-- {self._speaker_notes[i]} -->"
            parts.append(md + note)
        self._editor.blockSignals(True)
        self._editor.setPlainText("\n---\n".join(parts))
        self._editor.blockSignals(False)
        self._update_preview()
        self._show_slide(idx + 1)
        self._set_status("已复制幻灯片", 2000)

    def _toggle_hide_slide(self):
        """隐藏/显示当前幻灯片（缩略图标记，放映时仍建议手动核对）。"""
        if not getattr(self, "_slides_md", None):
            return
        if not hasattr(self, "_slide_hidden"):
            self._slide_hidden = set()
        idx = self._current_slide
        if idx in self._slide_hidden:
            self._slide_hidden.discard(idx)
            self._set_status("已取消隐藏", 2000)
        else:
            self._slide_hidden.add(idx)
            self._set_status("已隐藏幻灯片", 2000)
        self._update_thumbnails()

    # ==================== 增删 ====================
    def _add_slide(self):
        """在文档末尾追加新幻灯片（`---` 分隔 + 默认标题）。

        2026-10-21 修复（GUI 实跑发现）：
        - 原实现 `insertText("\\n\\n---\\n\\n## 新幻灯片")` **结尾没有换行**，
          且插入点取当前光标（新建演示时光标在文首）；
        - 结果：`## 新幻灯片` 与原有首行 `# 欢迎使用蜜演` 粘成同一标题
          （`新幻灯片# 欢迎使用蜜演 🎥`），按 `\\n---` 切分后**页数不变**（2→2）。

        修复：光标移到文末再插入，并保证插入串以换行结尾 → 页数 +1、标题独立。
        """
        cursor = self._editor.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText("\n\n---\n\n## 新幻灯片\n")
        self._editor.setTextCursor(cursor)
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
            # 4.6：编辑器内翻页时也累计当前页排练耗时（若正在排练）
            if hasattr(self, "_record_rehearsal_page"):
                self._record_rehearsal_page(self._current_slide)
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
            # 优化规划 §3.3：骨架统一走 beeshow_html.render_slide_html()
            from beeoffice.plugins.beeshow_native_shapes import shapes_html
            inner = self._slides_html[index]
            if index < len(getattr(self, '_native_shapes', [])):
                inner += shapes_html(self._native_shapes[index])
            if index < len(getattr(self, '_native_charts', [])):
                from beeoffice.plugins.beeshow_native_chart import chart_html
                inner += chart_html(self._native_charts[index])
            if index < len(getattr(self, '_native_tables', [])):
                from beeoffice.plugins.beeshow_native_table import table_html
                inner += table_html(self._native_tables[index])
            full_html = render_slide_html(
                inner,
                theme_css=theme['css'],
                layout_css=self._get_layout_css(),
                bg=bg,
                extra_css=(getattr(self, '_font_css', '') + getattr(self, '_slide_size_css', '') + getattr(self, '_guides_css', '') + getattr(self, '_master_css', '') + __import__('beeoffice.plugins.beeshow_master', fromlist=['master_css']).master_css(getattr(self, '_master_config', {}) or {'title_font':'Microsoft YaHei','body_font':'Microsoft YaHei'})),
                body_extra=(
                    f'<div class="slide-number">'
                    f"{index + 1}/{len(self._slides_html)}</div>"
                    f"{dynamic_js}{editor_js}{image_js}"
                    f"{self._canvas_js_for(index)}"
                    f"{self._native_shape_js_for(index)}"
                    f"{__import__('beeoffice.plugins.beeshow_master', fromlist=['overlay_html']).overlay_html(getattr(self, '_master_config', {}) or {}, index + 1)}"
                ),
            )

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

    # ==================== 画布编辑 ====================
    def _canvas_js_for(self, index):
        try:
            from beeoffice.plugins.beeshow_canvas import get_canvas_edit_js
            overrides = getattr(self, "_canvas_overrides", {})
            deleted = getattr(self, "_canvas_deleted", {})
            return get_canvas_edit_js(
                overrides.get(index, {}), deleted.get(index, [])
            )
        except Exception:
            return ""

    def _canvas_history(self):
        if not hasattr(self, "_canvas_undo_stack"):
            self._canvas_undo_stack = []
        return self._canvas_undo_stack

    def _on_canvas_edit_applied(self, data):
        idx = self._current_slide
        if not hasattr(self, "_canvas_overrides"):
            self._canvas_overrides = {}
        stack = self._canvas_history()
        stack.append((dict(self._canvas_overrides.get(idx, {})), list(getattr(self, "_canvas_deleted", {}).get(idx, []))))
        self._canvas_overrides.setdefault(idx, {})[int(data.get("index", 0))] = {
            "left": float(data.get("left", 0)),
            "top": float(data.get("top", 0)),
            "width": float(data.get("width", 0) or 0),
            "height": float(data.get("height", 0) or 0),
        }
        self._show_slide(idx)

    def _on_canvas_delete(self, data):
        idx = self._current_slide
        if not hasattr(self, "_canvas_deleted"):
            self._canvas_deleted = {}
        stack = self._canvas_history()
        stack.append((dict(self._canvas_overrides.get(idx, {})), list(self._canvas_deleted.get(idx, []))))
        self._canvas_deleted.setdefault(idx, []).append(int(data.get("index", 0)))
        self._show_slide(idx)

    def _canvas_undo(self):
        stack = self._canvas_history()
        if not stack:
            self._set_status("没有可撤销的画布操作", 2000)
            return
        overrides, deleted = stack.pop()
        idx = self._current_slide
        if not hasattr(self, "_canvas_overrides"):
            self._canvas_overrides = {}
        if not hasattr(self, "_canvas_deleted"):
            self._canvas_deleted = {}
        self._canvas_overrides[idx] = overrides
        self._canvas_deleted[idx] = deleted
        self._show_slide(idx)
        self._set_status("已撤销画布操作", 2000)

    def _canvas_reset(self):
        idx = self._current_slide
        if hasattr(self, "_canvas_overrides"):
            self._canvas_overrides.pop(idx, None)
        if hasattr(self, "_canvas_deleted"):
            self._canvas_deleted.pop(idx, None)
        self._show_slide(idx)
        self._set_status("已重置当前页画布", 2000)

    def _native_shape_js_for(self, index):
        try:
            from beeoffice.plugins.beeshow_native_shapes import get_native_shape_edit_js
            shapes = getattr(self, "_native_shapes", [])
            if index < len(shapes) and shapes[index]:
                return get_native_shape_edit_js(len(shapes[index]))
        except Exception:
            pass
        return ""

    def _on_native_shape_edit(self, data):
        try:
            idx = int(data.get("index", -1))
        except Exception:
            return
        shapes = self._native_shapes[self._current_slide]
        if not (0 <= idx < len(shapes)):
            return
        for key in ("x", "y", "w", "h", "rotation"):
            if key in data:
                try:
                    shapes[idx][key] = float(data[key])
                except Exception:
                    pass
        self._persist_native_shapes_current()

    # ==================== 图表 ====================
    def _show_chart_dialog(self):
        from PySide6.QtWidgets import (
            QDialog, QVBoxLayout, QComboBox, QPlainTextEdit,
            QDialogButtonBox, QLabel,
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("插入原生图表")
        dlg.resize(460, 380)
        layout = QVBoxLayout(dlg)
        kind = QComboBox()
        kind.addItems(["柱状图", "折线图", "饼图"])
        layout.addWidget(kind)
        layout.addWidget(QLabel("数据（每行：标签,数值）"))
        data = QPlainTextEdit("一月,100\n二月,120\n三月,90\n四月,150")
        layout.addWidget(data)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        if dlg.exec() != QDialog.Accepted:
            return
        if not hasattr(self, "_native_charts"):
            self._native_charts = []
        while len(self._native_charts) <= self._current_slide:
            self._native_charts.append([])
        self._native_charts[self._current_slide].append({
            "type": {"柱状图": "bar", "折线图": "line", "饼图": "pie"}[kind.currentText()],
            "title": "BeeShow 图表",
            "data": data.toPlainText(),
        })
        self._persist_native_charts_current()
        self._set_status("已插入原生图表", 2000)

    def _persist_native_charts_current(self):
        from beeoffice.plugins.beeshow_native_chart import marker_for
        import re as _re
        idx = self._current_slide
        while len(self._native_charts) <= idx:
            self._native_charts.append([])
        if isinstance(self._native_charts[idx], dict):
            self._native_charts[idx] = [self._native_charts[idx]]
        marker = marker_for(self._native_charts[idx])
        md = _re.sub(r"<!--\s*beeoffice-chartobj:.*?-->", "", self._slides_md[idx], flags=_re.DOTALL).strip()
        self._slides_md[idx] = (md + "\n" + marker).strip()
        self._rebuild_editor_from_slides()
        self._show_slide(idx)

    # ==================== 版式槽位绑定 ====================
    def _apply_layout_slots(self, layout_id, slots):
        from beeoffice.plugins.beeshow_layout_slots import bind_layout
        md = bind_layout(layout_id, slots)
        if not md:
            return False
        if not getattr(self, "_slides_md", None):
            self._editor.setPlainText(md)
            self._update_preview()
            return True
        self._slides_md[self._current_slide] = md
        self._rebuild_editor_from_slides()
        self._show_slide(self._current_slide)
        self._set_status("版式槽位已填充", 2000)
        return True

    def _show_layout_slot_dialog(self):
        from PySide6.QtWidgets import (
            QDialog, QComboBox, QLineEdit, QTextEdit, QFormLayout,
            QDialogButtonBox, QFileDialog,
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("版式槽位填充")
        dlg.resize(520, 420)
        form = QFormLayout(dlg)
        combo = QComboBox()
        for layout_id, meta in __import__("beeoffice.plugins.beeshow_constants", fromlist=["LAYOUTS"]).LAYOUTS.items():
            combo.addItem(f"{meta['icon']} {meta['name']}", layout_id)
        form.addRow("版式", combo)
        title = QLineEdit(); form.addRow("标题", title)
        subtitle = QLineEdit(); form.addRow("副标题", subtitle)
        body = QTextEdit(); body.setPlaceholderText("每行一个要点"); body.setMaximumHeight(110); form.addRow("正文要点", body)
        image = QLineEdit(); form.addRow("图片路径", image)
        caption = QLineEdit(); form.addRow("图片说明", caption)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() != QDialog.Accepted:
            return
        self._apply_layout_slots(combo.currentData(), {
            "title": title.text(), "subtitle": subtitle.text(),
            "body": body.toPlainText(), "image": image.text(),
            "caption": caption.text(),
        })

    # ==================== 母版 / 视图模式 ====================
    def _show_master_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("幻灯片母版")
        form = QFormLayout(dlg)
        font = QComboBox()
        font.addItems(["Microsoft YaHei", "SimSun", "SimHei", "KaiTi", "Arial"])
        form.addRow("统一样式字体", font)
        bg = QComboBox()
        bg.addItems(["默认主题背景", "白色", "浅灰", "米色", "深色"])
        form.addRow("母版背景", bg)
        from PySide6.QtWidgets import QLineEdit, QCheckBox
        footer = QLineEdit()
        footer.setPlaceholderText("例如：XX 公司 · 内部资料")
        form.addRow("母版页脚", footer)
        page_no = QCheckBox("显示页码")
        page_no.setChecked(True)
        form.addRow("页码", page_no)
        title_color = QLineEdit("#E67E22")
        form.addRow("标题颜色", title_color)
        date_text = QLineEdit()
        date_text.setPlaceholderText("例如：2026-11-17")
        form.addRow("日期占位符", date_text)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() != QDialog.Accepted:
            return
        self._apply_unified_font(font.currentText())
        chosen = bg.currentText()
        if chosen == "默认主题背景":
            self._custom_bg = ""
        else:
            self._custom_bg = {"白色": "#FFFFFF", "浅灰": "#F5F5F5",
                               "米色": "#FFF8E1", "深色": "#263238"}[chosen]
        from beeoffice.plugins.beeshow_master import marker_for
        cfg = dict(getattr(self, "_master_config", {}) or {})
        cfg.update({
            "title_font": font.currentText(),
            "title_color": title_color.text().strip() or "#E67E22",
            "footer": footer.text().strip(),
            "date": date_text.text().strip(),
            "show_date": bool(date_text.text().strip()),
            "show_page": page_no.isChecked(),
        })
        self._master_config = cfg
        if self._slides_md:
            import re as _re
            md = _re.sub(r"<!--\s*beeoffice-master:.*?-->", "", self._slides_md[0], flags=_re.DOTALL).strip()
            self._slides_md[0] = marker_for(cfg) + "\n" + md
            self._rebuild_editor_from_slides()
        self._show_slide(self._current_slide)
        self._set_status("母版占位符样式已应用", 2000)

    def _toggle_slide_sorter(self):
        self._view_mode = "sorter" if getattr(self, "_view_mode", "normal") != "sorter" else "normal"
        self._thumb_list.setMaximumWidth(280 if self._view_mode == "sorter" else 180)
        self._set_status("幻灯片浏览视图" if self._view_mode == "sorter" else "普通视图", 2000)

    def _toggle_notes_view(self):
        visible = getattr(self, "_notes_editor", None) is not None and self._notes_editor.isVisible()
        if getattr(self, "_notes_editor", None) is not None:
            self._notes_editor.setVisible(not visible)
        self._set_status("隐藏备注" if visible else "显示备注", 2000)

    def _show_reading_view(self):
        self._preview.setFocus()
        self._set_status("阅读视图：使用 F5 进入全屏放映", 3000)

    # ==================== 原生形状 ====================
    def _add_native_shape(self, kind, text=""):
        if not hasattr(self, "_native_shapes"):
            self._native_shapes = []
        while len(self._native_shapes) <= self._current_slide:
            self._native_shapes.append([])
        shape = {"kind": kind, "x": 10, "y": 10, "w": 30, "h": 15,
                 "text": text or ("文本" if kind == "text" else ""),
                 "fill": "#FFF3E0", "line": "#E67E22"}
        self._native_shapes[self._current_slide].append(shape)
        from beeoffice.plugins.beeshow_native_shapes import marker_for
        marker = marker_for(self._native_shapes[self._current_slide])
        md = self._slides_md[self._current_slide]
        md = __import__("re").sub(r"<!--\s*beeoffice-shapes:.*?-->", "", md, flags=__import__("re").DOTALL).strip()
        self._slides_md[self._current_slide] = md + "\n" + marker
        self._rebuild_editor_from_slides()
        self._show_slide(self._current_slide)
        self._set_status("已添加原生形状", 2000)

    def _persist_native_shapes_current(self):
        from beeoffice.plugins.beeshow_native_shapes import marker_for
        import re as _re
        idx = self._current_slide
        while len(self._native_shapes) <= idx:
            self._native_shapes.append([])
        marker = marker_for(self._native_shapes[idx])
        md = self._slides_md[idx]
        md = _re.sub(r"<!--\s*beeoffice-shapes:.*?-->", "", md, flags=_re.DOTALL).strip()
        self._slides_md[idx] = (md + "\n" + marker).strip()
        self._rebuild_editor_from_slides()
        self._show_slide(idx)

    def _update_native_shape(self, index, props):
        shapes = self._native_shapes[self._current_slide]
        if 0 <= index < len(shapes):
            shapes[index].update(props)
            self._persist_native_shapes_current()
            return True
        return False

    def _delete_native_shape(self, index):
        shapes = self._native_shapes[self._current_slide]
        if 0 <= index < len(shapes):
            shapes.pop(index)
            self._persist_native_shapes_current()
            return True
        return False

    def _move_native_shape_layer(self, index, delta):
        shapes = self._native_shapes[self._current_slide]
        target = index + delta
        if 0 <= index < len(shapes) and 0 <= target < len(shapes):
            shapes[index], shapes[target] = shapes[target], shapes[index]
            self._persist_native_shapes_current()
            return True
        return False

    def _align_native_shapes(self, indices, mode):
        shapes = self._native_shapes[self._current_slide]
        chosen = [shapes[i] for i in indices if 0 <= i < len(shapes)]
        if len(chosen) < 2:
            return False
        left = min(float(s.get("x", 0)) for s in chosen)
        right = max(float(s.get("x", 0)) + float(s.get("w", 30)) for s in chosen)
        top = min(float(s.get("y", 0)) for s in chosen)
        bottom = max(float(s.get("y", 0)) + float(s.get("h", 15)) for s in chosen)
        cx = (left + right) / 2; cy = (top + bottom) / 2
        for s in chosen:
            if mode == "left": s["x"] = left
            elif mode == "right": s["x"] = right - float(s.get("w", 30))
            elif mode == "center": s["x"] = cx - float(s.get("w", 30)) / 2
            elif mode == "top": s["y"] = top
            elif mode == "bottom": s["y"] = bottom - float(s.get("h", 15))
            elif mode == "middle": s["y"] = cy - float(s.get("h", 15)) / 2
        self._persist_native_shapes_current()
        return True

    def _distribute_native_shapes(self, indices, axis="h"):
        shapes = self._native_shapes[self._current_slide]
        chosen = [(i, shapes[i]) for i in indices if 0 <= i < len(shapes)]
        if len(chosen) < 3:
            return False
        key = (lambda p: float(p[1].get("x", 0))) if axis == "h" else (lambda p: float(p[1].get("y", 0)))
        chosen.sort(key=key)
        if axis == "h":
            first = float(chosen[0][1].get("x", 0))
            last = float(chosen[-1][1].get("x", 0)) + float(chosen[-1][1].get("w", 30))
            total = sum(float(s.get("w", 30)) for _, s in chosen)
            gap = (last - first - total) / (len(chosen) - 1)
            pos = first
            for _, s in chosen:
                s["x"] = pos
                pos += float(s.get("w", 30)) + gap
        else:
            first = float(chosen[0][1].get("y", 0))
            last = float(chosen[-1][1].get("y", 0)) + float(chosen[-1][1].get("h", 15))
            total = sum(float(s.get("h", 15)) for _, s in chosen)
            gap = (last - first - total) / (len(chosen) - 1)
            pos = first
            for _, s in chosen:
                s["y"] = pos
                pos += float(s.get("h", 15)) + gap
        self._persist_native_shapes_current()
        return True

    def _show_align_distribute_dialog(self):
        from PySide6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
            QPushButton, QDialogButtonBox,
        )
        if not getattr(self, "_native_shapes", None) or not self._native_shapes[self._current_slide]:
            return
        shapes = self._native_shapes[self._current_slide]
        dlg = QDialog(self)
        dlg.setWindowTitle("对齐与分布")
        layout = QVBoxLayout(dlg)
        lst = QListWidget()
        for i, s in enumerate(shapes):
            item = QListWidgetItem(f"{i + 1}. {s.get('kind')} {s.get('text', '')[:20]}")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            lst.addItem(item)
        layout.addWidget(lst)
        row1 = QHBoxLayout()
        for label, mode in (("左对齐", "left"), ("水平居中", "center"), ("右对齐", "right")):
            b = QPushButton(label); b.clicked.connect(lambda checked=False, m=mode: (self._align_native_shapes(self._checked_rows(lst), m), dlg.accept())); row1.addWidget(b)
        row2 = QHBoxLayout()
        for label, mode in (("顶端对齐", "top"), ("垂直居中", "middle"), ("底端对齐", "bottom")):
            b = QPushButton(label); b.clicked.connect(lambda checked=False, m=mode: (self._align_native_shapes(self._checked_rows(lst), m), dlg.accept())); row2.addWidget(b)
        row3 = QHBoxLayout()
        for label, axis in (("水平等距分布", "h"), ("垂直等距分布", "v")):
            b = QPushButton(label); b.clicked.connect(lambda checked=False, ax=axis: (self._distribute_native_shapes(self._checked_rows(lst), ax), dlg.accept())); row3.addWidget(b)
        layout.addLayout(row1); layout.addLayout(row2); layout.addLayout(row3)
        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        dlg.exec()

    @staticmethod
    def _checked_rows(lst):
        return [i for i in range(lst.count()) if lst.item(i).checkState() == Qt.Checked]

    def _show_shape_manager(self):
        from PySide6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton,
            QFormLayout, QLineEdit, QDoubleSpinBox, QSpinBox, QDialogButtonBox,
        )
        if not hasattr(self, "_native_shapes"):
            self._native_shapes = []
        while len(self._native_shapes) <= self._current_slide:
            self._native_shapes.append([])
        shapes = self._native_shapes[self._current_slide]
        dlg = QDialog(self)
        dlg.setWindowTitle("原生形状管理")
        dlg.resize(620, 420)
        layout = QVBoxLayout(dlg)
        lst = QListWidget()
        for i, s in enumerate(shapes):
            lst.addItem(f"{i + 1}. {s.get('kind')} {s.get('text', '')[:20]}")
        layout.addWidget(lst)
        form = QFormLayout()
        text_edit = QLineEdit()
        x = QDoubleSpinBox(); x.setRange(0, 100); x.setSuffix(" %")
        y = QDoubleSpinBox(); y.setRange(0, 100); y.setSuffix(" %")
        w = QDoubleSpinBox(); w.setRange(1, 100); w.setSuffix(" %")
        h = QDoubleSpinBox(); h.setRange(1, 100); h.setSuffix(" %")
        rot = QSpinBox(); rot.setRange(-180, 180); rot.setSuffix(" °")
        fill = QLineEdit(); line = QLineEdit()
        for label, widget in (("文本", text_edit), ("X", x), ("Y", y),
                              ("宽", w), ("高", h), ("旋转", rot),
                              ("填充", fill), ("边框", line)):
            form.addRow(label, widget)
        layout.addLayout(form)

        def load_row():
            i = lst.currentRow()
            if not (0 <= i < len(shapes)):
                return
            s = shapes[i]
            text_edit.setText(str(s.get("text", "")))
            x.setValue(float(s.get("x", 10))); y.setValue(float(s.get("y", 10)))
            w.setValue(float(s.get("w", 30))); h.setValue(float(s.get("h", 15)))
            rot.setValue(int(s.get("rotation", 0) or 0))
            fill.setText(str(s.get("fill", "#FFF3E0")))
            line.setText(str(s.get("line", "#E67E22")))

        def apply_row():
            i = lst.currentRow()
            if not (0 <= i < len(shapes)):
                return
            self._update_native_shape(i, {
                "text": text_edit.text(), "x": x.value(), "y": y.value(),
                "w": w.value(), "h": h.value(), "rotation": rot.value(),
                "fill": fill.text(), "line": line.text(),
            })
            dlg.accept()

        lst.currentRowChanged.connect(lambda _: load_row())
        row = QHBoxLayout()
        for label, slot in (("应用", apply_row), ("上移一层", lambda: self._move_native_shape_layer(lst.currentRow(), 1)),
                            ("下移一层", lambda: self._move_native_shape_layer(lst.currentRow(), -1)),
                            ("删除", lambda: (self._delete_native_shape(lst.currentRow()), dlg.accept()))):
            b = QPushButton(label); b.clicked.connect(slot); row.addWidget(b)
        layout.addLayout(row)
        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        if shapes:
            lst.setCurrentRow(0); load_row()
        dlg.exec()

    def _rebuild_editor_from_slides(self):
        parts = []
        for i, md in enumerate(self._slides_md):
            note = ""
            if i < len(self._speaker_notes) and self._speaker_notes[i]:
                note = f"\n<!-- {self._speaker_notes[i]} -->"
            parts.append(md + note)
        self._editor.blockSignals(True)
        self._editor.setPlainText("\n---\n".join(parts))
        self._editor.blockSignals(False)
        self._update_preview()

    def _show_native_shape_menu(self):
        menu = QMenu(self)
        for label, kind in (("矩形", "rect"), ("椭圆", "ellipse"),
                            ("箭头", "arrow"), ("文本框", "text"),
                            ("艺术字", "art")):
            act = menu.addAction(label)
            act.triggered.connect(lambda checked=False, k=kind: self._add_native_shape(k))
        menu.exec(QCursor.pos())

    # ==================== P1：形状/艺术字/幻灯片大小 ====================
    def _insert_html_block(self, html: str, name: str):
        cursor = self._editor.textCursor()
        cursor.insertText("\n" + html + "\n")
        self._editor.setTextCursor(cursor)
        self._update_preview()
        self._set_status(f"已插入{name}", 2000)

    def _show_shape_menu(self):
        menu = QMenu(self)
        shapes = {
            "矩形": '<div style="width:240px;height:120px;border:3px solid #E67E22;background:#FFF3E0;border-radius:6px;"></div>',
            "圆形": '<div style="width:140px;height:140px;border:3px solid #1565C0;background:#E3F2FD;border-radius:50%;"></div>',
            "箭头": '<div style="font-size:48px;color:#E67E22;">➜</div>',
            "文本框": '<div style="padding:12px 16px;border:1px dashed #888;background:#FFFFFF;">在此输入文本</div>',
            "艺术字": '<div style="font-size:44px;font-weight:bold;color:#E67E22;text-shadow:2px 2px 0 #FFE0B2;">艺术字</div>',
        }
        for name, html in shapes.items():
            act = menu.addAction(name)
            act.triggered.connect(lambda checked=False, n=name, h=html: self._insert_html_block(h, n))
        menu.exec(QCursor.pos())

    def _set_slide_size_dialog(self):
        size, ok = QInputDialog.getItem(self, "幻灯片大小", "比例：", ["16:9", "4:3"], 0, False)
        if not ok:
            return
        self._slide_size = size
        self._slide_size_css = (
            ".slide{aspect-ratio:16/9;max-width:100%;}" if size == "16:9"
            else ".slide{aspect-ratio:4/3;max-width:100%;}"
        )
        self._show_slide(self._current_slide)
        self._set_status(f"幻灯片大小：{size}", 2000)

    def _toggle_guides(self):
        self._guides_on = not getattr(self, "_guides_on", False)
        self._guides_css = (
            ".slide{background-image:linear-gradient(#E0E0E0 1px,transparent 1px),"
            "linear-gradient(90deg,#E0E0E0 1px,transparent 1px);"
            "background-size:5% 5%;}"
            if self._guides_on else ""
        )
        self._show_slide(self._current_slide)
        self._set_status("参考线开" if self._guides_on else "参考线关", 2000)

    # ==================== 设计 / 过渡 ====================
    def _apply_unified_font(self, family: str):
        self._font_css = (
            f"body, h1, h2, h3, p, li, td, th {{ font-family: '{family}', "
            "'Microsoft YaHei', sans-serif; }}"
        )
        self._show_slide(self._current_slide)
        self._set_status(f"统一字体：{family}", 2000)

    def _show_design_panel(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("设计")
        form = QFormLayout(dlg)
        combo = QComboBox()
        combo.addItems(["Microsoft YaHei", "SimSun", "SimHei", "KaiTi", "Segoe UI", "Arial"])
        form.addRow("统一字体", combo)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() == QDialog.Accepted:
            self._apply_unified_font(combo.currentText())

    def _apply_transition_all(self, transition: str):
        if not hasattr(self, "_slide_animations"):
            return
        while len(self._slide_animations) < len(self._slides_html):
            self._slide_animations.append({})
        for i in range(len(self._slides_html)):
            cfg = self._slide_animations[i] or {}
            cfg["transition"] = transition
            self._slide_animations[i] = cfg
        self._show_slide(self._current_slide)
        self._set_status(f"已对全部幻灯片应用过渡：{TRANSITIONS.get(transition, transition)}", 3000)

    def _show_transition_panel(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("幻灯片过渡")
        form = QFormLayout(dlg)
        combo = QComboBox()
        for key, label in TRANSITIONS.items():
            combo.addItem(label, key)
        form.addRow("过渡效果", combo)
        apply_all = QCheckBox("应用到全部幻灯片")
        form.addRow(apply_all)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() != QDialog.Accepted:
            return
        key = combo.currentData()
        if apply_all.isChecked():
            self._apply_transition_all(key)
        else:
            while len(self._slide_animations) <= self._current_slide:
                self._slide_animations.append({})
            cfg = self._slide_animations[self._current_slide] or {}
            cfg["transition"] = key
            self._slide_animations[self._current_slide] = cfg
            self._show_slide(self._current_slide)

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
                self._set_status("✅ 样式已应用", 2000)

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
                self._set_status("✅ 图片样式已应用", 2000)

        except Exception as e:
            logging.error(f"应用图片编辑失败：{e}")
            self._set_status(f"❌ 应用失败：{e}", 3000)