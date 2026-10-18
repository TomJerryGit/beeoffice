# beeoffice/plugins/beewrite_mode_mixin.py
"""
蜜写模式切换与基础格式 Mixin

本次更新（修复全选改字号时表格字号不跟随）：
  - _on_font_size 中新增 _iter_all_tables 方法，
    使用 QTextFrame.childFrames() 递归获取所有表格，
    不依赖 cursor.currentTable()（该方法只在光标位于表格内时有效）
  - 覆盖所有表格：手动插入的表格、Markdown 转换的表格、
    DataFrame 插入的表格

其他：
  - 修复字号丢失：切模式时缓存 Markdown 源码，若未改动直接切回原富文本文档
  - 富文本模式隐藏预览栏，编辑区占满
  - 新增 _toggle_toolbars 方法（配合 ToolbarMixin 的折叠按钮）
  - 新增 _sync_mode_buttons / _apply_mode_layout 辅助方法

v5.0.2 图片修复：
  - _switch_mode 从富文本切到 Markdown 前，
    若检测到文档含图片，弹出确认提示，避免用户误以为丢图
  - 新增 _document_has_images 检测方法
    扫描所有 block 的 fragment，检查 charFormat().isImageFormat()
  - _switch_mode 从 Markdown 切回富文本时，
    调用 _apply_mode_layout 前先确保 rich_editor._current_file_dir
    已同步（保证 set_markdown 解析图片路径正确）
"""
import logging

from PySide6.QtWidgets import QMessageBox, QColorDialog
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextCharFormat, QTextCursor, QTextTable

from beeoffice.plugins.beewrite_utils import FORMAT_PAINTER
from beeoffice.i18n import tr


