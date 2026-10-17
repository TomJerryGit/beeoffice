# optimize_tests.py
"""
一次性添加 5 个测试文件（幂等：已存在则跳过）。

用法:
    python optimize_tests.py            # 执行
    python optimize_tests.py --dry-run  # 只看会做什么
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
DRY = "--dry-run" in sys.argv

FILES = {}


FILES["tests/regression/p0/test_p0_08_beeshow_plugin.py"] = '''# tests/regression/p0/test_p0_08_beeshow_plugin.py
"""
P0-8 回归：beeshow_plugin.play_show 删死代码，直接调用 _start_play

背景：
  原 play_show 在调用 _start_play 前，检查：
    hasattr(view, "current_index")
    hasattr(view, "show_slide")
  但 BeeShowView 实际属性/方法是 _current_slide 和 _show_slide，
  这两个 hasattr 恒为 False，是纯误导性代码。

  且 _start_play 内部已执行 self._current_slide = 0，
  无需在插件层做任何重置。

修复：
  play_show 删除死代码，直接调 view._start_play()

测试策略：
  1. 结构断言：源码里不再有 current_index / show_slide
  2. 行为断言：mock view._start_play，调用 plugin.play_show，验证被调用
"""
import inspect


def test_play_show_has_no_dead_code():
    """P0-8：beeshow_plugin 源码不应含 current_index / show_slide。"""
    from beeoffice.plugins import beeshow_plugin
    source = inspect.getsource(beeshow_plugin)
    assert "current_index" not in source, (
        "P0-8：beeshow_plugin 里出现了 current_index，应改为 _current_slide"
    )
    assert "show_slide" not in source, (
        "P0-8：beeshow_plugin 里出现了 show_slide，应改为 _show_slide"
    )


def test_play_show_calls_start_play(qtbot, monkeypatch):
    """P0-8：plugin.play_show 应实际调用 view._start_play。"""
    from beeoffice.plugins.beeshow import BeeShowView
    from beeoffice.plugins.beeshow_plugin import BeeShowPlugin

    view = BeeShowView()
    qtbot.addWidget(view)

    called = []
    monkeypatch.setattr(
        view, "_start_play",
        lambda: called.append("_start_play"),
    )

    class _FakeTabManager:
        def currentWidget(self):
            return view

    class _FakeParent:
        def __init__(self):
            self.tab_manager = _FakeTabManager()

    plugin = BeeShowPlugin(parent=_FakeParent())
    plugin.play_show()

    assert called == ["_start_play"], (
        "P0-8：play_show 未调用 view._start_play。"
        "可能死代码被恢复了"
    )


def test_play_show_warns_when_no_view(monkeypatch):
    """P0-8：无活动蜜演视图时应提示。"""
    from beeoffice.plugins.beeshow_plugin import BeeShowPlugin

    warned = []
    monkeypatch.setattr(
        BeeShowPlugin, "_warn",
        lambda self, msg: warned.append(msg),
    )

    class _FakeTabManager:
        def currentWidget(self):
            return None

    class _FakeParent:
        def __init__(self):
            self.tab_manager = _FakeTabManager()

    plugin = BeeShowPlugin(parent=_FakeParent())
    plugin.play_show()

    assert warned, "无视图时应调用 _warn()"
    assert "蜜演" in warned[0]
'''


FILES["tests/regression/p1/test_p1_11_spelling.py"] = '''# tests/regression/p1/test_p1_11_spelling.py
"""
P1-11 回归：beewrite_* 文件头注释拼写正确

背景：
  10 个 beewrite_* 文件的头注释把 "beewrite_" 拼成了 "bewrite_"，
  少一个 e。虽然不影响运行，但容易误导搜索。

修复：
  文件头注释统一为正确的 "beewrite_"。

测试策略：
  1. 静态扫描 beewrite_*.py，检查 docstring 里没有 "bewrite_"
  2. 磁盘上不存在 bewrite_*.py 文件
