# -*- coding: utf-8 -*-
"""
同步范围（阶段三 #6）

背景：
    文档同步原本固定为"已打开 + 最近文档"，用户无法选择。
    想只备份当前文档时没有入口；最近列表很长时首次同步会传很多文件。

实现：
    · 设置项 `cloud_sync_scope`：`recent`（默认）/ `current`
    · 云存储设置对话框提供下拉框
    · `collect_documents(window, scope)` 按范围收集

一个关键设计决定：
    同步范围是**独立偏好**，保存时不走连接配置校验。
    否则用户只改范围、地址没填时，`_save` 会整体 return，改了等于没改。
"""
import pytest

pytest.importorskip("PySide6.QtWidgets")

from beeoffice.document_sync import collect_documents  # noqa: E402


# ==================== 文档收集 ====================
class _Tab:
    def __init__(self, path):
        self._current_file_path = path


class _Tabs:
    def __init__(self, paths, current_index=0):
        self._tabs = [_Tab(p) for p in paths]
        self._current = current_index

    def count(self):
        return len(self._tabs)

    def widget(self, i):
        return self._tabs[i]

    def currentWidget(self):
        return self._tabs[self._current] if self._tabs else None


class _Settings:
    def __init__(self, recent):
        self.recent_files = recent


class _Window:
    def __init__(self, open_paths, recent, current_index=0):
        self.tab_manager = _Tabs(open_paths, current_index)
        self.settings = _Settings(recent)


@pytest.fixture
def docs(tmp_path):
    a = tmp_path / "a.md"; a.write_text("a", encoding="utf-8")
    b = tmp_path / "b.md"; b.write_text("b", encoding="utf-8")
    c = tmp_path / "c.md"; c.write_text("c", encoding="utf-8")
    # 当前标签是第 2 个（b.md）
    return _Window([str(a), str(b)], [str(c), str(a)], current_index=1)


def test_scope_current_returns_only_active_document(docs):
    got = collect_documents(docs, scope="current")
    assert [p.name for p in got] == ["b.md"]


def test_scope_recent_includes_open_and_recent(docs):
    got = [p.name for p in collect_documents(docs, scope="recent")]
    assert got == ["a.md", "b.md", "c.md"]


def test_unknown_scope_falls_back_to_recent(docs):
    got = [p.name for p in collect_documents(docs, scope="whatever")]
    assert got == ["a.md", "b.md", "c.md"]


def test_scope_current_without_open_file(tmp_path):
    w = _Window([None], [])          # 当前标签是欢迎页
    assert collect_documents(w, scope="current") == []


# ==================== 设置持久化 ====================
def test_settings_roundtrip_scope(tmp_path):
    from beeoffice.settings import AppSettings

    import json

    path = tmp_path / "s.json"
    s = AppSettings()
    s.path = path
    # 注意：不在这里断言"默认值"，因为 AppSettings() 构造时会读取真实用户的
    # 设置文件，默认值可能已被历史配置覆盖。这里只验证"写进去、读得回"。
    s.cloud_sync_scope = "current"
    assert s.save() is True
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved.get("cloud_sync_scope") == "current"

    s2 = AppSettings()
    s2.path = path
    s2.load()
    assert s2.cloud_sync_scope == "current"


# ==================== 对话框 ====================
def test_dialog_exposes_scope_combo(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from beeoffice.cloud_settings import CloudSettingsDialog

    for name in ("warning", "information", "critical", "question"):
        monkeypatch.setattr(
            QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok)
        )

    dlg = CloudSettingsDialog()
    qtbot.addWidget(dlg)

    assert dlg.scope_combo.count() == 2
    assert dlg.scope_combo.currentData() in ("recent", "current")
    assert dlg.scope_combo.findData("current") >= 0


def test_scope_saved_even_when_connection_invalid(qtbot, monkeypatch):
    """
    只改同步范围、连接信息不完整时，范围也必须保存成功。

    这正是重构前的问题：`_save` 校验失败会整体 return，偏好白改。
    """
    from PySide6.QtWidgets import QMessageBox

    from beeoffice.cloud_settings import CloudSettingsDialog

    for name in ("warning", "information", "critical", "question"):
        monkeypatch.setattr(
            QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok)
        )

    dlg = CloudSettingsDialog()
    qtbot_add = qtbot.addWidget
    qtbot_add(dlg)

    dlg.url_edit.setText("")                     # 故意留空，触发校验失败
    dlg.scope_combo.setCurrentIndex(dlg.scope_combo.findData("current"))
    dlg._save()

    assert dlg.settings.cloud_sync_scope == "current"