class ModeMixin:
    """蜜写模式切换与基础格式 Mixin"""

    # ==================================================================
    # 内容接口
    # ==================================================================
    @property
    def editor(self):
        """对外暴露的活动编辑器（当前始终指向 Markdown 源码编辑器）"""
        return self.markdown_editor

    def content(self):
        """获取当前编辑器的内容（Markdown 文本）"""
        if self._edit_mode == "markdown":
            return self.markdown_editor.toPlainText()
        return self.rich_editor.to_markdown()

    def set_content(self, text):
        """设置当前编辑器内容"""
        if self._edit_mode == "markdown":
            self.markdown_editor.setPlainText(text)
        else:
            self.rich_editor.set_markdown(text)

    def get_rendered_content(self):
        """获取渲染后的内容（数据变量已替换）"""
        return self.binding_engine.render(self.content())[0]

    def _get_active_editor(self):
        """返回当前活动编辑器控件（供 AI 等模块使用）"""
        return (
            self.rich_editor
            if self._edit_mode == "rich_text"
            else self.markdown_editor
        )

    # ==================================================================
    # 模式切换
    # ==================================================================
    def _on_md_clicked(self):
        """点击「Markdown」按钮"""
        self._switch_mode("markdown")

    def _on_rich_clicked(self):
        """点击「所见即所得」按钮"""
        self._switch_mode("rich_text")

    def _sync_mode_buttons(self):
        """同步模式按钮状态（Markdown / 所见即所得）"""
        self._md_btn.blockSignals(True)
        self._rich_btn.blockSignals(True)
        self._md_btn.setChecked(self._edit_mode == "markdown")
        self._rich_btn.setChecked(self._edit_mode == "rich_text")
        self._md_btn.blockSignals(False)
        self._rich_btn.blockSignals(False)

    def _apply_mode_layout(self, mode):
        """切换视图布局（工具栏、预览、分屏宽度、查找栏、大纲）"""
        if mode == "rich_text":
            self.editor_stack.setCurrentWidget(self.rich_editor)
            self._toolbar1.setVisible(True)
            self._toolbar2.setVisible(True)
            # 隐藏预览栏，编辑区占满
            self.preview.setVisible(False)
            sizes = self._main_splitter.sizes()
            total = sum(sizes)
            self._main_splitter.setSizes([0, total, 0, 0, 0])
        else:
            self.editor_stack.setCurrentWidget(self.markdown_editor)
            self._toolbar1.setVisible(False)
            self._toolbar2.setVisible(False)
            # 显示预览栏
            self.preview.setVisible(True)
            self._main_splitter.setSizes([0, 500, 450, 0, 0])

        # 查找栏同步绑定到新编辑器
        if self.find_bar.isVisible():
            new_editor = (
                self.rich_editor
                if mode == "rich_text"
                else self.markdown_editor
            )
            self.find_bar.set_editor(new_editor)

        # 大纲面板刷新
        if self._outline_panel.isVisible():
            self._refresh_outline_if_visible()

    # ==================================================================
    # v5.0.2 新增：图片检测
    # ==================================================================
    def _document_has_images(self) -> bool:
        """
        v5.0.2 新增：检查富文本文档是否包含图片 fragment。

        用于切换模式前给出提示：
          - 富文本 → Markdown：图片会变成 ![](path) 语法
          - 预览区无法显示图片，但源码保留路径
          - 切回富文本时从路径重新加载

        :return: True 若至少包含一张图片
        """
        try:
            if not hasattr(self, "rich_editor"):
                return False
            doc = self.rich_editor.document()
            block = doc.begin()
            while block.isValid():
                it = block.begin()
                while not it.atEnd():
                    fragment = it.fragment()
                    if fragment.isValid():
                        if fragment.charFormat().isImageFormat():
                            return True
                    it += 1
                block = block.next()
        except Exception as e:
            logging.debug(f"检测图片失败: {e}")
        return False

    def _switch_mode(self, mode):
        """
        切换编辑模式：
          - markdown → rich_text ：优先保留原富文本样式（若内容未变）
          - rich_text → markdown ：把富文本转换为 Markdown

        切到 Markdown 时缓存源码；切回时若源码未变，
        直接切回原富文本文档，不丢失字号 / 颜色等样式。

        v5.0.2：从富文本切到 Markdown 时，若文档含图片，弹出确认提示。
        """
        if mode == self._edit_mode:
            return

        # ========== 场景 A：从 Markdown 切回富文本 ==========
        if self._edit_mode == "markdown" and mode == "rich_text":
            current_md = self.markdown_editor.toPlainText()
            cached_md = getattr(self, "_md_cache_before_switch", None)

            # 若 Markdown 源码未被修改 → 直接切回原富文本文档（保留样式）
            if cached_md is not None and current_md == cached_md:
                self._edit_mode = mode
                self._md_cache_before_switch = None
                self._sync_mode_buttons()
                self._apply_mode_layout(mode)
                self._set_status(
                    tr("auto.beewrite_mode_mixin.c263fa57", "✨ 已切换回所见即所得（保留原样式）"), 3000
                )
                return

            # 用户改动了 Markdown 源码 → 需重建富文本（样式会重置为默认）
            # v5.0.2：确保 rich_editor._current_file_dir 已同步，
            #         否则 set_markdown 解析 ![](相对路径) 时会失败
            try:
                self._ensure_rich_editor_dir()
            except Exception as e:
                logging.debug(f"同步 rich_editor 目录失败: {e}")

            try:
                self.rich_editor.set_markdown(current_md)
            except Exception as e:
                import traceback
                traceback.print_exc()
                QMessageBox.warning(
                    self,
                    tr("auto.beewrite_mode_mixin.4f77b594", "模式切换失败"),
                    f"错误: {e}\n\n请把上方控制台的报错信息发给开发者。",
                )
                self._sync_mode_buttons()
                return

        # ========== 场景 B：从富文本切到 Markdown ==========
        elif self._edit_mode == "rich_text" and mode == "markdown":
            # ---------- v5.0.2：含图片时弹确认 ----------
            try:
                if self._document_has_images():
                    reply = QMessageBox.question(
                        self,
                        tr("auto.beewrite_mode_mixin.77db9f23", "⚠️ 文档含图片"),
                        "当前文档包含图片。\n\n"
                        "切换到 Markdown 模式后，图片会以 "
                        "![](...) 语法展示在源码中，\n"
                        "但右侧预览区无法显示图片。\n\n"
                        "若切回所见即所得模式，图片会从原路径"
                        "重新加载——请确保图片文件未被移动或删除。\n\n"
                        "是否继续切换？",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.Yes,
                    )
                    if reply != QMessageBox.Yes:
                        # 用户取消 → 还原按钮状态
                        self._sync_mode_buttons()
                        return
            except Exception as e:
                logging.error(f"图片检测失败: {e}")

            try:
                md_text = self.rich_editor.to_markdown()
                self.markdown_editor.setPlainText(md_text)
                # 缓存 Markdown 源码，用于切回时比对
                self._md_cache_before_switch = md_text
            except Exception as e:
                import traceback
                traceback.print_exc()
                QMessageBox.warning(
                    self,
                    tr("auto.beewrite_mode_mixin.4f77b594", "模式切换失败"),
                    f"错误: {e}\n\n请把上方控制台的报错信息发给开发者。",
                )
                self._sync_mode_buttons()
                return

        # ========== 更新状态 ==========
        self._edit_mode = mode
        self._sync_mode_buttons()
        self._apply_mode_layout(mode)

        if mode == "rich_text":
            self._set_status(
                tr("auto.beewrite_mode_mixin.929d1ba9", "✨ 已切换到所见即所得模式（可编辑表格）"), 3000
            )
        else:
            self._set_status(tr("auto.beewrite_mode_mixin.6dd99d4d", "已切换到 Markdown 源码模式"), 3000)

    def _ensure_rich_editor_dir(self):
        """
        v5.0.2 新增：确保 rich_editor._current_file_dir 已同步到当前文档目录。

        场景：用户先在 Markdown 模式打开文档，然后切到富文本模式时，
              set_markdown 会解析 ![](相对路径)，需要正确的基准目录。

        优先级：
          1. self._current_file_path 的父目录
          2. self.get_current_file_dir()（若存在）
          3. 保持现状（不改）
        """
        try:
            from pathlib import Path as _Path
            target_dir = None

            # 优先级 1：_current_file_path 的父目录
            if getattr(self, "_current_file_path", None):
                target_dir = str(_Path(self._current_file_path).parent)

            # 优先级 2：get_current_file_dir()
            if not target_dir and hasattr(self, "get_current_file_dir"):
                try:
                    d = self.get_current_file_dir()
                    if d:
                        target_dir = str(d)
                except Exception:
                    pass

            if target_dir and hasattr(self, "rich_editor"):
                self.rich_editor.set_current_file_dir(target_dir)
                logging.debug(
                    f"[_ensure_rich_editor_dir] 已同步 rich_editor 目录 "
                    f"为 {target_dir}"
                )
        except Exception as e:
            logging.debug(f"_ensure_rich_editor_dir 失败: {e}")

    # ==================================================================
    # 工具栏折叠
    # ==================================================================
    def _toggle_toolbars(self):
        """折叠 / 展开插入工具栏（_toolbar2）"""
        visible = self._toolbar2.isVisible()
        self._toolbar2.setVisible(not visible)
        if hasattr(self, "_collapse_btn"):
            self._collapse_btn.setText("▼ 展开" if visible else "▲ 收起")

    # ==================================================================
    # 格式状态同步
    # ==================================================================
    def _update_format_state(self):
        """光标移动时同步按钮状态（粗体 / 斜体 / 下划线 / 删除线）"""
        if self._edit_mode != "rich_text":
            return
        cf = self.rich_editor.currentCharFormat()
        self._bold_btn.setChecked(cf.fontWeight() == QFont.Bold)
        self._italic_btn.setChecked(cf.fontItalic())
        self._underline_btn.setChecked(cf.fontUnderline())
        self._strike_btn.setChecked(cf.fontStrikeOut())

    # ==================================================================
    # 字体 / 字号
    # ==================================================================
    def _on_font_family(self, f):
        """切换字体"""
        if self._edit_mode != "rich_text":
            return
        c = self.rich_editor.textCursor()
        if c.hasSelection():
            fmt = QTextCharFormat()
            fmt.setFontFamilies([f])
            c.mergeCharFormat(fmt)

    def _iter_all_tables(self, frame):
        """
        递归遍历 QTextFrame 内的所有 QTextTable。

        QTextFrame.childFrames() 返回所有子 frame（包括表格、普通 frame），
        比依赖 cursor.currentTable() 更可靠——后者只在光标位于表格内时有效。
        """
        tables = []
        try:
            children = frame.childFrames()
        except Exception:
            return tables
        for child in children:
            try:
                if isinstance(child, QTextTable):
                    tables.append(child)
                else:
                    tables.extend(self._iter_all_tables(child))
            except Exception:
                continue
        return tables

    def _on_font_size(self, s):
        """
        切换字号。

        修复目标：全选改字号时，标题、正文、表格内文字、
                 DataFrame 表格全部跟随变化。

        处理四段：
          1. mergeCharFormat 覆盖普通段落内的字符
          2. 遍历 block，对标题块（headingLevel > 0）额外应用
             setBlockCharFormat——因为 Qt 内置 Heading 样式会优先于
             普通 char format
          3. 用 QTextFrame.childFrames() 递归获取所有表格，
             对每个 cell 内的文字应用 mergeCharFormat
             ——不依赖 cursor.currentTable()，覆盖所有表格
          4. 恢复原选区（mergeCharFormat 会移动光标）
        """
        if self._edit_mode != "rich_text":
            return
        c = self.rich_editor.textCursor()
        if not c.hasSelection():
            return

        try:
            size = float(s)
        except (ValueError, TypeError):
            return

        sel_start = c.selectionStart()
        sel_end = c.selectionEnd()

        # ---------- 1. 应用字符格式（覆盖普通段落） ----------
        fmt = QTextCharFormat()
        fmt.setFontPointSize(size)
        c.mergeCharFormat(fmt)

        doc = self.rich_editor.document()

        # ---------- 2. 遍历 block，处理标题块 ----------
        block = doc.begin()
        while block.isValid():
            block_start = block.position()
            block_end = block_start + block.length()
            if block_start < sel_end and block_end > sel_start:
                bf = block.blockFormat()
                if bf.headingLevel() > 0:
                    # 标题块：同时应用 block char format
                    block_cursor = QTextCursor(block)
                    block_fmt = QTextCharFormat()
                    block_fmt.setFontPointSize(size)
                    block_cursor.setBlockCharFormat(block_fmt)
            block = block.next()

        # ---------- 3. 递归获取所有表格，处理每个 cell ----------
        try:
            all_tables = self._iter_all_tables(doc.rootFrame())
        except Exception as e:
            logging.error(f"遍历表格失败: {e}")
            all_tables = []

        for table in all_tables:
            # 判断表格是否与选区有交集
            try:
                first_pos = table.firstCursorPosition().position()
                last_pos = table.lastCursorPosition().position()
            except Exception:
                continue

            if not (first_pos < sel_end and last_pos > sel_start):
                continue

            # 遍历表格内所有 cell
            for r in range(table.rows()):
                for c_ in range(table.columns()):
                    try:
                        cell = table.cellAt(r, c_)
                        cell_cursor = cell.firstCursorPosition()
                        cell_cursor.movePosition(
                            QTextCursor.EndOfBlock,
                            QTextCursor.KeepAnchor
                        )
                        cell_fmt = QTextCharFormat()
                        cell_fmt.setFontPointSize(size)
                        cell_cursor.mergeCharFormat(cell_fmt)
                    except Exception:
                        continue

        # ---------- 4. 恢复原选区 ----------
        try:
            new_c = self.rich_editor.textCursor()
            new_c.setPosition(sel_start)
            new_c.setPosition(sel_end, QTextCursor.KeepAnchor)
            self.rich_editor.setTextCursor(new_c)
        except Exception:
            pass

    # ==================================================================
    # 粗体 / 斜体 / 下划线 / 删除线
    # ==================================================================
    def _toggle_bold(self):
        """切换粗体"""
        if self._edit_mode != "rich_text":
            return
        c = self.rich_editor.textCursor()
        f = QTextCharFormat()
        f.setFontWeight(
            QFont.Bold
            if c.charFormat().fontWeight() != QFont.Bold
            else QFont.Normal
        )
        c.mergeCharFormat(f)
        self._update_format_state()

    def _toggle_italic(self):
        """切换斜体"""
        if self._edit_mode != "rich_text":
            return
        c = self.rich_editor.textCursor()
        f = QTextCharFormat()
        f.setFontItalic(not c.charFormat().fontItalic())
        c.mergeCharFormat(f)
        self._update_format_state()

    def _toggle_underline(self):
        """切换下划线"""
        if self._edit_mode != "rich_text":
            return
        c = self.rich_editor.textCursor()
        f = QTextCharFormat()
        f.setFontUnderline(not c.charFormat().fontUnderline())
        c.mergeCharFormat(f)
        self._update_format_state()

    def _toggle_strikethrough(self):
        """切换删除线"""
        if self._edit_mode != "rich_text":
            return
        c = self.rich_editor.textCursor()
        f = QTextCharFormat()
        f.setFontStrikeOut(not c.charFormat().fontStrikeOut())
        c.mergeCharFormat(f)
        self._update_format_state()

    # ==================================================================
    # 文字色 / 高亮
    # ==================================================================
    def _set_text_color(self):
        """设置选中文字颜色"""
        if self._edit_mode != "rich_text":
            return
        col = QColorDialog.getColor()
        if col.isValid():
            c = self.rich_editor.textCursor()
            f = QTextCharFormat()
            f.setForeground(col)
            c.mergeCharFormat(f)

    def _set_bg_color(self):
        """设置选中文字高亮色"""
        if self._edit_mode != "rich_text":
            return
        col = QColorDialog.getColor()
        if col.isValid():
            c = self.rich_editor.textCursor()
            f = QTextCharFormat()
            f.setBackground(col)
            c.mergeCharFormat(f)

    # ==================================================================
    # 对齐
    # ==================================================================
    def _align_left(self):
        """左对齐"""
        if self._edit_mode != "rich_text":
            return
        c = self.rich_editor.textCursor()
        bf = c.blockFormat()
        bf.setAlignment(Qt.AlignLeft)
        c.setBlockFormat(bf)

    def _align_center(self):
        """居中对齐"""
        if self._edit_mode != "rich_text":
            return
        c = self.rich_editor.textCursor()
        bf = c.blockFormat()
        bf.setAlignment(Qt.AlignCenter)
        c.setBlockFormat(bf)

    def _align_right(self):
        """右对齐"""
        if self._edit_mode != "rich_text":
            return
        c = self.rich_editor.textCursor()
        bf = c.blockFormat()
        bf.setAlignment(Qt.AlignRight)
        c.setBlockFormat(bf)

    # ==================================================================
    # 样式 / 列表
    # ==================================================================
    def _on_heading(self, style):
        """切换标题级别"""
        if self._edit_mode != "rich_text":
            return
        c = self.rich_editor.textCursor()
        bf = c.blockFormat()
        bf.setHeadingLevel({
            "正文": 0,
            "标题 1": 1,
            "标题 2": 2,
            "标题 3": 3,
            "标题 4": 4,
        }.get(style, 0))
        c.setBlockFormat(bf)

    def _insert_list(self):
        """插入无序列表"""
        if self._edit_mode != "rich_text":
            return
        self.rich_editor._insert_list_item("", False)

    def _insert_ordered_list(self):
        """插入有序列表"""
        if self._edit_mode != "rich_text":
            return
        self.rich_editor._insert_list_item("", True)

    # ==================================================================
    # 格式刷
    # ==================================================================
    def _toggle_format_painter(self, checked):
        """切换格式刷状态"""
        if self._edit_mode != "rich_text":
            return
        if checked:
            cursor = self.rich_editor.textCursor()
            if cursor.hasSelection():
                FORMAT_PAINTER.copy_from_cursor(cursor)
                self._set_status(
                    tr("auto.beewrite_mode_mixin.ed568dd8", "🖌️ 格式已复制！选中其他文字自动应用"), 5000
                )
            else:
                self._fmt_btn.setChecked(False)
                self._set_status(tr("auto.beewrite_mode_mixin.7dde5bf4", "请先选中要复制格式的文字"), 2000)
        else:
            FORMAT_PAINTER.clear()

    def _on_format_painter_applied(self):
        """格式刷应用完成时的回调（由 RichTextEditor 通知）"""
        self._fmt_btn.setChecked(False)
        FORMAT_PAINTER.clear()
        self._set_status(tr("auto.beewrite_mode_mixin.537fe393", "✅ 格式已应用！"), 3000)