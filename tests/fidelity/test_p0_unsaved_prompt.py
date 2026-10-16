# tests/fidelity/test_p0_unsaved_prompt.py
"""
P0 修复：蜜算/蜜演**关标签时提示未保存**（止损版）。

## 背景（实测/审计）
`tab_manager._on_tab_close_request` 靠 `widget.content()` 判断"内容变没变"；
而 `BeeSheetView` 与 `BeeShowView` **原先都没有 `content()`** →
`initial_content` 被记为 `None` → **直接关闭、不弹确认**。
后果：蜜演更严重——它**没有保存链路**（导出件是 PPTX/PDF/HTML，回不到编辑器），
关标签就等于稿子没了；蜜算的会话备份还会在 `closeEvent` 里被删掉。

## 本次修的是"能判断有没有改动"这一半（止损）
· 蜜算：`content()` 返回**轻量签名**（形状 + 内容哈希，向量化、对任何单元格改动敏感），
  并把模型信号接到 `contentChanged`；
· 蜜演：`content()` 返回编辑器里的 Markdown 源，接 `textChanged` → `contentChanged`。

## 环境限制（如实说明）
`BeeShowView` 在本沙箱**无法实例化**（QtWebEngine 初始化即
`FATAL: platform_channel.cc Check failed`），所以蜜演只能做**类级**校验；
蜜算这条做的是**真实端到端**（真控件 + 真关闭请求 + 真弹窗拦截）。
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ==================== 1. 两个视图都提供内容接口 ====================

def test_beesheet_view_exposes_content_interface():
    from beeoffice.plugins.beesheet import BeeSheetView

    assert callable(getattr(BeeSheetView, "content", None))
    assert hasattr(BeeSheetView, "contentChanged")


def test_beeshow_view_exposes_content_interface():
    """类级校验（本沙箱不能实例化 BeeShowView，见文件头说明）。"""
    from beeoffice.plugins.beeshow import BeeShowView

    assert callable(getattr(BeeShowView, "content", None))
    assert hasattr(BeeShowView, "contentChanged")


# ==================== 2. 蜜算：签名对改动敏感 + 信号会发 ====================

def test_sheet_content_signature_changes_on_edit(qtbot):
    from PySide6.QtCore import Qt

    from beeoffice.plugins.beesheet import BeeSheetView

    view = BeeSheetView()
    qtbot.addWidget(view)
    try:
        view.model.set_full_dataframe(pd.DataFrame({"a": [1, 2, 3]}))
        before = view.content()
        assert before, "content() 不该是空的（否则关标签不会提示）"

        view.model.setData(view.model.index(0, 0), 999,
                           Qt.ItemDataRole.EditRole)
        after = view.content()
        assert before != after, "改了一个单元格，内容签名却没变 → 关标签不会提示"
    finally:
        view.close()


def test_sheet_content_changed_is_emitted(qtbot):
    from PySide6.QtCore import Qt

    from beeoffice.plugins.beesheet import BeeSheetView

    view = BeeSheetView()
    qtbot.addWidget(view)
    try:
        hits = []
        view.contentChanged.connect(lambda: hits.append(1))
        view.model.set_full_dataframe(pd.DataFrame({"a": [1, 2, 3]}))
        view.model.setData(view.model.index(0, 0), 7,
                           Qt.ItemDataRole.EditRole)
        assert hits, "编辑后没有发出 contentChanged（● 未保存标记不会亮）"
    finally:
        view.close()


def test_sheet_content_is_cheap_for_large_dataframe(qtbot):
    """签名必须便宜：关标签时会调它，几十万行的表不能做 `to_csv`。"""
    import time

    from beeoffice.plugins.beesheet import BeeSheetView

    view = BeeSheetView()
    qtbot.addWidget(view)
    try:
        view.model.set_full_dataframe(
            pd.DataFrame({"a": range(50000), "b": range(50000)})
        )
        started = time.perf_counter()
        text = view.content()
        elapsed = time.perf_counter() - started
        assert text
        assert elapsed < 1.0, f"content() 用了 {elapsed:.2f}s，太慢（会影响关标签）"
    finally:
        view.close()


# ==================== 3. 端到端：关标签真的会问 ====================

def test_closing_dirty_sheet_tab_asks(qtbot, app, monkeypatch):
    """
    **核心验收**：蜜算标签改过内容后，关闭它必须**弹出确认**。

    （修复前 `content()` 不存在 → `initial_content=None` → 直接关掉，
      审计员实测"0 次弹窗"。）
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox

    from beeoffice.plugins.beesheet import BeeSheetView

    view = BeeSheetView()
    qtbot.addWidget(view)
    app.tab_manager.addTab(view, "蜜算")
    index = app.tab_manager.indexOf(view)

    asked = []

    def fake_question(*args, **kwargs):
        asked.append(args[1] if len(args) > 1 else "")
        return QMessageBox.StandardButton.No      # 选"否" → 不关

    monkeypatch.setattr(QMessageBox, "question", staticmethod(fake_question))

    # 制造一处真实改动
    view.model.set_full_dataframe(pd.DataFrame({"a": [1, 2, 3]}))
    view.model.setData(view.model.index(0, 0), 42,
                       Qt.ItemDataRole.EditRole)

    app.tab_manager._on_tab_close_request(index)

    assert asked, "关闭改过的蜜算标签没有弹确认 —— 内容会被静默丢弃"
    assert app.tab_manager.indexOf(view) != -1, "选了『否』却被关掉了"
    view.close()


def test_closing_clean_sheet_tab_does_not_ask(qtbot, app, monkeypatch):
    """没改过就不该打扰用户（不能因为修了这个就到处弹窗）。"""
    from PySide6.QtWidgets import QMessageBox

    from beeoffice.plugins.beesheet import BeeSheetView

    view = BeeSheetView()
    qtbot.addWidget(view)
    app.tab_manager.addTab(view, "蜜算")
    index = app.tab_manager.indexOf(view)

    asked = []
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: asked.append(1) or QMessageBox.Yes),
    )

    app.tab_manager._on_tab_close_request(index)

    assert not asked, "没改过的标签也弹了确认（会烦人）"
