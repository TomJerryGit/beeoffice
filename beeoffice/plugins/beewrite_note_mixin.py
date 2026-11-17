"""BeeWrite 脚注/尾注/题注/交叉引用/目录更新/字数统计（W7）。"""
from __future__ import annotations

from PySide6.QtGui import QTextCharFormat, QTextCursor, QTextFormat, QTextBlockFormat
from PySide6.QtWidgets import QInputDialog, QMessageBox


class NoteMixin:
    """注释、题注、交叉引用、目录更新。"""

    def _ensure_note_state(self):
        if not hasattr(self, "_footnotes"):
            self._footnotes = []
        if not hasattr(self, "_endnotes"):
            self._endnotes = []
        if not hasattr(self, "_captions"):
            self._captions = []

    def _insert_note_marker(self, number, char_format=None):
        cursor = self.rich_editor.textCursor()
        cf = char_format or QTextCharFormat()
        cf.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignSuperScript)
        cursor.insertText(f"[{number}]", cf)
        self.rich_editor.setTextCursor(cursor)

    def _insert_footnote(self):
        self._ensure_note_state()
        text, ok = QInputDialog.getMultiLineText(self, "插入脚注", "脚注内容：")
        if not ok or not text.strip():
            return
        self._footnotes.append(text.strip())
        self._insert_note_marker(len(self._footnotes))
        self._set_status(f"已插入脚注 {len(self._footnotes)}（导出时写入文末）", 3000)

    def _insert_endnote(self):
        self._ensure_note_state()
        text, ok = QInputDialog.getMultiLineText(self, "插入尾注", "尾注内容：")
        if not ok or not text.strip():
            return
        self._endnotes.append(text.strip())
        self._insert_note_marker(len(self._endnotes))
        self._set_status(f"已插入尾注 {len(self._endnotes)}（导出时写入文末）", 3000)

    def _insert_caption(self):
        self._ensure_note_state()
        kind, ok = QInputDialog.getItem(
            self, "插入题注", "类型：", ["图", "表", "公式"], 0, False
        )
        if not ok:
            return
        text, ok = QInputDialog.getText(self, "插入题注", f"{kind}题注：")
        if not ok or not text.strip():
            return
        self._captions.append({"kind": kind, "text": text.strip()})
        number = len(self._captions)
        cursor = self.rich_editor.textCursor()
        cursor.insertBlock()
        cursor.insertText(f"{kind} {number}：{text.strip()}")
        self.rich_editor.setTextCursor(cursor)
        self._set_status(f"已插入{kind}题注 {number}", 3000)

    def _insert_cross_reference(self):
        self._ensure_note_state()
        if not self._captions:
            QMessageBox.information(self, "交叉引用", "当前文档还没有题注。")
            return
        labels = [
            f"{c['kind']} {i + 1}：{c['text']}"
            for i, c in enumerate(self._captions)
        ]
        label, ok = QInputDialog.getItem(
            self, "交叉引用", "引用题注：", labels, 0, False
        )
        if not ok:
            return
        number = labels.index(label) + 1
        kind = self._captions[number - 1]["kind"]
        cursor = self.rich_editor.textCursor()
        cursor.insertText(f"{kind} {number}")
        self.rich_editor.setTextCursor(cursor)
        self._set_status("已插入交叉引用", 2000)

    def _update_toc(self):
        """根据标题重建目录并插入光标处。"""
        headings = []
        it = self.rich_editor.document().begin()
        while it.isValid():
            level = it.blockFormat().headingLevel()
            if 1 <= level <= 4 and it.text().strip():
                headings.append((level, it.text()))
            it = it.next()

        cursor = self.rich_editor.textCursor()
        cursor.beginEditBlock()
        try:
            cursor.insertBlock()
            cursor.insertText("目录")
            marker_bf = QTextBlockFormat()
            marker_bf.setProperty(QTextFormat.UserProperty, 0xBEEF)
            cursor.setBlockFormat(marker_bf)
            for level, text in headings:
                cursor.insertBlock()
                cursor.insertText("    " * (level - 1) + text)
                cursor.setBlockFormat(marker_bf)
            if not headings:
                cursor.insertBlock()
                cursor.insertText("（暂无标题）")
                cursor.setBlockFormat(marker_bf)
        finally:
            cursor.endEditBlock()
        self._set_status(f"目录已更新（{len(headings)} 个标题）", 3000)

    def _add_toc_field(self, doc):
        """在 DOCX 中插入可更新的 Word TOC 域。"""
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        para = doc.add_paragraph()
        run = para.add_run()
        begin = OxmlElement("w:fldChar")
        begin.set(qn("w:fldCharType"), "begin")
        instr = OxmlElement("w:instrText")
        instr.set(qn("xml:space"), "preserve")
        instr.text = 'TOC \\o "1-3" \\h \\z \\u'
        sep = OxmlElement("w:fldChar")
        sep.set(qn("w:fldCharType"), "separate")
        end = OxmlElement("w:fldChar")
        end.set(qn("w:fldCharType"), "end")
        run._r.append(begin)
        run._r.append(instr)
        run._r.append(sep)
        para.add_run("（打开 Word 后右键目录 → 更新域）")
        para.add_run()._r.append(end)
        return para

    def _show_word_count_dialog(self):
        text = self.rich_editor.toPlainText()
        chars = len(text)
        paragraphs = len([p for p in text.splitlines() if p.strip()])
        from beeoffice.plugins.beewrite_utils import count_words
        words = count_words(text)
        QMessageBox.information(
            self, "字数统计",
            f"字数：{words}\n字符数：{chars}\n段落数：{paragraphs}",
        )

    def _append_notes_to_docx(self, path):
        """把脚注/尾注以文末注释区写入 DOCX。"""
        if not getattr(self, "_footnotes", None) and not getattr(self, "_endnotes", None):
            return
        try:
            from docx import Document
            doc = Document(path)
            doc.add_heading("注释", level=2)
            for i, note in enumerate(getattr(self, "_footnotes", []), 1):
                doc.add_paragraph(f"{i}. {note}")
            for i, note in enumerate(getattr(self, "_endnotes", []), 1):
                doc.add_paragraph(f"尾注 {i}. {note}")
            doc.save(path)
        except Exception:  # noqa: BLE001
            pass
