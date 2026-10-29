# tests/unit/test_plugin_api.py
"""插件 API v1：manifest 校验 + PluginContext + 加载契约。"""
import json
from pathlib import Path

import pytest

from beeoffice.plugin_api import (
    ALLOWED_PERMISSIONS,
    API_VERSION,
    PluginContext,
    PluginLoader,
    PluginManifest,
    PluginManifestError,
    PluginPermissionError,
)


def _manifest(**overrides):
    data = {
        "id": "com.example.demo",
        "name": "Demo",
        "version": "1.0.0",
        "api_version": API_VERSION,
        "entry": "plugin.py",
        "permissions": ["doc.read"],
    }
    data.update(overrides)
    return data


def test_manifest_valid():
    m = PluginManifest.from_dict(_manifest())
    assert m.id == "com.example.demo"
    assert m.activation == "on_demand"
    assert m.has_permission("doc.read")
    assert not m.has_permission("doc.write")
    assert m.describe_permissions()[0]["permission"] == "doc.read"


@pytest.mark.parametrize("overrides", [
    {"id": "bad id!"},
    {"api_version": "2"},
    {"permissions": ["unknown.permission"]},
    {"entry": "../outside.py"},
    {"entry": "plugin.txt"},
    {"activation": "always"},
    {"min_app_version": "99.0.0"},
])
def test_manifest_rejects_invalid(overrides):
    with pytest.raises(PluginManifestError):
        PluginManifest.from_dict(_manifest(**overrides), app_version="5.0.30")


def test_allowed_permissions_set():
    assert "doc.write" in ALLOWED_PERMISSIONS
    assert "ai.network" in ALLOWED_PERMISSIONS


def test_context_commands_events_settings():
    m = PluginManifest.from_dict(_manifest())
    ctx = PluginContext(m, "5.0.30")
    called = []
    ctx.commands.register("demo.run", lambda: called.append(1), title="Run")
    assert ctx.commands.invoke("demo.run") is None
    assert called == [1]
    with pytest.raises(ValueError):
        ctx.commands.register("demo.run", lambda: None)
    with pytest.raises(KeyError):
        ctx.commands.invoke("missing")

    events = []
    cb = lambda *a: events.append(a)
    ctx.events.on("doc.opened", cb)
    ctx.events.emit("doc.opened", "x")
    assert events == [("x",)]
    ctx.events.off("doc.opened", cb)
    ctx.events.emit("doc.opened", "y")
    assert events == [("x",)]

    ctx.settings.set("k", 1)
    assert ctx.settings.get("k") == 1


def test_context_permission_and_task_pane():
    m = PluginManifest.from_dict(_manifest())
    ctx = PluginContext(m, "5.0.30")
    ctx.require_permission("doc.read")
    with pytest.raises(PluginPermissionError):
        ctx.require_permission("doc.write")
    decl = ctx.ui.add_task_pane("demo", "Demo")
    assert decl.side == "right"
    with pytest.raises(ValueError):
        ctx.ui.add_task_pane("demo", "Dup")


def _write_plugin(tmp_path: Path, source: str = None):
    manifest = _manifest()
    (tmp_path / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    source = source or '''
from beeoffice.plugin_api import BeePlugin

class DemoPlugin(BeePlugin):
    def activate(self, ctx):
        ctx.commands.register("demo.hello", lambda: "hello", title="Hello")
        ctx.ui.add_task_pane("demo", "Demo")
        self.activated = True

    def deactivate(self):
        self.closed = True
'''
    (tmp_path / "plugin.py").write_text(source, encoding="utf-8")
    return tmp_path


def test_loader_activates_and_deactivates(tmp_path):
    loaded = PluginLoader.load(_write_plugin(tmp_path), app_version="5.0.30")
    assert loaded.manifest.id == "com.example.demo"
    assert loaded.context.commands.invoke("demo.hello") == "hello"
    assert "demo" in loaded.context.ui.task_panes
    assert loaded.plugin.activated is True
    loaded.deactivate()
    assert loaded.context.is_active() is False
    assert loaded.plugin.closed is True


def test_loader_requires_beeplugin_subclass(tmp_path):
    with pytest.raises(PluginManifestError):
        PluginLoader.load(_write_plugin(tmp_path, "x = 1\n"))