"""
import re
from pathlib import Path


PLUGINS_DIR = (
    Path(__file__).parent.parent.parent.parent
    / "beeoffice" / "plugins"
)


def test_no_bewrite_typo_in_docstrings():
    """P1-11：beewrite_*.py 的 docstring 不应出现 bewrite_（少一个 e）。"""
    files = sorted(PLUGINS_DIR.glob("beewrite_*.py"))
    assert files, f"未找到 beewrite_*.py，目录: {PLUGINS_DIR}"

    problems = []
    for f in files:
        text = f.read_text(encoding="utf-8")
        for m in re.finditer(r"(?<!b)bewrite_", text):
            line_no = text[:m.start()].count("\\n") + 1
            problems.append(f"{f.name}:{line_no}")

    assert not problems, (
        "P1-11：以下位置有 bewrite_ 拼写错误：\\n"
        + "\\n".join(f"  {p}" for p in problems)
    )


def test_no_bewrite_files_on_disk():
    """P1-11：磁盘上不应存在 bewrite_*.py（拼错的文件名）。"""
    wrong = list(PLUGINS_DIR.glob("bewrite_*.py"))
    assert not wrong, (
        "P1-11：发现拼写错误的文件：\\n"
        + "\\n".join(f"  {f.name}" for f in wrong)
    )
'''


FILES["tests/qt/test_tab_manager_extra.py"] = '''# tests/qt/test_tab_manager_extra.py
"""
TabManager 补充测试：未保存标记 / 重命名 / 复制路径 / 初始内容
覆盖原 test_tab_manager.py 未覆盖的路径。
"""
from PySide6.QtWidgets import QPlainTextEdit, QWidget, QApplication


class TestUnsavedMark:
    def test_mark_unsaved_adds_dot(self, qtbot):
        from beeoffice.tab_manager import TabManager
        tm = TabManager()
        qtbot.addWidget(tm)
        w = QPlainTextEdit()
        tm.addTab(w, "test")
        tm._mark_unsaved(w)
        idx = tm.indexOf(w)
        assert tm.tabText(idx).startswith("● ")

    def test_mark_saved_removes_dot(self, qtbot):
        from beeoffice.tab_manager import TabManager
        tm = TabManager()
        qtbot.addWidget(tm)
        w = QPlainTextEdit()
        tm.addTab(w, "test")
        tm._mark_unsaved(w)
        tm._mark_saved(w)
        idx = tm.indexOf(w)
        assert not tm.tabText(idx).startswith("● ")

    def test_mark_saved_idempotent(self, qtbot):
        from beeoffice.tab_manager import TabManager
        tm = TabManager()
        qtbot.addWidget(tm)
        w = QPlainTextEdit()
        tm.addTab(w, "test")
        tm._mark_saved(w)
        tm._mark_saved(w)
        idx = tm.indexOf(w)
        assert tm.tabText(idx) == "test"


class TestRenameTab:
    def test_rename_keeps_unsaved_prefix(self, qtbot, monkeypatch):
        from beeoffice.tab_manager import TabManager
        from PySide6.QtWidgets import QInputDialog

        tm = TabManager()
        qtbot.addWidget(tm)
        w = QPlainTextEdit()
        tm.addTab(w, "old")
        tm._mark_unsaved(w)

        monkeypatch.setattr(
            QInputDialog, "getText",
            staticmethod(lambda *a, **k: ("new", True)),
        )
        idx = tm.indexOf(w)
        tm._rename_tab(idx)

        text = tm.tabText(idx)
        assert text.startswith("● ")
        assert "new" in text


class TestCopyFilePath:
    def test_copy_path_to_clipboard(self, qtbot, tmp_path):
        from beeoffice.tab_manager import TabManager
        tm = TabManager()
        qtbot.addWidget(tm)
        w = QPlainTextEdit()
        tm.addTab(w, "doc")
        path = str(tmp_path / "doc.md")
        tm.set_tab_file_path(w, path)
        idx = tm.indexOf(w)
        tm._copy_file_path(idx)
        assert QApplication.clipboard().text() == path

    def test_copy_path_no_path(self, qtbot):
        from beeoffice.tab_manager import TabManager
        tm = TabManager()
        qtbot.addWidget(tm)
        w = QPlainTextEdit()
        tm.addTab(w, "no-path")
        before = QApplication.clipboard().text()
        idx = tm.indexOf(w)
        tm._copy_file_path(idx)
        after = QApplication.clipboard().text()
        assert before == after


class TestInitialContent:
    def test_qplaintextedit_records_content(self, qtbot):
        from beeoffice.tab_manager import TabManager
        tm = TabManager()
        qtbot.addWidget(tm)
        w = QPlainTextEdit()
        w.setPlainText("hello")
        tm.addTab(w, "t")
        assert tm._tab_initial_content[id(w)] == "hello"

    def test_qwidget_marked_none(self, qtbot):
        from beeoffice.tab_manager import TabManager
        tm = TabManager()
        qtbot.addWidget(tm)
        w = QWidget()
        tm.addTab(w, "t")
        assert tm._tab_initial_content[id(w)] is None
'''


FILES["tests/unit/test_plugin_manager.py"] = '''# tests/unit/test_plugin_manager.py
"""PluginManager 单元测试：查询 / 卸载 / 关闭"""


class _FakePlugin:
    name = "Fake"
    version = "0.0"
    description = "fake"
    author = "test"

    def __init__(self, parent=None):
        self.parent = parent
        self._enabled = True

    def is_enabled(self):
        return self._enabled

    def set_enabled(self, v):
        self._enabled = bool(v)

    def on_close(self):
        pass

    def on_load(self):
        pass


def test_manager_init_empty():
    from beeoffice.plugin_manager import PluginManager
    pm = PluginManager()
    assert pm.plugins == []
    assert pm.plugin_info == []
    assert pm.count() == 0


def test_get_plugin_by_name_missing():
    from beeoffice.plugin_manager import PluginManager
    pm = PluginManager()
    assert pm.get_plugin_by_name("不存在") is None


def test_get_plugin_info_by_name_missing():
    from beeoffice.plugin_manager import PluginManager
    pm = PluginManager()
    assert pm.get_plugin_info_by_name("不存在") is None


def test_get_enabled_plugins_empty():
    from beeoffice.plugin_manager import PluginManager
    pm = PluginManager()
    assert pm.get_enabled_plugins() == []


def test_unload_plugin_not_found():
    from beeoffice.plugin_manager import PluginManager
    pm = PluginManager()
    assert pm.unload_plugin("不存在") is False


def test_unload_plugin_success():
    from beeoffice.plugin_manager import PluginManager
    pm = PluginManager()
    p = _FakePlugin()
    pm.plugins.append(p)
    pm.plugin_info.append({
        "name": p.name, "version": p.version,
        "description": p.description, "author": p.author,
        "enabled": True, "instance": p,
    })
    assert pm.unload_plugin(p.name) is True
    assert pm.count() == 0


def test_close_all_does_not_crash():
    from beeoffice.plugin_manager import PluginManager
    pm = PluginManager()
    p = _FakePlugin()
    pm.plugins.append(p)
    pm.close_all()
    assert pm.count() == 1


def test_get_plugin_by_name_found():
    from beeoffice.plugin_manager import PluginManager
    pm = PluginManager()
    p = _FakePlugin()
    pm.plugins.append(p)
    assert pm.get_plugin_by_name(p.name) is p


def test_get_plugin_info_by_name_found():
    from beeoffice.plugin_manager import PluginManager
    pm = PluginManager()
    p = _FakePlugin()
    info = {"name": p.name, "version": p.version,
            "description": p.description, "author": p.author,
            "enabled": True, "instance": p}
    pm.plugin_info.append(info)
    assert pm.get_plugin_info_by_name(p.name) is info


def test_repr():
    from beeoffice.plugin_manager import PluginManager
    pm = PluginManager()
    assert "PluginManager" in repr(pm)
'''


FILES["tests/unit/test_cloud_factory.py"] = '''# tests/unit/test_cloud_factory.py
"""cloud.py 云存储工厂单例测试"""
import pytest


def _reset():
    from beeoffice import cloud
    cloud._cloud_storage_instance = None
    cloud._cloud_storage_signature = None


def _make_settings_class(**kwargs):
    class _Settings:
        pass
    for k, v in kwargs.items():
        setattr(_Settings, k, v)
    return _Settings


def test_disabled_returns_none(monkeypatch):
    from beeoffice import cloud
    _reset()
    monkeypatch.setattr(cloud, "AppSettings",
                        _make_settings_class(
                            cloud_enabled=False,
                            cloud_type="webdav",
                            cloud_config={}))
    assert cloud.get_cloud_storage() is None


def test_empty_config_returns_none(monkeypatch):
    from beeoffice import cloud
    _reset()
    monkeypatch.setattr(cloud, "AppSettings",
                        _make_settings_class(
                            cloud_enabled=True,
                            cloud_type="webdav",
                            cloud_config={}))
    assert cloud.get_cloud_storage() is None


def test_unknown_type_returns_none(monkeypatch):
    from beeoffice import cloud
    _reset()
    monkeypatch.setattr(cloud, "AppSettings",
                        _make_settings_class(
                            cloud_enabled=True,
                            cloud_type="unknown",
                            cloud_config={"k": "v"}))
    assert cloud.get_cloud_storage() is None


def test_webdav_config_creates_instance(monkeypatch):
    from beeoffice import cloud
    _reset()
    monkeypatch.setattr(cloud, "AppSettings",
                        _make_settings_class(
                            cloud_enabled=True,
                            cloud_type="webdav",
                            cloud_config={
                                "url": "https://a.com/dav",
                                "username": "u",
                                "password": "p",
                            }))
    a = cloud.get_cloud_storage()
    assert a is not None
    assert a.name == "WebDAV"
    # 单例：第二次相同配置返回同一个
    assert cloud.get_cloud_storage() is a


def test_config_change_recreates(monkeypatch):
    from beeoffice import cloud
    _reset()
    monkeypatch.setattr(cloud, "AppSettings",
                        _make_settings_class(
                            cloud_enabled=True,
                            cloud_type="webdav",
                            cloud_config={
                                "url": "https://a.com",
                                "username": "u",
                                "password": "p",
                            }))
    a = cloud.get_cloud_storage()

    monkeypatch.setattr(cloud, "AppSettings",
                        _make_settings_class(
                            cloud_enabled=True,
                            cloud_type="webdav",
                            cloud_config={
                                "url": "https://b.com",
                                "username": "u",
                                "password": "p",
                            }))
    b = cloud.get_cloud_storage()
    assert a is not b, "配置变化后应重建实例"


def test_reset_clears_singleton(monkeypatch):
    from beeoffice import cloud
    _reset()
    monkeypatch.setattr(cloud, "AppSettings",
                        _make_settings_class(
                            cloud_enabled=True,
                            cloud_type="webdav",
                            cloud_config={
                                "url": "https://x.com",
                                "username": "u",
                                "password": "p",
                            }))
    a = cloud.get_cloud_storage()
    assert a is not None

    cloud.reset_cloud_storage()
    assert cloud._cloud_storage_instance is None
    assert cloud._cloud_storage_signature is None
'''


def main():
    print("=" * 60)
    print(f"  优化：添加 5 个测试文件  {'[DRY-RUN]' if DRY else ''}")
    print("=" * 60)
    print()

    created = 0
    skipped = 0
    failed = 0
    for rel, content in sorted(FILES.items()):
        target = ROOT / rel
        if target.exists():
            print(f"  [SKIP] {rel} (已存在)")
            skipped += 1
            continue
        if not DRY:
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            except Exception as e:
                print(f"  [FAIL] {rel}: {e}")
                failed += 1
                continue
        print(f"  [CREATE] {rel}")
        created += 1

    print()
    print("=" * 60)
    if DRY:
        print(f"  DRY-RUN: 将创建 {created} 个，跳过 {skipped} 个")
    else:
        print(f"  ✅ 创建 {created} 个，跳过 {skipped} 个，失败 {failed} 个")
        print()
        print("  下一步:")
        print("    1. pytest tests/regression/p0/test_p0_08_beeshow_plugin.py -v")
        print("    2. pytest tests/regression/p1/test_p1_11_spelling.py -v")
        print("    3. pytest tests/qt/test_tab_manager_extra.py -v")
        print("    4. pytest tests/unit/test_plugin_manager.py -v")
        print("    5. pytest tests/unit/test_cloud_factory.py -v")
        print("    6. run_tests.bat")
    print("=" * 60)


if __name__ == "__main__":
    main()