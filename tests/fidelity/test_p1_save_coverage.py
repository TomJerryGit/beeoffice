# tests/fidelity/test_p1_save_coverage.py
"""
P1 + P0 收尾：让**蜜算与蜜演都有"当前文件 + 保存"**，从而被
平台级的「保存前备份 / 5 分钟自动保存 / Ctrl+S / 未保存提示」覆盖。

## 背景（审计报告 §2.6 / §2.7）
* 蜜算原先**从不设置** `_current_file_path`、也没有 `save()` →
  自动保存跳过它、保存前备份不覆盖它（手动点还弹"还没有保存到文件"）、
  Ctrl+S 每次都弹另存对话框（没有"当前文件"概念，与 Excel/WPS 不符）。
* 蜜演**整条保存链路不存在**（`def save`/`save_as` 全为 0）→
  Ctrl+S 毫无反应，而导出件（PPTX/PDF/HTML）**回不到编辑器** →
  做好的稿子关掉就改不了。这是全审计里唯一的"数据丢失级"问题。

## 本轮的修法
* 蜜算：抽出 `_write_xlsx()` 供"导出/保存/另存"共用；新增
  `save()`/`save_as()`/`set_current_file_path()`；导入后记住路径。
* 蜜演：新增 `beeshow_doc.py`（**纯逻辑、不依赖 Qt**）定义 `.beshow` 格式
  （内容是 Markdown + 一行注释标记 + **原子写**），视图侧接
  `save()`/`save_as()`/`open_deck()`；app 增加 `.beshow` 打开路由。
* **自动保存守卫**：必须有 `_current_file_path` 才自动保存 ——
  否则蜜算/蜜演第一次自动保存就会弹"另存为"对话框（每 5 分钟一次是灾难）。

## 环境限制
`BeeShowView` 在本沙箱**无法实例化**（QtWebEngine 初始化 FATAL），
所以蜜演这部分：格式逻辑走**纯模块**做完整测试，视图侧只做**类级**校验。
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from beeoffice.plugins import beeshow_doc                               # noqa: E402


# ==================== 1. `.beshow` 格式（纯逻辑，完整测试）====================

DECK = "# 第一页\n\n内容一\n\n---\n\n# 第二页\n\n内容二"


def test_serialize_adds_marker_and_is_idempotent():
    once = beeshow_doc.serialize(DECK)
    twice = beeshow_doc.serialize(once)

    assert beeshow_doc.has_marker(once)
    assert once == twice, "重复保存不应叠加标记"
    assert beeshow_doc.serialize(DECK).count(beeshow_doc.DECK_MARKER) == 1


def test_marker_roundtrip_preserves_content_exactly():
    """写完再读，内容必须**逐字一致**（否则"保存"本身就在改用户内容）。"""
    assert beeshow_doc.strip_marker(beeshow_doc.serialize(DECK)) == DECK


def test_save_and_load_roundtrip(tmp_path):
    target = tmp_path / "演示.beshow"

    assert beeshow_doc.save_deck(target, DECK) is True
    assert target.exists()
    assert beeshow_doc.load_deck(target) == DECK


def test_save_is_atomic_no_tmp_left(tmp_path):
    target = tmp_path / "演示.beshow"

    beeshow_doc.save_deck(target, DECK)

    assert not list(tmp_path.glob("*.tmp")), "保存后留下了临时文件"


def test_load_is_lenient_for_plain_markdown(tmp_path):
    """没有标记的普通 Markdown 也要能读（否则"以前存的打不开"）。"""
    plain = tmp_path / "old.md"
    plain.write_text(DECK, encoding="utf-8")

    assert beeshow_doc.load_deck(plain) == DECK


def test_load_reports_failure_instead_of_empty_deck(tmp_path):
    """读不到就返回 None（调用方提示），**不能静默变成空文稿**。"""
    assert beeshow_doc.load_deck(tmp_path / "不存在.beshow") is None


def test_extension_detection_and_name_suggestion():
    assert beeshow_doc.is_deck_file("a.beshow")
    assert beeshow_doc.is_deck_file("A.BESHOW")
    assert not beeshow_doc.is_deck_file("a.md")

    name = beeshow_doc.suggested_filename("# 季度汇报\n第二行")
    assert name == "季度汇报.beshow", name

    # 非法字符要清掉（Windows 上否则直接写失败）
    assert "/" not in beeshow_doc.suggested_filename("a/b:c*d")
    assert beeshow_doc.suggested_filename("") == "未命名演示.beshow"


def test_save_reports_failure_when_target_is_a_directory(tmp_path):
    """写失败必须返回 False（调用方据此提示，不能假装成功）。"""
    assert beeshow_doc.save_deck(tmp_path, DECK) is False


# ==================== 2. 蜜算：当前文件 + 保存 ====================

def test_sheet_save_writes_to_current_file_without_dialog(qtbot, tmp_path,
                                                          monkeypatch):
    """保存到当前文件时**不该**再弹"另存为"对话框。"""
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from beeoffice.plugins.beesheet import BeeSheetView

    view = BeeSheetView()
    qtbot.addWidget(view)
    try:
        monkeypatch.setattr(QMessageBox, "information",
                            staticmethod(lambda *a, **k: None))
        monkeypatch.setattr(QMessageBox, "warning",
                            staticmethod(lambda *a, **k: None))

        def _no_dialog(*args, **kwargs):
            raise AssertionError("保存到当前文件时不该弹另存对话框")

        monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(_no_dialog))

        target = tmp_path / "表格.xlsx"
        view.model.set_full_dataframe(pd.DataFrame({"a": [3, 1, 2]}))
        view.set_current_file_path(target)
        view.model.setData(view.model.index(0, 0), 99,
                           __import__("PySide6.QtCore", fromlist=["Qt"])
                           .Qt.ItemDataRole.EditRole)

        assert view.save() is True
        assert target.exists()
        assert pd.read_excel(target).iloc[0, 0] == 99
        assert Path(view._current_file_path) == target
    finally:
        view.close()


def test_sheet_save_without_path_falls_back_to_save_as(qtbot, monkeypatch):
    """没有当前文件时退化为"另存为"（不能静默丢弃用户的保存请求）。"""
    from beeoffice.plugins.beesheet import BeeSheetView

    view = BeeSheetView()
    qtbot.addWidget(view)
    try:
        called = []
        monkeypatch.setattr(view, "_export_xlsx", lambda: called.append(1))

        assert view.save() is False          # 没有路径、也没真的存成功
        assert called, "没有当前文件时应当走『另存为』"
    finally:
        view.close()


def test_sheet_import_remembers_path(qtbot, tmp_path):
    """导入一个真实 xlsx 后必须记住路径（否则备份/自动保存都不覆盖它）。"""
    from beeoffice.plugins.beesheet import BeeSheetView

    source = tmp_path / "导入.xlsx"
    pd.DataFrame({"a": [1, 2, 3]}).to_excel(source, index=False)

    view = BeeSheetView()
    qtbot.addWidget(view)
    try:
        view._import_file_from_path(str(source))
        assert getattr(view, "_current_file_path", None), (
            "导入后没有记住当前文件 → Ctrl+S/自动保存/备份对蜜算全部失效"
        )
        assert Path(view._current_file_path) == source
    finally:
        view.close()


# ==================== 3. 蜜演：接口与路由（类级，见文件头环境限制）======

def test_beeshow_exposes_save_interface():
    from beeoffice.plugins.beeshow import BeeShowView

    for name in ("save", "save_as", "open_deck", "set_current_file_path",
                 "content"):
        assert callable(getattr(BeeShowView, name, None)), (
            f"BeeShowView 缺少 {name} → 蜜演仍然无法保存"
        )


def test_app_routes_beshow_extension():
    """`.beshow` 必须被 app 认识并路由到蜜演（否则存了也打不开）。"""
    from beeoffice import app as app_module

    assert ".beshow" in app_module.SHOW_EXTENSIONS
    assert callable(getattr(app_module.BeeApp, "_open_show_file", None))


def test_open_dialog_filter_mentions_beshow():
    """打开对话框里要能看到蜜演文稿类型（否则用户不知道该开什么文件）。"""
    import inspect

    from beeoffice import tab_manager

    source = inspect.getsource(tab_manager.TabManager.open_file)
    assert "beshow" in source, "打开对话框的过滤器里没有 .beshow"


# ==================== 4. 备份与自动保存的覆盖面 ====================

def test_backup_before_save_covers_sheet_with_path(tmp_path, monkeypatch):
    """蜜算一旦有当前文件，保存前的自动备份就该覆盖它。"""
    from beeoffice.app import BeeApp
    from beeoffice.backup import BackupStore

    class _FakeApp:
        def __init__(self, store):
            self._backup_store_cache = store

        def _backup_store(self):
            return self._backup_store_cache

    store = BackupStore(root=tmp_path / "bk")
    app = _FakeApp(store)

    source = tmp_path / "表格.xlsx"
    source.write_text("x", encoding="utf-8")

    class _Widget:
        _current_file_path = str(source)

    created = BeeApp._backup_before_save(app, _Widget())
    assert created is True
    assert len(store.list_versions(source)) == 1


def test_autosave_skips_widgets_without_current_file(qtbot, app, monkeypatch):
    """
    **自动保存守卫**：没有当前文件的标签**不该**被自动保存 ——
    它的 `save()` 会退化成"另存为"，每 5 分钟弹一次对话框是灾难。
    """
    from PySide6.QtWidgets import QWidget

    class _FakeWidget(QWidget):
        def __init__(self):
            super().__init__()
            self._editor = type("E", (), {"toPlainText": lambda self: "改动"})()
            self.saved = []

        def content(self):
            return "改动"

        def save(self):
            self.saved.append(1)
            return True

    widget = _FakeWidget()
    qtbot.addWidget(widget)
    app.tab_manager.addTab(widget, "无路径")
    app.tab_manager.setCurrentWidget(widget)

    widget.saved.clear()
    app._autosave()

    assert not widget.saved, "没有当前文件却触发了自动保存（会弹另存对话框）"
    widget.close()


def test_autosave_saves_widgets_with_current_file(qtbot, app, tmp_path):
    """有当前文件时，自动保存应当真的写回。"""
    from PySide6.QtWidgets import QMessageBox

    monkeypatch_dummy = None
    _ = monkeypatch_dummy

    from PySide6.QtWidgets import QWidget as _QWidget

    class _FakeWidget(_QWidget):
        def __init__(self, path):
            super().__init__()
            self._current_file_path = str(path)
            self.saved = []
            self._text = "初始内容"

        def content(self):
            return self._text

        def save(self):
            self.saved.append(1)
            return True

    target = tmp_path / "有路径.xlsx"
    target.write_text("x", encoding="utf-8")
    widget = _FakeWidget(target)
    qtbot.addWidget(widget)
    app.tab_manager.addTab(widget, "有路径")     # ← addTab 会记下 "初始内容"
    app.tab_manager.setCurrentWidget(widget)
    QMessageBox.information = staticmethod(lambda *a, **k: None)

    widget._text = "改过之后的内容"               # ← 制造真实改动
    widget.saved.clear()
    app._autosave()

    assert widget.saved, "有当前文件却没有自动保存"
    widget.close()
