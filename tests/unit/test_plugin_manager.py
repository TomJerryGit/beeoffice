# tests/unit/test_plugin_manager.py
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
