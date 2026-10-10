# tests/test_p0_regression/test_p0_01_beesheet_imports.py
"""
P0-1 回归：蜜算「排序」「查找替换」不应因缺导入而 NameError。

背景：
  原 beesheet.py 顶部 import 漏了 QFormLayout 和 QCheckBox，
  导致 _show_sort_dialog / _show_find_replace 被点击时抛：
      NameError: name 'QFormLayout' is not defined
      NameError: name 'QCheckBox' is not defined
  这是"点击即崩溃"的 P0 缺陷。

修复：
  在 from PySide6.QtWidgets import (...) 中补齐这两个类。

测试策略：
  1. 模块级断言：beesheet.py 命名空间里存在 QFormLayout / QCheckBox
     —— 防止未来重构 import 块时再次漏掉
  2. 行为级断言：调用 _show_sort_dialog / _show_find_replace，
     monkeypatch QDialog.exec 立即返回，验证无 NameError
"""
import pytest


def test_beesheet_module_exposes_required_imports():
    """P0-1：beesheet.py 应已导入 QFormLayout / QCheckBox。"""
    import beeoffice.plugins.beesheet as module

    assert hasattr(module, "QFormLayout"), (
        "P0-1：beesheet.py 未导入 QFormLayout。"
        "_show_sort_dialog / _show_find_replace 会 NameError"
    )
    assert hasattr(module, "QCheckBox"), (
        "P0-1：beesheet.py 未导入 QCheckBox。"
        "_show_sort_dialog / _show_find_replace 会 NameError"
    )

    # 顺带确认这两个是 Qt 真正的类（不是同名占位）
    from PySide6.QtWidgets import (
        QFormLayout as _QFormLayout,
        QCheckBox as _QCheckBox,
    )
    assert module.QFormLayout is _QFormLayout
    assert module.QCheckBox is _QCheckBox


@pytest.fixture
def beesheet_view(qtbot):
    """构造一个最小可用的 BeeSheetView。"""
    from beeoffice.plugins.beesheet import BeeSheetView
    view = BeeSheetView()
    qtbot.addWidget(view)
    return view


def test_show_sort_dialog_no_nameerror(beesheet_view, monkeypatch):
    """P0-1：_show_sort_dialog 不应抛 NameError。"""
    from PySide6.QtWidgets import QDialog

    # 让 QDialog.exec 立即返回（避免真的弹窗阻塞测试）
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)

    # 应正常返回，不抛 NameError
    beesheet_view._show_sort_dialog()


def test_show_find_replace_no_nameerror(beesheet_view, monkeypatch):
    """P0-1：_show_find_replace 不应抛 NameError。"""
    from PySide6.QtWidgets import QDialog

    monkeypatch.setattr(QDialog, "exec", lambda self: 0)

    beesheet_view._show_find_replace()