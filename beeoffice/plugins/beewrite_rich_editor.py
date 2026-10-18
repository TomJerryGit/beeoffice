# beeoffice/plugins/beewrite_rich_editor.py
"""
蜜写富文本编辑器（RichTextEditor）

职责：
  - 继承 QTextEdit，支持表格 / 图片 / 富文本编辑
  - Markdown ↔ 富文本双向转换（to_markdown / set_markdown）
  - Tab / Backtab 在表格内跳转，最后一格自动新增一行
  - 粘贴处理：图片保存到 media/，TSV/CSV 自动转表格
  - 表格插入 / 行列操作 / 合并拆分 / 单元格颜色
  - 表格右键菜单
  - 格式刷应用（鼠标松开时自动应用）
  - 光标位置通知父窗口（状态栏显示表格行列）

依赖：
  - beewrite_utils.FORMAT_PAINTER （格式刷全局状态）

v5.0.1 历史修复：
  - 所有 _insert_* 方法开头 movePosition(End)，保证"追加到文档末尾"
    避免 cursor 位置引发的 block 顺序错乱
  - _insert_md_table 检查当前 block 是否为空，空则复用（避免多出空行）
  - _insert_heading 末尾不再插入额外空 block
  - _insert_code_block / _insert_quote 末尾不再插入额外空 block
  - to_markdown() 长文本标题自动降级为正文（不加粗体）
  - to_markdown() 去掉文首/文末连续空行
  - to_markdown() 用段落首字符格式判断粗斜
  - _table_to_md() 过滤全空列 + 数字列右对齐
  - _insert_heading() 空文档时复用首个 block
  - _insert_formatted_paragraph() 使用 setBlockCharFormat
  - _insert_md_table() 表格加白底 + 表头淡橙底纹
  - _insert_table_from_rows() / insert_dataframe_table() /
    _insert_table() 表头加淡橙底纹
  - set_markdown() 遇到空标题行当作空行处理

v5.0.2 图片全量修复：
  - to_markdown() 新增图片 fragment 支持：
      富文本 → Markdown 时，图片转为 ![](path) 语法
      图文混排的 block 按 fragment 顺序拼接
      图片所在 block 的 block.text() 为空，所以图片检测必须在
      "空段落" 判断之前，否则会被当空行丢弃
  - set_markdown() 新增图片语法解析：
      遇到 ![](path) 时，按路径加载并插入到富文本
      相对路径相对于 _current_file_dir 解析
      图片不存在时插入占位文字 [图片缺失: path]，避免静默丢失
  - 新增 3 个辅助方法：
      _block_has_image          检查 block 是否含图片 fragment
      _block_with_images_to_md  图片混排 block → Markdown
      _insert_image_by_path     按路径加载并插入图片

v5.0.2 增强：
  - _insert_image_by_path 支持多基准目录兜底解析：
      1. 从 parent 链找 BeeWriteEditor._current_file_path 的父目录
      2. self._current_file_dir（默认）
      3. 用户主目录（最后兜底）
  - 图片找不到时记录所有尝试过的路径到日志

v5.0.4 优化（本次）：
  - _IMAGE_MAX_WIDTH 从 600 提升到 720：
      使图片宽度接近 A4 页面可用宽度（约 7.5 英寸），
      长条图片（如诗词截图 1544×152）缩放后高度更合理，
      可读性更好（高度从 59px 提升到 71px）
  - _insert_image_by_path 插入图片时同步设置段落居中：
      图片所在 block 设置 alignment=center + 段前后 margin=16px，
      使 Qt 编辑器里的图片与导出 DOCX 的居中效果一致
  - insertFromMimeData（粘贴图片）也应用 _IMAGE_MAX_WIDTH 缩放
      避免粘贴大图后显示过宽

设计说明：
  - 本模块不导入其他 beewrite_* Mixin，避免循环依赖
"""
import re
import time
import logging
from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import (
    QTextEdit,
    QColorDialog,
    QDialog,
    QFormLayout,
    QSpinBox,
    QCheckBox,
    QDialogButtonBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QFont,
    QTextCursor,
    QTextCharFormat,
    QTextBlockFormat,
    QTextListFormat,
    QColor,
    QTextTableFormat,
    QTextImageFormat,
    QImage,
)

from beeoffice.plugins.beewrite_utils import FORMAT_PAINTER
from beeoffice.i18n import tr


# 默认正文字体色（避免继承标题的橙色）
_DEFAULT_TEXT_COLOR = "#333333"
_DEFAULT_FONT_SIZE = 14

# 表头底纹色（淡橙）
_TABLE_HEADER_BG = "#FFF3E0"
# 表格背景色（白）
_TABLE_BG = "#FFFFFF"

# 标题文本长度阈值：超过此长度且以句末标点结尾，视为正文而非标题
_HEADING_TEXT_MAX_LEN = 40
# 句末标点集合
_SENTENCE_ENDINGS = "。！？.!?"

# 图片宽度限制：超过此宽度按比例缩小
# v5.0.4：从 600 提升到 720，使图片宽度接近 A4 页面可用宽度，
#         避免长条图片被过度压缩成"小灰字"
_IMAGE_MAX_WIDTH = 720


