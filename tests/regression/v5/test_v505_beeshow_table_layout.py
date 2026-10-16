# tests/regression/v5/test_v505_beeshow_table_layout.py
"""
优化规划 §1.6 / §1.7 回归：蜜演表格与版式的数据破坏缺陷。

§1.6a `_insert_col` 参数顺序写反
    `self._table.setItem(insert_at, r, QTableWidgetItem(""))`，而实际签名是
    setItem(row, column, item)。于是把列号当行号，用空 item 覆盖了第
    insert_at 行的各列——静默丢数据；当行数小于列号时越界报错。

§1.6b `_replace_current_table` 删掉表格之间的正文
    表格范围取「第一个 | 行」到「最后一个 | 行」，于是页面里存在两个表格、
    或表格之后还有正文时，中间内容被整体删除。

§1.7 `_apply_layout` 静默清空整份文档
    `self._editor.setPlainText(skeleton)`，无确认、无撤销、不限于当前页。

这里用轻量 fake 承载 Mixin，避免实例化 BeeShowView（会拉起 QtWebEngine，
在 offscreen 下退出时会触发已知的原生崩溃，见优化规划 §4.2）。
"""
from PySide6.QtWidgets import QMessageBox, QPlainTextEdit, QTableWidget, QTableWidgetItem

from beeoffice.plugins.beeshow_table_mixin import TableEditorDialog, TableMixin
from beeoffice.plugins.beeshow_layout_mixin import LayoutMixin


class _TableHost(TableMixin):
    """只提供 _insert_col / _replace_current_table 需要的最小状态。"""

    def __init__(self):
        self._table = QTableWidget(3, 3)
        self._current_slide = 0
        self._slides_md = [""]
        self._editor = QPlainTextEdit()
        self.preview_updates = 0

    def _update_preview(self):
        self.preview_updates += 1


class _DialogHost:
    """
    承载 TableEditorDialog 的插入行列逻辑。

    这些方法只用到 self._table 与 self._update_preview()，因此以"借用方法"
    的方式调用（TableEditorDialog._insert_col(host, ...)），避免为了测一段
    纯逻辑而构建整个 QDialog（含表格、按钮等 UI，且会拉更多 Qt 依赖）。
    """

    def __init__(self, rows=3, cols=3):
        self._table = QTableWidget(rows, cols)
        self.preview_updates = 0

    def _update_preview(self):
        self.preview_updates += 1


class _LayoutHost(LayoutMixin):
    """只提供 _apply_layout 需要的最小状态。"""

    def __init__(self, text=""):
        self._editor = QPlainTextEdit()
        self._editor.setPlainText(text)
        self._current_slide = 3
        self.snapshots = 0
        self.statuses = []

    def _update_preview(self):
        pass

    def _set_status(self, msg, timeout=0):
        self.statuses.append(msg)

    def _save_snapshot(self, force=False):
        self.snapshots += 1


# ==================== §1.6a 插入列不得破坏已有数据 ====================

def test_insert_col_preserves_existing_cells():
    host = _DialogHost()
    for r in range(3):
        for c in range(3):
            host._table.setItem(r, c, QTableWidgetItem(f"r{r}c{c}"))

    host._table.setCurrentCell(1, 1)   # 在第 1 列右侧插入
    TableEditorDialog._insert_col(host, offset=+1)

    assert host._table.columnCount() == 4
    # 原有三列的数据必须逐格保留（含被插入位置之后的那一列）
    assert host._table.item(0, 0).text() == "r0c0"
    assert host._table.item(0, 1).text() == "r0c1"
    assert host._table.item(0, 3).text() == "r0c2", "插入列右侧的原数据被清掉了"
    assert host._table.item(2, 3).text() == "r2c2"
    # 新插入的列应为空
    assert host._table.item(0, 2).text() == ""
    assert host._table.item(1, 2).text() == ""
    assert host._table.item(2, 2).text() == ""


def test_insert_col_no_crash_when_rows_less_than_column_index():
    """原实现把列号当行号，行数不足时会越界；修复后不应异常。"""
    host = _DialogHost(rows=2, cols=6)
    host._table.setCurrentCell(0, 5)   # 列号 5 > 行数 2
    TableEditorDialog._insert_col(host, offset=+1)   # 不应抛异常
    assert host._table.columnCount() == 7


# ==================== §1.6b 替换表格不得删除表格外的正文 ====================

def test_replace_table_keeps_text_between_tables():
    host = _TableHost()
    host._slides_md = [
        "# 标题\n"
        "| A | B |\n"
        "| --- | --- |\n"
        "| 1 | 2 |\n"
        "\n"
        "中间这段正文必须保留\n"
        "\n"
        "| C | D |\n"
        "| --- | --- |\n"
        "| 3 | 4 |\n"
        "结尾这段也必须保留\n"
    ]
    host._editor.setPlainText(host._slides_md[0])

    host._replace_current_table("| A | B |\n| --- | --- |\n| 9 | 9 |")

    new_text = host._editor.toPlainText()
    assert "中间这段正文必须保留" in new_text, "两张表格之间的正文被删除了"
    assert "结尾这段也必须保留" in new_text, "表格之后的正文被删除了"
    assert "| 9 | 9 |" in new_text, "新表格没有写入"


def test_replace_table_only_replaces_the_first_block():
    """第二个表格不应被当作第一个表格的一部分而消失。"""
    host = _TableHost()
    host._slides_md = [
        "| A |\n| --- |\n| 1 |\n\n正文\n\n| B |\n| --- |\n| 2 |\n"
    ]
    host._editor.setPlainText(host._slides_md[0])

    host._replace_current_table("| A |\n| --- |\n| 100 |")

    new_text = host._editor.toPlainText()
    assert "| 100 |" in new_text
    assert "| B |" in new_text, "第二张表格不应被吞掉"


# ==================== §1.7 应用版式必须可确认、可回滚 ====================

def _patch_question(monkeypatch, answer):
    calls = []
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: calls.append(a) or answer),
    )
    return calls


def test_apply_layout_cancel_keeps_content(monkeypatch):
    """用户点「否」时文档必须原样保留。"""
    host = _LayoutHost("# 我辛苦写的幻灯片\n\n正文")
    before = host._editor.toPlainText()
    calls = _patch_question(monkeypatch, QMessageBox.No)

    host._apply_layout("title_only")

    assert calls, "内容非空时必须先确认"
    assert host._editor.toPlainText() == before, "取消后内容不得改变"
    assert host.snapshots == 0, "取消时不应写快照"


def test_apply_layout_confirm_snapshots_first(monkeypatch):
    """确认后：先存快照，再替换全文。"""
    host = _LayoutHost("# 旧内容")
    _patch_question(monkeypatch, QMessageBox.Yes)

    host._apply_layout("title_only")

    assert host.snapshots == 1, "替换前必须保存快照以便回滚"
    assert host._editor.toPlainText() != "# 旧内容"


def test_apply_layout_empty_document_does_not_prompt(monkeypatch):
    """空文档无需确认。"""
    host = _LayoutHost("")
    calls = _patch_question(monkeypatch, QMessageBox.No)

    host._apply_layout("title_only")

    assert calls == [], "空文档不应弹确认框"
    assert host._editor.toPlainText() != ""


def test_apply_layout_unknown_id_is_noop(monkeypatch):
    host = _LayoutHost("# 原内容")
    before = host._editor.toPlainText()
    _patch_question(monkeypatch, QMessageBox.Yes)

    host._apply_layout("no_such_layout")

    assert host._editor.toPlainText() == before
    assert host.snapshots == 0
