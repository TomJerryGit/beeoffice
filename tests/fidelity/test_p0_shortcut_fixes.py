# tests/fidelity/test_p0_shortcut_fixes.py
"""
P0 修复：**同键注册导致的 Qt 歧义快捷键**（Ctrl+S 完全失效 / 蜜算 Ctrl+Z 失效），
以及蜜写 `editor` 属性指向隐藏编辑器。

## 背景（实测）
`menus.py` 为「保存」「撤销」「重做」注册了**窗口级** QAction（默认 `WindowShortcut`），
而蜜写的 `beewrite.py` 与蜜算的 `beesheet_ui_mixin.py` 又对**同一个键**注册了 QShortcut
（同样默认 `WindowShortcut`）→ Qt 判为 `Ambiguous shortcut overload`，
**两个槽都不执行**。现象就是：蜜写里按 Ctrl+S 毫无反应、蜜算里按 Ctrl+Z 毫无反应。

## 修法
把模块级快捷键改为 `Qt.ShortcutContext.WidgetWithChildrenShortcut`：
Qt 按"上下文更具体者优先"分派 —— 焦点在控件内走模块处理，焦点在别处仍由窗口级动作兜住。
（已核对：这两个模块与菜单的交集**只有** 蜜写 Ctrl+S 与 蜜算 Ctrl+Z/Ctrl+Y，
其余快捷键无冲突，所以只改了这三处，不扩大改动面。）

## 本文件守的
1. **行为级**：真发按键，断言被调用（不只是"上下文对不对"）；
2. **静态级**：这两个模块里不允许再出现"同键同上下文"的重复注册（防回归）。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt                                          # noqa: E402
from PySide6.QtGui import QShortcut                                    # noqa: E402

WIDGET_CHILD = Qt.ShortcutContext.WidgetWithChildrenShortcut


def _contexts(widget):
    """把控件里的快捷键按"键 → 上下文集合"归并。"""
    found = {}
    for shortcut in widget.findChildren(QShortcut):
        found.setdefault(shortcut.key().toString(), set()).add(
            shortcut.context()
        )
    return found


# ==================== 1. 静态：不再有同键同上下文的重复注册 ====================

@pytest.mark.parametrize("factory", ["beewrite", "beesheet"])
def test_no_duplicate_shortcut_in_same_context(qtbot, factory):
    """
    同键 + 同上下文 = Qt 歧义 → 两个都不触发。**这条防回归**。

    （菜单里那份是窗口级，模块这份是控件级，二者上下文不同，属正常分工。）
    """
    from beeoffice.plugins.beesheet import BeeSheetView
    from beeoffice.plugins.beewrite import BeeWriteEditor

    widget = BeeWriteEditor() if factory == "beewrite" else BeeSheetView()
    qtbot.addWidget(widget)
    try:
        duplicated = []
        for shortcut in widget.findChildren(QShortcut):
            same_key_same_ctx = [
                other for other in widget.findChildren(QShortcut)
                if other is not shortcut
                and other.key() == shortcut.key()
                and other.context() == shortcut.context()
            ]
            if same_key_same_ctx:
                duplicated.append(shortcut.key().toString())
        assert not duplicated, (
            f"{factory} 存在同键同上下文的快捷键（会造成 Qt 歧义）："
            f"{sorted(set(duplicated))}"
        )
    finally:
        widget.close()


def test_conflicting_keys_have_single_source(qtbot):
    """
    与菜单同键的那几个键，**模块侧必须不再注册**（唯一来源原则）。

    （我中途试过"改成 WidgetWithChildren 上下文让模块侧胜出"——**不行**：
      Qt 的上下文只决定"是否匹配"、**不做优先级排序**，两个都匹配仍判歧义。
      所以正确做法是只留一个来源：菜单动作。这条测试就是钉住这一点。）
    """
    from beeoffice.plugins.beesheet import BeeSheetView
    from beeoffice.plugins.beewrite import BeeWriteEditor

    editor = BeeWriteEditor()
    sheet = BeeSheetView()
    qtbot.addWidget(editor)
    qtbot.addWidget(sheet)
    try:
        # 蜜写曾与「保存」同键
        assert _shortcut_count(editor, "Ctrl+S") == 0
        # 蜜算曾与「撤销/重做」同键
        assert _shortcut_count(sheet, "Ctrl+Z") == 0
        assert _shortcut_count(sheet, "Ctrl+Y") == 0
    finally:
        editor.close()
        sheet.close()


# ==================== 2. 行为级：真发按键，看有没有被调用 ====================

def _shortcut_for(widget, key_text):
    """取某个控件里指定按键的 QShortcut（用于观察它是否被触发）。"""
    for shortcut in widget.findChildren(QShortcut):
        if shortcut.key().toString() == key_text:
            return shortcut
    return None


def _shortcut_count(widget, key_text):
    return sum(
        1 for sc in widget.findChildren(QShortcut)
        if sc.key().toString() == key_text
    )


def test_ctrl_s_actually_triggers_save(qtbot, app, monkeypatch):
    """
    **核心验收**：真实 BeeApp 里按 Ctrl+S 必须真的走到蜜写的 `save()`。

    ⚠️ 踩坑记录（这条测试我返工过两次，值得留着）：
    1. 用**裸 `BeeWriteEditor`** 测 → 裸控件里没有菜单 QAction，**根本不存在冲突**，
       把实现改回"重复注册"它照样通过 → 没有牙；
    2. 改成在**真实 app** 里 `editor.save = lambda: ...` → 快捷键/菜单在**构造时**
       就 connect 了绑定方法，**事后再赋值不会改变连接** → 观察不到；
    3. 最终：真实 app + **在类上**打桩 `BeeWriteEditor.save`（`_save_current`
       是调用时才 `widget.save()` → 类属性查找）✓ 这样才既还原冲突、又能观察。
    """
    from PySide6.QtTest import QTest

    from beeoffice.plugins.beewrite import BeeWriteEditor

    # ⚠️ 必须让主窗口**真正显示**：窗口级 QAction 的快捷键要求窗口处于激活态，
    # `app` fixture 默认不 show → 按键不会进快捷键系统（我第一版就栽在这里）。
    app.show()
    qtbot.waitExposed(app)

    editor = BeeWriteEditor()
    qtbot.addWidget(editor)
    app.tab_manager.addTab(editor, "蜜写")
    app.tab_manager.setCurrentWidget(editor)
    editor.show()
    qtbot.waitExposed(editor)

    calls = []
    monkeypatch.setattr(BeeWriteEditor, "save",
                        lambda self: calls.append("save") or True)

    editor.markdown_editor.setFocus()
    qtbot.wait(80)
    QTest.keyClick(editor.markdown_editor, Qt.Key.Key_S,
                   Qt.KeyboardModifier.ControlModifier)
    qtbot.wait(80)

    assert calls, "真实 app 里按 Ctrl+S 没有触发保存 —— 又出现同键歧义了"
    editor.close()


def test_sheet_ctrl_z_and_y_reach_the_view(qtbot, app):
    """
    蜜算里 Ctrl+Z / Ctrl+Y 必须真的调到**视图**的 undo/redo。

    设计：QShortcut 那两份**已删除**，统一由菜单 QAction 负责；
    `menus._apply_undo` 在**调用时**用 `_resolve_editor(widget)` 解析目标
    （蜜算没有 `editor`，但它自己实现了 `undo/redo` → 直接把视图给它），
    所以对实例属性打桩能被观察到。
    """
    from PySide6.QtTest import QTest

    from beeoffice.plugins.beesheet import BeeSheetView

    app.show()
    qtbot.waitExposed(app)

    sheet = BeeSheetView()
    qtbot.addWidget(sheet)
    app.tab_manager.addTab(sheet, "蜜算")
    app.tab_manager.setCurrentWidget(sheet)
    sheet.show()
    qtbot.waitExposed(sheet)

    undone, redone = [], []
    sheet.undo = lambda: undone.append(1)
    sheet.redo = lambda: redone.append(1)

    sheet.table_view.setFocus()
    qtbot.wait(80)
    QTest.keyClick(sheet.table_view, Qt.Key.Key_Z,
                   Qt.KeyboardModifier.ControlModifier)
    qtbot.wait(50)
    QTest.keyClick(sheet.table_view, Qt.Key.Key_Y,
                   Qt.KeyboardModifier.ControlModifier)
    qtbot.wait(50)

    assert undone, "Ctrl+Z 没有调到蜜算视图的 undo（同键歧义？）"
    assert redone, "Ctrl+Y 没有调到蜜算视图的 redo（同键歧义？）"
    sheet.close()


def test_sheet_no_longer_registers_undo_shortcut(qtbot):
    """蜜算不再自己注册 Ctrl+Z/Ctrl+Y（避免与菜单同键歧义）。"""
    from beeoffice.plugins.beesheet import BeeSheetView

    sheet = BeeSheetView()
    qtbot.addWidget(sheet)
    try:
        assert _shortcut_count(sheet, "Ctrl+Z") == 0
        assert _shortcut_count(sheet, "Ctrl+Y") == 0
    finally:
        sheet.close()


def test_beewrite_no_longer_registers_ctrl_s(qtbot):
    """蜜写不再自己注册 Ctrl+S（菜单的窗口级动作是唯一来源）。"""
    from beeoffice.plugins.beewrite import BeeWriteEditor

    editor = BeeWriteEditor()
    qtbot.addWidget(editor)
    try:
        assert _shortcut_count(editor, "Ctrl+S") == 0
        # Ctrl+B/I/U 与菜单无冲突，应当保留
        assert _shortcut_count(editor, "Ctrl+B") == 1
    finally:
        editor.close()


def test_resolve_editor_supports_view_level_undo():
    """`_resolve_editor` 认"自己实现了 undo/redo 的视图"（蜜算就是这种）。"""
    from beeoffice.menus import _resolve_editor

    class _View:
        def undo(self):
            pass

        def redo(self):
            pass

    view = _View()
    assert _resolve_editor(view) is view

    class _Plain:
        pass

    assert _resolve_editor(_Plain()) is None
    assert _resolve_editor(None) is None


# ==================== 3. editor 属性指向"看得见"的那个 ====================

def test_editor_property_follows_active_mode(qtbot):
    """
    `editor` 原先恒返回 `markdown_editor` → 所见即所得模式下点"撤销"
    操作的是**隐藏**的源码编辑器（用户看不到任何变化）。
    """
    from beeoffice.plugins.beewrite import BeeWriteEditor

    editor = BeeWriteEditor()
    qtbot.addWidget(editor)
    try:
        assert editor.editor is editor.markdown_editor
        editor._switch_mode("rich_text")
        assert editor.editor is editor.rich_editor, (
            "rich_text 模式下 editor 应指向富文本编辑器（否则撤销/查找都打空）"
        )
        editor._switch_mode("markdown")
        assert editor.editor is editor.markdown_editor
    finally:
        editor.close()


def test_editor_property_matches_get_active_editor(qtbot):
    """`editor` 与 `_get_active_editor()` 必须一致（插件侧一直用的是后者）。"""
    from beeoffice.plugins.beewrite import BeeWriteEditor

    editor = BeeWriteEditor()
    qtbot.addWidget(editor)
    try:
        for mode in ("markdown", "rich_text"):
            editor._switch_mode(mode)
            assert editor.editor is editor._get_active_editor(), mode
    finally:
        editor.close()