# ==================== 富文本编辑器 ====================
class RichTextEditor(QTextEdit):
    """蜜写富文本编辑器：所见即所得 + 表格 + 图片 + 格式刷"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(True)
        self._current_file_dir = str(Path.home())
        self.setStyleSheet("""
            QTextEdit {
                border: none; padding: 20px 40px;
                background-color: #FFFFFF;
                font-family: "Segoe UI", "微软雅黑", sans-serif;
                font-size: 14px; line-height: 1.8;
            }
        """)
        # 光标移动时通知父窗口
        self.cursorPositionChanged.connect(self._notify_cursor_position)

    def set_current_file_dir(self, d):
        """设置当前文件目录（用于粘贴图片时保存到 media/）"""
        self._current_file_dir = d

    # ==================== 工具方法 ====================
    def _is_empty_doc(self) -> bool:
        """
        判断当前文档是否为空（仅有一个空 block）。
        用于 set_markdown 时决定是否复用首个 block。
        """
        doc = self.document()
        first = doc.begin()
        if not first.isValid():
            return True
        if first.next().isValid():
            return False
        if first.text():
            return False
        return True

    def _cursor_at_end(self) -> QTextCursor:
        """
        返回位于文档末尾的 cursor。
        所有插入操作使用它，确保新内容"追加到文档末尾"，
        避免 cursor 位置引发 block 顺序错乱。
        """
        c = self.textCursor()
        c.movePosition(QTextCursor.End)
        return c

    def _current_block_is_empty(self, c: QTextCursor) -> bool:
        """判断 cursor 所在 block 是否为空 block"""
        return not c.block().text().strip()

    # ==================== 光标位置通知 ====================
    def _notify_cursor_position(self):
        """通知父窗口当前光标位置（若在表格中显示行列）"""
        cursor = self.textCursor()
        table = cursor.currentTable()
        msg = ""
        if table:
            cell = table.cellAt(cursor)
            if cell.isValid():
                msg = (
                    f"📊 表格：第 {cell.row() + 1} 行，"
                    f"第 {cell.column() + 1} 列"
                )
        p = self.parent()
        while p:
            if hasattr(p, 'set_global_status'):
                p.set_global_status(msg, 0)
                return
            p = p.parent()

    # ==================== Tab 键跳转 ====================
    def keyPressEvent(self, event):
        """Tab 在表格内跳转，最后一格自动新增一行"""
        if event.key() == Qt.Key_Tab:
            cursor = self.textCursor()
            table = cursor.currentTable()
            if table:
                cell = table.cellAt(cursor)
                if cell.isValid():
                    row = cell.row()
                    col = cell.column()
                    total_rows = table.rows()
                    total_cols = table.columns()

                    if row == total_rows - 1 and col == total_cols - 1:
                        table.appendRows(1)
                        next_cell = table.cellAt(total_rows, 0)
                    elif col + 1 < total_cols:
                        next_cell = table.cellAt(row, col + 1)
                    else:
                        next_cell = table.cellAt(row + 1, 0)

                    self.setTextCursor(next_cell.firstCursorPosition())
                    return

        if event.key() == Qt.Key_Backtab:
            cursor = self.textCursor()
            table = cursor.currentTable()
            if table:
                cell = table.cellAt(cursor)
                if cell.isValid():
                    row = cell.row()
                    col = cell.column()
                    if col > 0:
                        prev_cell = table.cellAt(row, col - 1)
                    elif row > 0:
                        prev_cell = table.cellAt(
                            row - 1, table.columns() - 1
                        )
                    else:
                        return
                    self.setTextCursor(prev_cell.firstCursorPosition())
                    return

        super().keyPressEvent(event)

    # ==================== 格式刷 ====================
    def mouseReleaseEvent(self, event):
        """鼠标松开时，若格式刷已激活且有选区，则应用格式"""
        super().mouseReleaseEvent(event)
        if FORMAT_PAINTER.active and FORMAT_PAINTER.char_format:
            cursor = self.textCursor()
            if cursor.hasSelection():
                if FORMAT_PAINTER.apply_to_cursor(cursor):
                    self.setTextCursor(cursor)
                    FORMAT_PAINTER.clear()
                    self._notify_painter_done()

    def _notify_painter_done(self):
        """通知父窗口格式刷已应用"""
        p = self.parent()
        while p:
            if hasattr(p, '_on_format_painter_applied'):
                p._on_format_painter_applied()
                return
            p = p.parent()

    # ==================== 图片辅助（v5.0.2 新增） ====================
    def _block_has_image(self, block):
        """
        v5.0.2 新增：判断 block 内是否包含图片 fragment。

        用途：to_markdown 时区分普通段落和含图片段落。
        图片所在 block 的 block.text() 为空，必须在"空段落"判断之前
        先检测图片，否则会被当空行丢弃。

        :param block: QTextBlock 对象
        :return: True 若至少包含一张图片 fragment
        """
        try:
            it = block.begin()
            while not it.atEnd():
                fragment = it.fragment()
                if fragment.isValid():
                    fmt = fragment.charFormat()
                    if fmt.isImageFormat():
                        return True
                it += 1
        except Exception:
            pass
        return False

    def _block_with_images_to_md(self, block):
        """
        v5.0.2 新增：将含图片的 block 转为 Markdown 文本。

        按 fragment 顺序遍历：
          - 图片 fragment → ![](path)
          - 文本 fragment → 保留加粗 / 斜体标记

        支持的混排场景：
          - 纯图片段落：![img](path)
          - 图文混排：前缀文本![img](path)后缀文本
          - 多图段落：![img1](path1)![img2](path2)

        :param block: QTextBlock 对象
        :return: Markdown 字符串
        """
        parts = []
        try:
            it = block.begin()
            while not it.atEnd():
                fragment = it.fragment()
                if fragment.isValid():
                    fmt = fragment.charFormat()
                    if fmt.isImageFormat():
                        img_fmt = fmt.toImageFormat()
                        name = img_fmt.name()
                        if name:
                            # 统一用 POSIX 风格路径
                            md_path = str(name).replace("\\", "/")
                            parts.append(f"![]({md_path})")
                    else:
                        txt = fragment.text()
                        if txt:
                            if fmt.fontWeight() == QFont.Bold:
                                txt = f"**{txt}**"
                            if fmt.fontItalic():
                                txt = f"*{txt}*"
                            parts.append(txt)
                it += 1
        except Exception as e:
            logging.debug(f"块内图片转换失败: {e}")
        return "".join(parts)

    def _insert_image_by_path(self, img_path):
        """
        v5.0.2 增强：按路径插入图片到文档末尾。

        多基准目录兜底解析相对路径（按优先级）：
          1. 从 parent 链找 BeeWriteEditor._current_file_path 的父目录
             （绕过 _current_file_dir 未及时同步的问题）
          2. self._current_file_dir（默认）
          3. 用户主目录（最后兜底）

        v5.0.4：图片插入后，所在段落自动居中（alignment=center），
                使 Qt 编辑器和导出 DOCX 的居中效果一致。

        处理：
          - 绝对路径：直接使用
          - 相对路径：依次尝试上述基准目录
          - 路径存在：QTextImageFormat 插入
          - 宽度限制：超过 _IMAGE_MAX_WIDTH 按比例缩放
          - 路径不存在：插入占位文字 [图片缺失: path]
                        并在日志里记录所有尝试过的路径

        :param img_path: 图片路径（绝对或相对）
        """
        path = Path(img_path)
        tried_paths = []

        if not path.is_absolute():
            # 收集候选基准目录
            candidates = []

            # 候选 1：从 parent 链找 BeeWriteEditor._current_file_path
            # （优先级最高，因为它是"当前正确"的目录）
            try:
                p = self.parent()
                while p:
                    cur_path = getattr(p, "_current_file_path", None)
                    if cur_path:
                        candidates.append(str(Path(cur_path).parent))
                        break
                    p = p.parent()
            except Exception as e:
                logging.debug(f"从 parent 链查找 _current_file_path 失败: {e}")

            # 候选 2：self._current_file_dir（默认）
            if self._current_file_dir:
                candidates.append(self._current_file_dir)

            # 候选 3：用户主目录（最后兜底）
            candidates.append(str(Path.home()))

            # 去重（保持顺序）
            seen = set()
            unique_candidates = []
            for c in candidates:
                if c and c not in seen:
                    seen.add(c)
                    unique_candidates.append(c)

            # 依次尝试
            for base in unique_candidates:
                try:
                    candidate = Path(base) / img_path
                except Exception:
                    continue
                tried_paths.append(str(candidate))
                if candidate.exists():
                    path = candidate
                    logging.debug(
                        f"图片相对路径解析成功: {img_path} → {candidate}"
                    )
                    break

        if not path.exists():
            logging.warning(
                f"图片文件不存在: {img_path}\n"
                f"尝试过的路径:\n  "
                + "\n  ".join(tried_paths if tried_paths else [str(path)])
            )
            c = self._cursor_at_end()
            if not self._current_block_is_empty(c):
                c.insertBlock()
            placeholder_fmt = QTextCharFormat()
            placeholder_fmt.setForeground(QColor("#B71C1C"))
            c.insertText(f"[图片缺失: {img_path}]", placeholder_fmt)
            c.insertBlock()
            return

        try:
            img = QImage(str(path))
            if img.isNull():
                logging.warning(tr("auto.beewrite_rich_editor.821376a8", "图片加载失败: {path}").format(path=path))
                return

            c = self._cursor_at_end()
            if not self._current_block_is_empty(c):
                c.insertBlock()

            fmt = QTextImageFormat()
            fmt.setName(str(path))

            if img.width() > _IMAGE_MAX_WIDTH:
                ratio = _IMAGE_MAX_WIDTH / img.width()
                fmt.setWidth(int(img.width() * ratio))
                fmt.setHeight(int(img.height() * ratio))
            else:
                fmt.setWidth(img.width())
                fmt.setHeight(img.height())

            c.insertImage(fmt)

            # ---------- v5.0.4：图片所在段落居中 ----------
            try:
                bf = c.blockFormat()
                bf.setAlignment(Qt.AlignCenter)
                # 段前段后间距（Qt 内部使用像素，按 96 DPI 换算约 16px ≈ 12pt）
                bf.setTopMargin(16)
                bf.setBottomMargin(16)
                c.setBlockFormat(bf)
            except Exception as e:
                logging.debug(f"设置图片段落格式失败: {e}")

            c.insertBlock()
        except Exception as e:
            logging.error(f"插入图片失败 {img_path}: {e}")

    # ==================== Markdown 转换：富文本 → Markdown ====================
    def to_markdown(self) -> str:
        """
        将富文本内容转换为 Markdown 文本。

        关键规则：
          1. 空段落 → 输出空行
          2. 图片 fragment（v5.0.2 新增）→ ![](path)
             - 优先于"空段落"判断，因为图片所在 block.text() 为空
          3. 标题（headingLevel > 0）：
             - 若文本长度 <= 40 且不以句末标点结尾 → 视为真标题
             - 否则视为误设为标题的正文段落 → 按正文输出
          4. 引用、列表、粗体/斜体保留
          5. 判断粗体/斜体时用段落**第一个字符**的格式
          6. 去掉文首/文末连续空行
        """
        md = []
        doc = self.document()
        block = doc.begin()
        processed_tables = set()
        while block.isValid():
            cursor = QTextCursor(block)
            table = cursor.currentTable()
            if table and id(table) not in processed_tables:
                processed_tables.add(id(table))
                md.append(self._table_to_md(table))
                last_cell = table.cellAt(
                    table.rows() - 1, table.columns() - 1
                )
                lc = last_cell.lastCursorPosition()
                lc.movePosition(QTextCursor.EndOfBlock)
                block = lc.block().next()
                continue
            if table:
                block = block.next()
                continue

            # ---------- v5.0.2：优先处理含图片的 block ----------
            if self._block_has_image(block):
                img_md = self._block_with_images_to_md(block)
                if img_md:
                    md.append(img_md)
                block = block.next()
                continue

            text = block.text()
            bf = block.blockFormat()
            hl = bf.headingLevel()

            # 取第一个字符的字符格式（更准确）
            cf = self._get_block_first_char_format(block)

            # 空段落
            if not text.strip():
                md.append("")
                block = block.next()
                continue

            # 标题（关键修复：长文本自动降级为正文）
            if hl > 0:
                is_likely_body = (
                    len(text) > _HEADING_TEXT_MAX_LEN
                    and text[-1] in _SENTENCE_ENDINGS
                )
                if is_likely_body:
                    md.append(text)
                else:
                    md.append("#" * min(hl, 6) + " " + text)
                block = block.next()
                continue

            # 引用
            # 修复：重建引用时用的是 setLeftMargin(20)，回写却判断 >30，
            # 于是引用永远识别不回来；同时正文带 "▎ " 前缀，需要剥掉。
            if bf.leftMargin() >= 10:
                quote_text = self._inline_to_md(
                    block, strip_lead="▎", keep_italic=False
                )
                md.append("> " + quote_text)
                block = block.next()
                continue

            # 列表
            tl = block.textList()
            if tl:
                indent = "    " * tl.format().indent()
                marker = (
                    "-"
                    if tl.format().style() != QTextListFormat.ListDecimal
                    else "1."
                )
                md.append(f"{indent}{marker} {self._inline_to_md(block)}")
                block = block.next()
                continue

            # 普通段落：按 fragment 序列化，保留粗体/斜体/删除线/行内代码/链接
            md.append(self._inline_to_md(block))
            block = block.next()

        # 去掉文首连续空行
        while md and md[0] == "":
            md.pop(0)
        # 去掉文末连续空行
        while md and md[-1] == "":
            md.pop()
        return "\n".join(md)

    @staticmethod
    def _get_block_first_char_format(block) -> QTextCharFormat:
        """获取段落第一个字符的字符格式"""
        text = block.text()
        if not text:
            return block.charFormat()
        doc = block.document()
        cursor = QTextCursor(doc)
        cursor.setPosition(block.position())
        cursor.movePosition(
            QTextCursor.Right, QTextCursor.KeepAnchor, 1
        )
        return cursor.charFormat()

    def _block_with_links_to_md(self, block):
        """
        若段落含超链接，按 fragment 拼成 `[文本](URL)`；否则返回 None。

        修复：md→富文本时只给链接文字染色、不保存 URL，回写时无 `[]()`，
        任何超链接都会在模式切换中永久丢失。
        """
        try:
            it = block.begin()
            parts = []
            has_link = False
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    t = frag.text()
                    href = frag.charFormat().anchorHref()
                    if href:
                        has_link = True
                        parts.append(f"[{t}]({href})")
                    else:
                        parts.append(t)
                it += 1
        except Exception as e:
            logging.error(f"解析段落超链接失败: {e}")
            return None
        return "".join(parts) if has_link else None

    # ==================================================================
    # 行内格式序列化
    # ==================================================================
    def _inline_to_md(self, block, strip_lead: str = "",
                      keep_italic: bool = True) -> str:
        """
        按 fragment 序列化段落内的行内格式。

        修复：原实现用 `block.text()` 整体加 `**`，且只看**第一个字符**的格式，
        所以「正文里有 **粗体**、*斜体* 和 `code`」这种混合行内格式
        在切回 Markdown 时会被整段抹平——只有整段同格式才勉强保留。
        引用块和列表更是完全按纯文本输出。

        :param strip_lead: 需要在序列化**之前**剥掉的视觉前缀（引用块的 "▎"）。
            必须在包标记之前剥，否则会变成 `**▎ 引用**`，前缀卡在标记里面。
        :param keep_italic: 是否把斜体写成 `*`。
            引用块整体是斜体样式，那是**视觉样式**不是用户强调，
            写回 `*` 会让引用在第一次往返就被改写；此时传 False。
        """
        try:
            it = block.begin()
            parts = []
            first = True
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    text = frag.text()
                    if first and strip_lead:
                        if text.startswith(strip_lead + " "):
                            text = text[len(strip_lead) + 1:]
                        elif text.startswith(strip_lead):
                            text = text[len(strip_lead):]
                    first = False
                    if text:
                        parts.append(
                            self._wrap_inline(
                                text, frag.charFormat(),
                                keep_italic=keep_italic,
                            )
                        )
                it += 1
            return "".join(parts) if parts else block.text()
        except Exception as e:
            logging.error(f"序列化行内格式失败: {e}")
            return block.text()

    @staticmethod
    def _wrap_inline(text: str, cf, keep_italic: bool = True) -> str:
        """给单个 fragment 的文本套上对应的 Markdown 标记。"""
        # 纯空白不要包标记，否则会产出 `** **` 这种坏掉的语法
        if not text.strip():
            return text

        href = ""
        bold = italic = strike = False
        is_code = False
        try:
            href = cf.anchorHref() or ""
            bold = cf.fontWeight() >= QFont.Bold
            italic = cf.fontItalic() if keep_italic else False
            strike = cf.fontStrikeOut()
            families = cf.fontFamilies() or []
            if not isinstance(families, (list, tuple)):
                families = [str(families)]
            is_code = any(
                ("Consolas" in str(f)) or ("Mono" in str(f))
                or ("Courier" in str(f))
                for f in families
            )
        except Exception:
            pass

        out = text
        if is_code:
            # 行内代码内部不再叠加其它标记，否则反引号里出现 ** 更难读
            out = f"`{out}`"
        else:
            if strike:
                out = f"~~{out}~~"
            if bold and italic:
                out = f"***{out}***"
            elif bold:
                out = f"**{out}**"
            elif italic:
                out = f"*{out}*"
        if href:
            out = f"[{out}]({href})"
        return out

    @staticmethod
    def _split_md_row(line):
        """
        把 Markdown 表格行拆成单元格（**保留空单元格**）。

        修复：原实现 `split('|')` 后用 `if c.strip()` 过滤，
        会把 `| a |  | c |` 的中间空列吞掉，导致数据整体左移。
        """
        s = line.strip()
        if s.startswith('|'):
            s = s[1:]
        if s.endswith('|'):
            s = s[:-1]
        return [c.strip() for c in s.split('|')]

    def _table_to_md(self, table) -> str:
        """将 QTextTable 转为 Markdown 表格文本"""
        rows, cols = table.rows(), table.columns()

        grid = []
        for r in range(rows):
            row_cells = []
            for c in range(cols):
                cell = table.cellAt(r, c)
                text = cell.firstCursorPosition().block().text().strip()
                row_cells.append(text)
            grid.append(row_cells)

        if not grid:
            return ""

        # 修复：不再丢弃"整列为空"的列——那会让表格在往返中悄悄少一列。
        # 列对齐由 _split_md_row 保证（解析时已保留空单元格）。
        keep_cols = list(range(cols))

        lines = []
        for r in range(rows):
            cells = [grid[r][c] for c in keep_cols]
            lines.append("| " + " | ".join(cells) + " |")

            if r == 0:
                seps = []
                for c in keep_cols:
                    is_numeric = False
                    for rr in range(1, rows):
                        val = grid[rr][c]
                        if not val:
                            continue
                        try:
                            float(val)
                            is_numeric = True
                        except (ValueError, TypeError):
                            is_numeric = False
                            break
                    if is_numeric:
                        seps.append("---:")
                    else:
                        seps.append("---")
                lines.append("|" + "|".join(seps) + "|")

        return "\n".join(lines) + "\n"

    # ==================== Markdown 转换：Markdown → 富文本 ====================
    def set_markdown(self, md_text: str):
        """
        将 Markdown 文本渲染为富文本（空标题行当作空行）

        v5.0.2：支持 ![](path) 图片语法
          - 匹配 ![alt](path) 或 ![alt](path "title")
          - 按路径加载并插入图片
          - 图片不存在时插入占位文字
        """
        self.clear()
        lines = md_text.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith('<!--'):
                i += 1
                continue
            if not line.strip():
                self._insert_block()
                i += 1
                continue
            if line.startswith('```'):
                cl = []
                i += 1
                while i < len(lines) and not lines[i].startswith('```'):
                    cl.append(lines[i])
                    i += 1
                i += 1
                if cl:
                    self._insert_code_block('\n'.join(cl))
                continue

            # ---------- v5.0.2：图片语法 ----------
            img_m = re.match(
                r'^\s*!\[([^\]]*)\]\(\s*([^)\s]+)(?:\s+"[^"]*")?\s*\)\s*$',
                line
            )
            if img_m:
                self._insert_image_by_path(img_m.group(2).strip())
                i += 1
                continue

            if line.startswith('#'):
                title_text = line.lstrip('#').strip()
                if title_text:
                    self._insert_heading(
                        title_text,
                        min(len(line) - len(line.lstrip('#')), 6)
                    )
                else:
                    self._insert_block()
                i += 1
                continue
            if line.startswith('> '):
                self._insert_quote(line[2:])
                i += 1
                continue
            if line.strip().startswith('|') and '|' in line[1:]:
                tl = [line]
                while (
                    i + 1 < len(lines)
                    and lines[i + 1].strip().startswith('|')
                ):
                    i += 1
                    tl.append(lines[i])
                self._insert_md_table(tl)
                i += 1
                continue
            lm = re.match(r'^(\s*)([-*+]|\d+\.)\s+(.*)', line)
            if lm:
                self._insert_list_item(
                    lm.group(3),
                    lm.group(2).rstrip('.').isdigit()
                )
                i += 1
                continue
            self._insert_formatted_paragraph(line)
            i += 1
        self.moveCursor(QTextCursor.Start)

    def _insert_md_table(self, lines):
        """将 Markdown 表格行渲染为 QTextTable（白底 + 表头淡橙底纹）"""
        if len(lines) < 2:
            return
        hc = self._split_md_row(lines[0])
        if not hc:
            return
        ds = 2 if re.match(r'^[\|\s\-:]+$', lines[1]) else 1
        dl = lines[ds:]
        rows, cols = len(dl) + 1, len(hc)
        c = self._cursor_at_end()

        if self._current_block_is_empty(c):
            pass
        else:
            c.insertBlock()

        tf = QTextTableFormat()
        tf.setBorder(1)
        tf.setCellPadding(6)
        tf.setCellSpacing(0)
        tf.setBorderStyle(QTextTableFormat.BorderStyle_Solid)
        tf.setHeaderRowCount(1)
        tf.setBackground(QColor(_TABLE_BG))
        table = c.insertTable(rows, cols, tf)
        for ci, h in enumerate(hc):
            cc = table.cellAt(0, ci).firstCursorPosition()
            cc.insertText(h)
            cc.select(QTextCursor.BlockUnderCursor)
            fmt = QTextCharFormat()
            fmt.setFontWeight(QFont.Bold)
            fmt.setBackground(QColor(_TABLE_HEADER_BG))
            fmt.setForeground(QColor(_DEFAULT_TEXT_COLOR))
            cc.mergeCharFormat(fmt)
        for ri, line in enumerate(dl):
            cells = self._split_md_row(line)
            for ci, cv in enumerate(cells):
                if ci < cols:
                    table.cellAt(ri + 1, ci).firstCursorPosition().insertText(cv)

    def _insert_block(self):
        """插入一个空段落（显式重置字符格式）"""
        c = self._cursor_at_end()
        bf = QTextBlockFormat()
        if self._is_empty_doc():
            c.setBlockFormat(bf)
        else:
            c.insertBlock(bf)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(_DEFAULT_TEXT_COLOR))
        fmt.setFontWeight(QFont.Normal)
        fmt.setFontPointSize(_DEFAULT_FONT_SIZE)
        c.setBlockCharFormat(fmt)

    def _insert_heading(self, text, level):
        """插入标题（cursor 定位到文档末尾，末尾不再插入额外空 block）"""
        c = self._cursor_at_end()
        f = QTextCharFormat()
        sz = {1: 24, 2: 20, 3: 17, 4: 15, 5: 13, 6: 11}
        f.setFontPointSize(sz.get(level, 14))
        f.setFontWeight(QFont.Bold)
        f.setForeground(QColor("#FF8F00"))
        bf = QTextBlockFormat()
        bf.setHeadingLevel(level)
        if self._is_empty_doc():
            c.setBlockFormat(bf)
        else:
            c.insertBlock(bf)
        c.insertText(text, f)

    def _insert_code_block(self, code):
        """插入代码块"""
        c = self._cursor_at_end()
        f = QTextCharFormat()
        f.setFontFamilies(["Consolas"])
        f.setFontPointSize(11)
        f.setBackground(QColor("#F5F5F5"))
        f.setForeground(QColor("#333"))
        if self._is_empty_doc():
            pass
        else:
            c.insertBlock()
        c.insertText(code, f)

    def _insert_quote(self, text):
        """插入引用"""
        c = self._cursor_at_end()
        f = QTextCharFormat()
        f.setFontItalic(True)
        f.setForeground(QColor("#888"))
        bf = QTextBlockFormat()
        bf.setLeftMargin(20)
        if self._is_empty_doc():
            c.setBlockFormat(bf)
        else:
            c.insertBlock(bf)
        c.insertText("▎ " + text, f)

    def _insert_list_item(self, text, ordered=False):
        """插入列表项"""
        c = self._cursor_at_end()
        lf = QTextListFormat()
        lf.setStyle(
            QTextListFormat.ListDecimal if ordered
            else QTextListFormat.ListDisc
        )
        if self._is_empty_doc():
            pass
        else:
            c.insertBlock()
        c.createList(lf)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(_DEFAULT_TEXT_COLOR))
        fmt.setFontWeight(QFont.Normal)
        c.setCharFormat(fmt)
        c.insertText(text)

    def _insert_formatted_paragraph(self, text):
        """插入普通段落（使用 setBlockCharFormat，避免格式泄漏）"""
        c = self._cursor_at_end()
        bf = QTextBlockFormat()
        bf.setHeadingLevel(0)
        if self._is_empty_doc():
            c.setBlockFormat(bf)
        else:
            c.insertBlock(bf)
        default_fmt = QTextCharFormat()
        default_fmt.setForeground(QColor(_DEFAULT_TEXT_COLOR))
        default_fmt.setFontWeight(QFont.Normal)
        default_fmt.setFontPointSize(_DEFAULT_FONT_SIZE)
        c.setBlockCharFormat(default_fmt)

        for seg in re.split(
            r'(\*\*.*?\*\*|\*[^*\n]+\*|`[^`\n]+`|\[.*?\]\(.*?\))',
            text
        ):
            if not seg:
                continue
            f = QTextCharFormat()
            f.setForeground(QColor(_DEFAULT_TEXT_COLOR))
            f.setFontWeight(QFont.Normal)
            f.setFontPointSize(_DEFAULT_FONT_SIZE)
            content = seg
            if seg.startswith('**') and seg.endswith('**'):
                content = seg[2:-2]
                f.setFontWeight(QFont.Bold)
            elif seg.startswith('*') and seg.endswith('*'):
                content = seg[1:-1]
                f.setFontItalic(True)
            elif seg.startswith('`') and seg.endswith('`'):
                content = seg[1:-1]
                f.setFontFamilies(["Consolas"])
                f.setBackground(QColor("#F5F5F5"))
                f.setForeground(QColor("#D32F2F"))
            elif re.match(r'\[.*?\]\(.*?\)', seg):
                m = re.match(r'\[(.*?)\]\((.*?)\)', seg)
                if m:
                    content = m.group(1)
                    # 修复：把 URL 真正存进字符格式的锚点，
                    # 否则回写时无从恢复，超链接在模式切换后会永久丢失。
                    f.setAnchor(True)
                    f.setAnchorHref(m.group(2))
                    f.setForeground(QColor("#1565C0"))
                    f.setFontUnderline(True)
            c.insertText(content, f)

    # ==================== 粘贴处理 ====================
    def insertFromMimeData(self, source):
        """粘贴数据：图片 / 表格数据 / 普通文本"""
        if source.hasImage():
            img = source.imageData()
            if img:
                try:
                    save_dir = Path(self._current_file_dir) / "media"
                    save_dir.mkdir(parents=True, exist_ok=True)
                    fp = save_dir / f"image_{int(time.time()*1000)}.png"
                    img.save(str(fp))
                    self.textCursor().insertImage(img, str(fp))
                    return
                except Exception as e:
                    logging.error(f"粘贴图片失败: {e}")

        if source.hasText():
            text = source.text()
            if self._looks_like_tsv_table(text):
                rows = self._parse_tsv(text)
                if rows and len(rows) >= 2:
                    self._insert_table_from_rows(rows)
                    return

        super().insertFromMimeData(source)

    def _looks_like_tsv_table(self, text):
        lines = [l for l in text.strip().split('\n') if l.strip()]
        if len(lines) < 2:
            return False
        tabs_count = [l.count('\t') for l in lines[:5]]
        if len(set(tabs_count)) == 1 and tabs_count[0] >= 1:
            return True
        commas_count = [l.count(',') for l in lines[:5]]
        if len(set(commas_count)) == 1 and commas_count[0] >= 2:
            return True
        return False

    def _parse_tsv(self, text):
        lines = [l for l in text.strip().split('\n') if l.strip()]
        if not lines:
            return []
        if '\t' in lines[0]:
            delim = '\t'
        else:
            delim = ','

        rows = []
        for line in lines:
            row = []
            cur = ""
            in_q = False
            for ch in line:
                if ch == '"':
                    in_q = not in_q
                elif ch == delim and not in_q:
                    row.append(cur.strip().strip('"'))
                    cur = ""
                else:
                    cur += ch
            row.append(cur.strip().strip('"'))
            rows.append(row)
        return rows

    def _insert_table_from_rows(self, rows):
        """从二维列表创建 QTextTable（表头加淡橙底纹）"""
        c = self._cursor_at_end()
        if not self._current_block_is_empty(c):
            c.insertBlock()
        n_rows = len(rows)
        n_cols = max(len(r) for r in rows)

        tf = QTextTableFormat()
        tf.setBorder(1)
        tf.setCellPadding(6)
        tf.setCellSpacing(0)
        tf.setBorderStyle(QTextTableFormat.BorderStyle_Solid)
        tf.setHeaderRowCount(1)
        tf.setBackground(QColor(_TABLE_BG))

        table = c.insertTable(n_rows, n_cols, tf)
        for ri, row in enumerate(rows):
            for ci in range(n_cols):
                text = row[ci] if ci < len(row) else ""
                cell = table.cellAt(ri, ci)
                cur = cell.firstCursorPosition()
                cur.insertText(text)
                if ri == 0:
                    fmt = QTextCharFormat()
                    fmt.setFontWeight(QFont.Bold)
                    fmt.setBackground(QColor(_TABLE_HEADER_BG))
                    fmt.setForeground(QColor(_DEFAULT_TEXT_COLOR))
                    cur.select(QTextCursor.BlockUnderCursor)
                    cur.mergeCharFormat(fmt)
                    cur.clearSelection()

    # ==================== 插入基础对象 ====================
    def insert_horizontal_line(self):
        c = self._cursor_at_end()
        c.insertBlock()
        c.insertHtml('<hr>')
        c.insertBlock()

    def insert_page_break(self):
        c = self._cursor_at_end()
        c.insertBlock()
        fmt = QTextBlockFormat()
        fmt.setPageBreakPolicy(QTextBlockFormat.PageBreak_AlwaysBefore)
        c.setBlockFormat(fmt)
        char_fmt = QTextCharFormat()
        char_fmt.setForeground(QColor("#BBB"))
        c.insertText("──── 分页符 ────", char_fmt)
        c.insertBlock()
        fmt2 = QTextBlockFormat()
        fmt2.setPageBreakPolicy(QTextBlockFormat.PageBreak_AlwaysBefore)
        c.setBlockFormat(fmt2)

    def insert_section_break(self):
        c = self._cursor_at_end()
        c.insertBlock()
        char_fmt = QTextCharFormat()
        char_fmt.setForeground(QColor("#FF8F00"))
        char_fmt.setFontPointSize(10)
        c.insertText("════ 分节符（新节开始） ════", char_fmt)
        c.insertBlock()
        fmt = QTextBlockFormat()
        fmt.setPageBreakPolicy(QTextBlockFormat.PageBreak_AlwaysBefore)
        c.setBlockFormat(fmt)

    def insert_current_date(self):
        self.textCursor().insertText(
            datetime.now().strftime('%Y年%m月%d日')
        )

    # ==================== 插入表格 ====================
    def insert_table_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("auto.beewrite_rich_editor.f9d8545d", "📋 插入表格"))
        form = QFormLayout(dlg)
        rows = QSpinBox()
        rows.setRange(1, 50)
        rows.setValue(3)
        form.addRow("行数:", rows)
        cols = QSpinBox()
        cols.setRange(1, 20)
        cols.setValue(3)
        form.addRow("列数:", cols)
        hdr = QCheckBox(tr("auto.beewrite_rich_editor.7bbad6ae", "含表头"))
        hdr.setChecked(True)
        form.addRow(hdr)
        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() == QDialog.Accepted:
            self._insert_table(rows.value(), cols.value(), hdr.isChecked())

    def _insert_table(self, rows, cols, has_header=True):
        c = self._cursor_at_end()
        if not self._current_block_is_empty(c):
            c.insertBlock()
        tf = QTextTableFormat()
        tf.setBorder(1)
        tf.setCellPadding(6)
        tf.setCellSpacing(0)
        tf.setBorderStyle(QTextTableFormat.BorderStyle_Solid)
        tf.setBackground(QColor(_TABLE_BG))
        if has_header:
            tf.setHeaderRowCount(1)
        table = c.insertTable(rows, cols, tf)
        if has_header and rows >= 1:
            for ci in range(cols):
                cell = table.cellAt(0, ci)
                cur = cell.firstCursorPosition()
                cur.select(QTextCursor.BlockUnderCursor)
                fmt = QTextCharFormat()
                fmt.setFontWeight(QFont.Bold)
                fmt.setBackground(QColor(_TABLE_HEADER_BG))
                fmt.setForeground(QColor(_DEFAULT_TEXT_COLOR))
                cur.mergeCharFormat(fmt)
                cur.clearSelection()

    def insert_dataframe_table(self, df, title=""):
        if df is None or df.empty:
            return
        c = self._cursor_at_end()
        if title:
            if not self._current_block_is_empty(c):
                c.insertBlock()
            f = QTextCharFormat()
            f.setFontPointSize(16)
            f.setFontWeight(QFont.Bold)
            c.insertText(title, f)
            c.insertBlock()
        else:
            if not self._current_block_is_empty(c):
                c.insertBlock()
        rows, cols = len(df) + 1, len(df.columns)
        tf = QTextTableFormat()
        tf.setBorder(1)
        tf.setCellPadding(6)
        tf.setCellSpacing(0)
        tf.setBorderStyle(QTextTableFormat.BorderStyle_Solid)
        tf.setHeaderRowCount(1)
        tf.setBackground(QColor(_TABLE_BG))
        table = c.insertTable(rows, cols, tf)
        for ci, cn in enumerate(df.columns):
            cc = table.cellAt(0, ci).firstCursorPosition()
            cc.insertText(str(cn))
            cc.select(QTextCursor.BlockUnderCursor)
            fmt = QTextCharFormat()
            fmt.setFontWeight(QFont.Bold)
            fmt.setBackground(QColor(_TABLE_HEADER_BG))
            fmt.setForeground(QColor(_DEFAULT_TEXT_COLOR))
            cc.mergeCharFormat(fmt)
            cc.clearSelection()
        for ri in range(len(df)):
            for ci in range(cols):
                val = df.iloc[ri, ci]
                text = (
                    ""
                    if (isinstance(val, float) and val != val)
                    else str(val)
                )
                table.cellAt(ri + 1, ci).firstCursorPosition().insertText(text)

    # ==================== 表格右键菜单 ====================
    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        t = self.textCursor().currentTable()
        if t:
            menu.addSeparator()
            menu.addAction(tr("auto.beewrite_rich_editor.36c83e53", "📋 上方插入行")).triggered.connect(
                lambda: self._insert_row(t, -1)
            )
            menu.addAction(tr("auto.beewrite_rich_editor.e2c257f4", "📋 下方插入行")).triggered.connect(
                lambda: t.appendRows(1)
            )
            menu.addAction(tr("auto.beewrite_rich_editor.8915aa4a", "📋 左侧插入列")).triggered.connect(
                lambda: self._insert_col(t, -1)
            )
            menu.addAction(tr("auto.beewrite_rich_editor.6154eff2", "📋 右侧插入列")).triggered.connect(
                lambda: t.appendColumns(1)
            )
            menu.addSeparator()
            menu.addAction(tr("auto.beewrite_rich_editor.8d3240d4", "❌ 删除当前行")).triggered.connect(
                lambda: self._delete_row(t)
            )
            menu.addAction(tr("auto.beewrite_rich_editor.b43820ae", "❌ 删除当前列")).triggered.connect(
                lambda: self._delete_col(t)
            )
            menu.addSeparator()
            menu.addAction(tr("auto.beewrite_rich_editor.09d684c7", "🔗 合并单元格")).triggered.connect(
                lambda: self._merge_cells(t)
            )
            menu.addAction(tr("auto.beewrite_rich_editor.14f02f54", "🔲 拆分单元格")).triggered.connect(
                lambda: self._split_cell(t)
            )
            menu.addSeparator()
            menu.addAction(tr("auto.beewrite_rich_editor.bedc41e8", "🎨 单元格背景色")).triggered.connect(
                self._cell_bg
            )
            menu.addAction(tr("auto.beewrite_rich_editor.e5d8c347", "🖍️ 单元格文字色")).triggered.connect(
                self._cell_fg
            )
        menu.exec(event.globalPos())

    # ==================== 表格辅助方法（右键菜单） ====================
    def _insert_row(self, t, pos):
        cell = t.cellAt(self.textCursor())
        if cell:
            insert_at = cell.row() + (0 if pos < 0 else 1)
            cur = self.textCursor()
            cur.beginEditBlock()
            try:
                t.insertRows(insert_at, 1)
            finally:
                cur.endEditBlock()

    def _insert_col(self, t, pos):
        cell = t.cellAt(self.textCursor())
        if cell:
            insert_at = cell.column() + (0 if pos < 0 else 1)
            cur = self.textCursor()
            cur.beginEditBlock()
            try:
                t.insertColumns(insert_at, 1)
            finally:
                cur.endEditBlock()

    def _delete_row(self, t):
        cell = t.cellAt(self.textCursor())
        if cell and t.rows() > 1:
            cur = self.textCursor()
            cur.beginEditBlock()
            try:
                t.removeRows(cell.row(), 1)
            finally:
                cur.endEditBlock()

    def _delete_col(self, t):
        cell = t.cellAt(self.textCursor())
        if cell and t.columns() > 1:
            cur = self.textCursor()
            cur.beginEditBlock()
            try:
                t.removeColumns(cell.column(), 1)
            finally:
                cur.endEditBlock()

    def _merge_cells(self, t):
        cursor = self.textCursor()
        if not cursor.hasSelection():
            return
        try:
            start = cursor.selectionStart()
            end = cursor.selectionEnd()
            c1 = QTextCursor(self.document())
            c1.setPosition(start)
            c2 = QTextCursor(self.document())
            c2.setPosition(end)
            cell1 = t.cellAt(c1)
            cell2 = t.cellAt(c2)
            if cell1.isValid() and cell2.isValid():
                r1, c1_ = cell1.row(), cell1.column()
                r2, c2_ = cell2.row(), cell2.column()
                r_start, r_end = min(r1, r2), max(r1, r2)
                c_start, c_end = min(c1_, c2_), max(c1_, c2_)
                cursor.beginEditBlock()
                try:
                    t.mergeCells(
                        r_start, c_start,
                        r_end - r_start + 1,
                        c_end - c_start + 1
                    )
                finally:
                    cursor.endEditBlock()
        except Exception:
            pass

    def _split_cell(self, t):
        cell = t.cellAt(self.textCursor())
        if cell:
            rowspan = cell.rowSpan()
            colspan = cell.colSpan()
            if rowspan > 1 or colspan > 1:
                cur = self.textCursor()
                cur.beginEditBlock()
                try:
                    t.splitCell(
                        cell.row(), cell.column(), rowspan, colspan
                    )
                finally:
                    cur.endEditBlock()

    def _cell_bg(self):
        col = QColorDialog.getColor()
        if col.isValid():
            fmt = QTextCharFormat()
            fmt.setBackground(col)
            self.textCursor().mergeCharFormat(fmt)

    def _cell_fg(self):
        col = QColorDialog.getColor()
        if col.isValid():
            fmt = QTextCharFormat()
            fmt.setForeground(col)
            self.textCursor().mergeCharFormat(fmt)