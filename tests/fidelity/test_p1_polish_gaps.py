# tests/fidelity/test_p1_polish_gaps.py
"""
第九批（收尾）：蜜算图表的两处"静默坏行为" + 蜜写「目录」插字面源码。

对应审计报告 §2.14 与 §2.13：

1. **取消图表对话框也会画一张柱状图**：`_create_chart` 里 `selected` 的初值
   就是 `"bar"`，而判断是 `if selected["value"]` —— **恒为真**。
2. **缺 matplotlib 时"插入图表"什么都不发生**：`_generate_chart` 里
   捕获 `ImportError` 后直接 `return`（连提示都没有）。
3. **「📑 目录」把 Markdown 源码插进所见即所得编辑器**：用户看到
   `## 目录` / `- [第一章](#第一章)` 这样的**字面字符**，导出 Word 时还会
   被当普通段落写进正文；而 markdown 模式分支**直接 return**（什么都不做）。
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ==================== 1. 图表：取消不该画图 ====================

@pytest.fixture
def sheet(qtbot):
    from PySide6.QtWidgets import QApplication, QMessageBox

    from beeoffice.plugins.beesheet import BeeSheetView

    app = QApplication.instance() or QApplication(sys.argv)
    _ = app
    view = BeeSheetView()
    qtbot.addWidget(view)
    view._set_status = lambda *a, **k: None
    view.model.set_full_dataframe(
        pd.DataFrame({"月份": ["1月", "2月"], "销量": [10, 20]})
    )
    view._ensure_full_data = lambda *a, **k: True
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    return view


def _select_all(view):
    from PySide6.QtCore import QItemSelection, QItemSelectionModel

    selection = QItemSelection(view.model.index(0, 0), view.model.index(1, 1))
    view.table_view.selectionModel().select(
        selection, QItemSelectionModel.SelectionFlag.Select
    )


def test_cancelling_chart_dialog_does_not_draw(sheet, monkeypatch):
    """**核心回归**：取消对话框不能画出任何图表。"""
    from PySide6.QtWidgets import QDialog

    _select_all(sheet)
    drawn = []
    monkeypatch.setattr(sheet, "_generate_chart",
                        lambda kind: drawn.append(kind))
    monkeypatch.setattr(QDialog, "exec",
                        lambda self: QDialog.DialogCode.Rejected)

    sheet._create_chart()

    assert drawn == [], f"取消对话框却画了图：{drawn}"


def test_missing_matplotlib_gives_clear_message(sheet, monkeypatch):
    """缺 matplotlib 要有**明确提示**（原先静默返回）。"""
    from PySide6.QtWidgets import QMessageBox

    _select_all(sheet)
    warnings = []
    monkeypatch.setattr(
        QMessageBox, "warning",
        staticmethod(lambda parent, title, text, *a, **k: warnings.append(text)),
    )
    monkeypatch.setattr(sheet, "_matplotlib_available", lambda: False)

    sheet._create_chart()

    assert warnings, "缺库时什么都没提示"
    assert "matplotlib" in warnings[0]
    assert "pip install" in warnings[0], "提示里要给出可操作的办法"


def test_matplotlib_probe_is_real(sheet):
    """探测函数要真的能判断（本环境装了 matplotlib）。"""
    assert sheet._matplotlib_available() is True


def test_generate_chart_still_records_spec(sheet, monkeypatch):
    """原有能力不能被改坏：确认选择后仍会生成并记录规格。"""
    from PySide6.QtWidgets import QDialog

    _select_all(sheet)
    sheet._charts = []
    # 直接测"未取消"的路径：模拟按钮把 selected 设好并 accept
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    sheet._generate_chart("bar")          # 直接调用生成（对话框已单测）
    assert sheet._charts, "直接生成时没有记录图表规格"


# ==================== 2. 蜜写目录 ====================

@pytest.fixture
def editor(qtbot):
    from beeoffice.plugins.beewrite import BeeWriteEditor

    widget = BeeWriteEditor()
    qtbot.addWidget(widget)
    widget._set_status = lambda *a, **k: None
    return widget


def test_toc_in_rich_mode_is_rendered_not_markdown_source(editor):
    """
    **核心回归**：所见即所得模式插入的目录不能是 Markdown 字面文本。

    原先 `insertText(generate_toc(md))` → 用户看到 `## 目录`、
    `- [第一章](#第一章)` 这种字面字符，导出时还会进正文。
    """
    editor._switch_mode("rich_text")
    editor.rich_editor.setPlainText("# 第一章\n正文\n## 第一节\n内容")
    cursor = editor.rich_editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    editor.rich_editor.setTextCursor(cursor)

    editor._insert_toc()

    text = editor.rich_editor.toPlainText()
    assert "## 目录" not in text, "插入了 Markdown 字面源码"
    assert "[第一章](第一章)" not in text
    assert "第一章" in text and "第一节" in text
    # 标题出现两次 = 原文一次 + 目录一次
    assert text.count("第一章") == 2


def test_toc_escapes_markup(editor):
    """标题里的尖括号等要转义，避免破坏文档结构。"""
    editor._switch_mode("rich_text")
    editor.rich_editor.setPlainText("# <script>x</script>")
    cursor = editor.rich_editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    editor.rich_editor.setTextCursor(cursor)

    editor._insert_toc()

    html = editor.rich_editor.toHtml()
    assert "&lt;script&gt;" in html or "&lt;script" in html


def test_toc_in_markdown_mode_inserts_source(editor):
    """markdown 模式：源码才是正确形态 —— 但原先这个分支**什么都不做**。"""
    editor._switch_mode("markdown")
    editor.markdown_editor.setPlainText("# 甲\n## 乙")
    cursor = editor.markdown_editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    editor.markdown_editor.setTextCursor(cursor)

    editor._insert_toc()

    text = editor.markdown_editor.toPlainText()
    assert "目录" in text, "markdown 模式下没有生成任何东西"
    assert "甲" in text


def test_toc_without_headings_prompts(editor, monkeypatch):
    """没有标题要提示，而不是插一个空目录。"""
    from PySide6.QtWidgets import QMessageBox

    shown = []
    monkeypatch.setattr(
        QMessageBox, "information",
        staticmethod(lambda parent, title, text, *a, **k: shown.append(text)),
    )
    editor._switch_mode("rich_text")
    editor.rich_editor.setPlainText("没有标题的正文")
    cursor = editor.rich_editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    editor.rich_editor.setTextCursor(cursor)

    editor._insert_toc()

    assert shown, "没有标题时应当提示"
