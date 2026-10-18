# beeoffice/plugins/beewrite_md_table_dialog.py
"""
蜜写 Markdown 表格可视化编辑对话框（MarkdownTableEditorDialog）

职责：
  - 在对话框中以富文本表格的形式展示 Markdown 表格
  - 支持加行 / 加列 / 删行 / 删列
  - 支持表头加粗显示
  - 确定后回写为二维列表（供上层渲染为 Markdown）

使用方式：
    dlg = MarkdownTableEditorDialog(rows, parent)
    if dlg.exec() == QDialog.Accepted:
        new_rows = dlg.rows
        # 上层调用 beewrite_utils.render_md_table(new_rows)

依赖：
  - PySide6（QDialog / QTextEdit / QTextTableFormat 等）
  - 不导入任何 beewrite_* 模块，避免循环依赖
"""
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QPushButton,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QFont,
    QTextCursor,
    QTextCharFormat,
    QTextTableFormat,
)
from beeoffice.i18n import tr


# ==================== Markdown 表格编辑对话框 ====================
class MarkdownTableEditorDialog(QDialog):
    """Markdown 表格可视化编辑对话框"""

    def __init__(self, rows, parent=None):
        """
        :param rows: 二维列表（第一行为表头），如 [["A", "B"], ["1", "2"]]
        :param parent: 父窗口
        """
        super().__init__(parent)
        self.setWindowTitle(tr("auto.beewrite_md_table_dialog.edfe0182", "📊 编辑 Markdown 表格"))
        self.resize(700, 500)
        # 深拷贝，避免修改原始数据
        self.rows = [list(r) for r in rows]

        layout = QVBoxLayout(self)

        # 顶部提示
        tip = QLabel(
            tr("auto.beewrite_md_table_dialog.42730a08", "💡 编辑完成后点击「确定」回写 Markdown，点击「取消」放弃修改\n"
            "Tab 跳下一格 · 右键表格加行/列")
        )
        tip.setStyleSheet("color:#666;font-size:12px;padding:4px;")
        layout.addWidget(tip)

        # 编辑器
        self.editor = QTextEdit()
        self.editor.setStyleSheet(
            "QTextEdit{background:#FFF;border:1px solid #CCC;"
            "padding:8px;font-size:14px;}"
        )
        layout.addWidget(self.editor, 1)

        # 底部按钮栏
        bl = QHBoxLayout()

        add_row_btn = QPushButton(tr("auto.beewrite_md_table_dialog.bca250c6", "➕ 加行"))
        add_row_btn.clicked.connect(self._add_row)
        bl.addWidget(add_row_btn)

        add_col_btn = QPushButton(tr("auto.beewrite_md_table_dialog.54bb7f69", "➕ 加列"))
        add_col_btn.clicked.connect(self._add_col)
        bl.addWidget(add_col_btn)

        del_row_btn = QPushButton(tr("auto.beewrite_md_table_dialog.2feac660", "➖ 删行"))
        del_row_btn.clicked.connect(self._del_row)
        bl.addWidget(del_row_btn)

        del_col_btn = QPushButton(tr("auto.beewrite_md_table_dialog.4e3f9310", "➖ 删列"))
        del_col_btn.clicked.connect(self._del_col)
        bl.addWidget(del_col_btn)

        bl.addStretch()

        ok_btn = QPushButton(tr("auto.beewrite_md_table_dialog.673142b9", "✅ 确定"))
        ok_btn.setStyleSheet(
            "QPushButton{background:#FFB300;color:#000;"
            "padding:6px 16px;border:none;border-radius:4px;"
            "font-weight:bold;}"
            "QPushButton:hover{background:#FFA000;}"
        )
        ok_btn.clicked.connect(self._on_ok)
        bl.addWidget(ok_btn)

        cancel_btn = QPushButton(tr("auto.beewrite_md_table_dialog.4d0b4688", "取消"))
        cancel_btn.clicked.connect(self.reject)
        bl.addWidget(cancel_btn)

        layout.addLayout(bl)

        # 初始化表格内容
        self._load_rows()

    # ==================== 加载 / 读取 ====================
    def _load_rows(self):
        """把二维列表填充到编辑器表格"""
        self.editor.clear()
        c = self.editor.textCursor()
        n_rows = len(self.rows)
        n_cols = max((len(r) for r in self.rows), default=0)
        if n_rows == 0 or n_cols == 0:
            return

        tf = QTextTableFormat()
        tf.setBorder(1)
        tf.setCellPadding(6)
        tf.setCellSpacing(0)
        tf.setBorderStyle(QTextTableFormat.BorderStyle_Solid)
        tf.setHeaderRowCount(1)
        table = c.insertTable(n_rows, n_cols, tf)

        for ri in range(n_rows):
            for ci in range(n_cols):
                text = self.rows[ri][ci] if ci < len(self.rows[ri]) else ""
                cell = table.cellAt(ri, ci)
                cur = cell.firstCursorPosition()
                cur.insertText(text)
                # 表头加粗
                if ri == 0:
                    fmt = QTextCharFormat()
                    fmt.setFontWeight(QFont.Bold)
                    cur.select(QTextCursor.BlockUnderCursor)
                    cur.mergeCharFormat(fmt)
                    cur.clearSelection()

    def _read_rows(self):
        """从编辑器表格读回二维列表"""
        doc = self.editor.document()
        block = doc.begin()
        table = None
        while block.isValid():
            c = QTextCursor(block)
            t = c.currentTable()
            if t:
                table = t
                break
            block = block.next()
        if not table:
            return []

        rows = []
        for r in range(table.rows()):
            row = []
            for c_ in range(table.columns()):
                cell = table.cellAt(r, c_)
                text = cell.firstCursorPosition().block().text()
                row.append(text.strip())
            rows.append(row)
        return rows

    def _get_table(self):
        """获取编辑器中的第一个 QTextTable"""
        doc = self.editor.document()
        block = doc.begin()
        while block.isValid():
            c = QTextCursor(block)
            t = c.currentTable()
            if t:
                return t
            block = block.next()
        return None

    # ==================== 行 / 列操作 ====================
    def _add_row(self):
        """追加一行"""
        t = self._get_table()
        if t:
            t.appendRows(1)

    def _add_col(self):
        """追加一列"""
        t = self._get_table()
        if t:
            t.appendColumns(1)

    def _del_row(self):
        """删除光标所在行（至少保留一行）"""
        t = self._get_table()
        if t:
            cursor = self.editor.textCursor()
            cell = t.cellAt(cursor)
            if cell.isValid() and t.rows() > 1:
                t.removeRows(cell.row(), 1)

    def _del_col(self):
        """删除光标所在列（至少保留一列）"""
        t = self._get_table()
        if t:
            cursor = self.editor.textCursor()
            cell = t.cellAt(cursor)
            if cell.isValid() and t.columns() > 1:
                t.removeColumns(cell.column(), 1)

    # ==================== 确认 ====================
    def _on_ok(self):
        """确认：把编辑器表格回读为二维列表，然后 accept"""
        self.rows = self._read_rows()
        self.accept()