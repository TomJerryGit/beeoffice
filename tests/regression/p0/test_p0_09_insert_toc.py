# tests/test_p0_regression/test_p0_09_insert_toc.py
"""
P0-9 回归：命令面板「插入目录」应调用 _insert_toc，而非 _generate_toc。

背景：
  BeeWriteEditor 实际方法名是 _insert_toc（插入到光标处），
  而 beeoffice/plugins/beewrite_plugin.py 的 generate_toc 一直
  检查 hasattr(editor, "_generate_toc")，恒为 False，
  导致命令面板始终提示"当前编辑器不支持生成目录"。

修复：
  plugin.generate_toc 改用 _insert_toc。

测试策略：
  1. 断言 BeeWriteEditor 有 _insert_toc（方法存在性）
  2. 断言 plugin.generate_toc 会调用 editor._insert_toc（行为）
"""


def test_beewrite_editor_has_insert_toc(qtbot):
    """P0-9：BeeWriteEditor 应提供 _insert_toc 方法。"""
    from beeoffice.plugins.beewrite import BeeWriteEditor
    editor = BeeWriteEditor()
    qtbot.addWidget(editor)

    assert hasattr(editor, "_insert_toc"), (
        "BeeWriteEditor 必须提供 _insert_toc。"
        "若方法名被重命名，需同步更新 beewrite_plugin.generate_toc"
    )
    assert callable(editor._insert_toc)


def test_plugin_generate_toc_calls_insert_toc(qtbot, monkeypatch):
    """
    P0-9：plugin.generate_toc 应实际调用 editor._insert_toc。

    如果 plugin 改回 _generate_toc（不存在的名字），
    本测试会因 editor._insert_toc 未被调用而失败。
    """
    from beeoffice.plugins.beewrite import BeeWriteEditor
    from beeoffice.plugins.beewrite_plugin import BeeWritePlugin

    editor = BeeWriteEditor()
    qtbot.addWidget(editor)

    # 记录 _insert_toc 被调用
    called = []
    monkeypatch.setattr(
        editor, "_insert_toc",
        lambda: called.append("_insert_toc"),
    )

    # 构造最小 parent（只需 tab_manager.currentWidget）
    class _FakeTabManager:
        def currentWidget(self):
            return editor

    class _FakeParent:
        def __init__(self):
            self.tab_manager = _FakeTabManager()

    plugin = BeeWritePlugin(parent=_FakeParent())
    plugin.generate_toc()

    assert called == ["_insert_toc"], (
        "plugin.generate_toc 未调用 editor._insert_toc。"
        "P0-9 修复被回退了（方法名可能又变成了 _generate_toc）"
    )


def test_plugin_generate_toc_warns_when_no_editor(monkeypatch):
    """P0-9：无活动编辑器时应给出提示，而不是静默失败。"""
    from beeoffice.plugins.beewrite_plugin import BeeWritePlugin

    warned = []
    monkeypatch.setattr(
        BeeWritePlugin, "_warn",
        lambda self, msg: warned.append(msg),
    )

    class _FakeTabManager:
        def currentWidget(self):
            return None

    class _FakeParent:
        def __init__(self):
            self.tab_manager = _FakeTabManager()

    plugin = BeeWritePlugin(parent=_FakeParent())
    plugin.generate_toc()

    assert warned, "无活动编辑器时应调用 _warn()"
    assert "蜜写" in warned[0]