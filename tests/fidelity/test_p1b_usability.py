# tests/fidelity/test_p1b_usability.py
"""
P1-B：**实机试用定位**发现的三处可用性/数据安全问题。

三项都不是"猜"出来的，是运行程序测出来的：

### 1. 刚打开文档按 Ctrl+Z 会删掉正文（**数据安全**）

实测：`set_content()` 装载文档后 `document().isUndoAvailable()` 就是 **True**
——**程序化装载内容本身进了撤销栈**。于是用户什么都没改，按一下 Ctrl+Z：

    加载后 689 字符 → 撤销一次 677 → 再撤 677 → 676   ⚠️ 正文被删

修法：装载完成时清空撤销栈（`reset_undo_history()`），
"无可撤销的操作"才是刚打开文件时符合直觉的状态。
⚠️ 只在**文件加载完成**时清，不放进 `set_markdown`（用户编辑中途切模式也会调它，
清栈会丢掉用户自己的撤销历史）。

### 2. 打开不支持的类型**毫无反馈**（最糟的失败模式）

实测：打开 `.doc` 时**不弹提示、不开标签**，只写一行日志，
**还把文件记进"最近文件"** —— 用户会以为程序坏了。`.pptx` 同样。

修法：明确弹框说明支持的格式 + **不记进最近文件**。

### 3. 蜜算/蜜演**完全没有打印**（功能缺失，不是"薄弱"）

实测清点：蜜写有完整实现（工具栏「🖨️ 打印预览」+ Ctrl+P + 右键菜单 +
`QPrintPreviewDialog`）；**蜜算 0 处、蜜演 0 处**。
表格打印（分页/缩放/重复标题行）是办公刚需 —— 这是**要开发**的项，本文件不做。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ==================== 1. 撤销边界（数据安全）====================

def test_loading_does_not_leave_undoable_content(qtbot):
    """
    **核心回归**：装载文档后清栈，撤销不得改动正文。

    实测缺陷：清栈前 `isUndoAvailable()` 为 True，Ctrl+Z 会把正文删成
    689→677 字符（用户什么都没改）。
    """
    from beeoffice.plugins.beewrite import BeeWriteEditor

    editor = BeeWriteEditor()
    qtbot.addWidget(editor)
    editor.set_content("\n\n".join(f"第 {i} 段：正文内容。" for i in range(1, 51)))
    editor._switch_mode("rich_text")
    qtbot.wait(20)

    rich = editor.rich_editor
    loaded = rich.toPlainText()

    # 未清栈时确实"可撤销"（说明缺陷真实存在，不是测试造出来的）
    assert rich.document().isUndoAvailable(), (
        "前置条件变了：装载后不再是可撤销状态，本测试前提需重新确认"
    )

    editor.reset_undo_history()

    assert not rich.document().isUndoAvailable(), (
        "清栈后仍显示可撤销"
    )
    for _ in range(3):
        rich.undo()
    qtbot.wait(10)
    assert rich.toPlainText() == loaded, (
        f"清栈后撤销仍改动了正文：{len(loaded)} → {len(rich.toPlainText())}"
    )
    editor.close()


def test_undo_still_works_after_typing(qtbot):
    """清栈不能把撤销功能一起弄坏：装入后输入的内容仍应可撤销。"""
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication

    from beeoffice.plugins.beewrite import BeeWriteEditor

    editor = BeeWriteEditor()
    qtbot.addWidget(editor)
    editor.set_content("正文")
    editor._switch_mode("rich_text")
    qtbot.wait(20)
    rich = editor.rich_editor
    editor.reset_undo_history()

    before = rich.toPlainText()
    for ch in "新增":
        QApplication.sendEvent(rich, QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_A,
            Qt.KeyboardModifier.NoModifier, ch))
        qtbot.wait(1)
    typed = rich.toPlainText()
    assert len(typed) > len(before)

    rich.undo()
    qtbot.wait(10)
    assert rich.toPlainText() == before, "撤销没有精确回退输入"
    editor.close()


def test_reset_undo_history_is_safe_on_empty_editor(qtbot):
    """空编辑器上调用不应抛异常。"""
    from beeoffice.plugins.beewrite import BeeWriteEditor

    editor = BeeWriteEditor()
    qtbot.addWidget(editor)
    editor.reset_undo_history()
    editor.close()


# ==================== 2. 不支持的类型要有反馈 ====================

class _FakeWindow:
    """只取 `_open_recent` 需要的那点接口（避免起整套 UI）。"""

    def __init__(self):
        from types import SimpleNamespace

        self.dialogs = []
        self.recent_added = []
        self.settings = SimpleNamespace(
            recent_files=[],
            add_recent_file=lambda p: self.recent_added.append(p),
            save=lambda: None,
        )
        self.opened = []

    # 从 BeeApp 借真实方法
    _open_recent = None


def _make_window():
    from beeoffice.app import BeeApp

    window = _FakeWindow()
    window._open_recent = BeeApp._open_recent.__get__(window, _FakeWindow)
    window._open_sheet_file = lambda p: window.opened.append(("sheet", p))
    window._open_docx_file = lambda p: window.opened.append(("docx", p))
    window._open_text_file = lambda p: window.opened.append(("text", p))
    window._update_recent_menu = lambda: None
    return window


@pytest.mark.parametrize("name", ["老文档.doc", "book.xlsm"])
def test_unsupported_extension_shows_message_and_skips_recent(
        tmp_path, monkeypatch, name):
    """
    **核心回归**：不支持的类型必须**明确告知**，且**不进最近文件**。

    实测缺陷：原先只写一行日志 —— 不弹提示、不开标签、还记进最近文件。
    """
    from PySide6.QtWidgets import QMessageBox

    shown = []
    monkeypatch.setattr(
        QMessageBox, "information",
        staticmethod(lambda parent, title, text, *a, **k: shown.append(
            (title, text))),
    )

    path = tmp_path / name
    path.write_bytes(b"\xd0\xcf\x11\xe0" + b"\x00" * 64)

    window = _make_window()
    window._open_recent(str(path))

    assert shown, f"打开 {name} 时没有给用户任何反馈"
    title, text = shown[0]
    assert "不支持" in title or "格式" in title, title
    assert ".docx" in text and ".xlsx" in text, "应告知支持哪些格式"

    assert not window.recent_added, (
        f"打不开的文件不该进最近文件，却加了 {window.recent_added}"
    )
    assert not window.opened, "不应该尝试打开"


def test_supported_extensions_still_open_and_go_to_recent(tmp_path):
    """修复不能误伤正常路径：.docx/.xlsx 仍要打开并进最近文件。"""
    window = _make_window()
    for name, kind in (("a.docx", "docx"), ("b.xlsx", "sheet"),
                       ("c.csv", "sheet"), ("d.md", "text")):
        path = tmp_path / name
        path.write_bytes(b"x")
        window._open_recent(str(path))
        assert window.opened[-1][1] == str(path), f"{name} 没被打开"
    assert len(window.recent_added) == 4, window.recent_added


def test_missing_file_still_warns(tmp_path, monkeypatch):
    """文件不存在的老路径不受影响。"""
    from PySide6.QtWidgets import QMessageBox

    shown = []
    monkeypatch.setattr(
        QMessageBox, "warning",
        staticmethod(lambda *a, **k: shown.append(a)),
    )

    window = _make_window()
    window.settings.recent_files = []
    window._open_recent(str(tmp_path / "不存在.docx"))

    assert shown, "文件不存在应提示"
