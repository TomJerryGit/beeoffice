# beeoffice/plugin_api.py
"""BeeOffice 插件 API v1（S1 第一步）。

范围（本文件只做**核心契约**，不绑定 Qt）：
- PluginManifest：解析/校验 manifest.json；
- 权限声明与运行时校验；
- PluginContext：Ribbon/UI/Commands/Events/Document/AI/Settings 的稳定入口；
- BeePlugin：插件生命周期基类；
- PluginLoader：从目录加载插件并调用 activate。

设计约束：
- 第三方插件不直接接触 Qt 控件；S1 先落“声明 + 命令 + 事件 + 权限”；
- 文档读写通过 DocumentAPI（宿主注入），loader 不实现具体编辑器；
- API 主版本不兼容时拒绝加载，不静默降级。
"""
from __future__ import annotations

import importlib.util
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

API_VERSION = "1"
APP_VERSION_FALLBACK = "0.0.0"

ALLOWED_PERMISSIONS = frozenset({
    "doc.read",
    "doc.write",
    "doc.export",
    "ai.network",
    "filesystem.read",
    "filesystem.write",
    "command.execute",
    "macro",
})
PERMISSION_HINTS = {
    "doc.read": "读取当前文档/选区",
    "doc.write": "事务内修改文档",
    "doc.export": "另存/导出",
    "ai.network": "调用 AI/网络",
    "filesystem.read": "读取用户选择的文件",
    "filesystem.write": "写入文件",
    "command.execute": "执行外部程序",
    "macro": "宏/脚本自动化",
}

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,127}$")
_VERSION_RE = re.compile(r"^\d+(\.\d+){0,3}$")
_ACTIVATIONS = {"startup", "on_demand"}
_SIDES = {"left", "right"}


class PluginManifestError(ValueError):
    """manifest 不合法。"""


class PluginPermissionError(PermissionError):
    """插件未声明或未获授权。"""


def _parse_version(value: str) -> tuple[int, ...]:
    if not isinstance(value, str) or not _VERSION_RE.match(value):
        raise PluginManifestError(f"版本号不合法: {value!r}（示例 1.0.0）")
    return tuple(int(x) for x in value.split("."))


def _version_lt(a: str, b: str) -> bool:
    pa = _parse_version(a)
    pb = _parse_version(b)
    n = max(len(pa), len(pb))
    return pa + (0,) * (n - len(pa)) < pb + (0,) * (n - len(pb))


def _safe_relative(path_str: str, base: Optional[Path], label: str) -> Path:
    if not isinstance(path_str, str) or not path_str.strip():
        raise PluginManifestError(f"{label} 不能为空")
    rel = Path(path_str)
    if rel.is_absolute():
        raise PluginManifestError(f"{label} 必须是包内相对路径: {path_str!r}")
    if ".." in rel.parts:
        raise PluginManifestError(f"{label} 不允许包含 '..': {path_str!r}")
    if base is None:
        return rel
    resolved = (base / rel).resolve()
    try:
        resolved.relative_to(base.resolve())
    except ValueError as e:
        raise PluginManifestError(f"{label} 越界: {path_str!r}") from e
    return resolved


@dataclass(frozen=True)
class PluginManifest:
    """manifest.json 的稳定表示。"""

    id: str
    name: str
    version: str
    api_version: str
    min_app_version: str
    entry: str
    description: str = ""
    author: str = ""
    icon: str = ""
    permissions: tuple[str, ...] = ()
    activation: str = "on_demand"
    ui: dict = field(default_factory=dict)
    base_dir: Optional[Path] = field(default=None, compare=False, repr=False)

    @classmethod
    def from_dict(cls, data: dict, *, app_version: str = APP_VERSION_FALLBACK,
                  base_dir: Optional[Path] = None) -> "PluginManifest":
        if not isinstance(data, dict):
            raise PluginManifestError("manifest 必须是 JSON 对象")
        required = ("id", "name", "version", "api_version", "entry")
        for key in required:
            if key not in data:
                raise PluginManifestError(f"manifest 缺少字段: {key}")
        pid = data["id"]
        if not isinstance(pid, str) or not ID_RE.match(pid):
            raise PluginManifestError(f"插件 id 不合法: {pid!r}")
        if data["api_version"] != API_VERSION:
            raise PluginManifestError(
                f"不兼容的 api_version: {data['api_version']!r}，"
                f"当前支持 {API_VERSION}"
            )
        name = data["name"]
        if not isinstance(name, str) or not name.strip():
            raise PluginManifestError("name 不能为空")
        version = data["version"]
        _parse_version(version)
        min_app_version = data.get("min_app_version", "0.0.0")
        _parse_version(min_app_version)
        if app_version and app_version != APP_VERSION_FALLBACK and _version_lt(
            app_version, min_app_version
        ):
            raise PluginManifestError(
                f"插件要求 app >= {min_app_version}，当前 {app_version}"
            )
        entry = _safe_relative(data["entry"], base_dir, "entry")
        if entry.suffix.lower() != ".py":
            raise PluginManifestError("entry 必须是 .py 文件")
        icon = data.get("icon", "")
        if icon:
            _safe_relative(icon, base_dir, "icon")
        raw_permissions = data.get("permissions", [])
        if not isinstance(raw_permissions, list):
            raise PluginManifestError("permissions 必须是数组")
        permissions = []
        for perm in raw_permissions:
            if not isinstance(perm, str) or perm not in ALLOWED_PERMISSIONS:
                raise PluginManifestError(
                    f"未知权限: {perm!r}；允许: {sorted(ALLOWED_PERMISSIONS)}"
                )
            if perm not in permissions:
                permissions.append(perm)
        activation = data.get("activation", "on_demand")
        if activation not in _ACTIVATIONS:
            raise PluginManifestError(
                f"activation 只能是 {sorted(_ACTIVATIONS)}，收到 {activation!r}"
            )
        ui = data.get("ui", {})
        if ui is not None and not isinstance(ui, dict):
            raise PluginManifestError("ui 必须是对象")
        return cls(
            id=pid, name=name.strip(), version=version,
            api_version=data["api_version"], min_app_version=min_app_version,
            entry=str(Path(data["entry"])), description=str(data.get("description", "")),
            author=str(data.get("author", "")), icon=str(icon),
            permissions=tuple(permissions), activation=activation,
            ui=ui or {}, base_dir=base_dir,
        )

    @classmethod
    def from_file(cls, path: str | Path, *, app_version: str = APP_VERSION_FALLBACK):
        path = Path(path)
        if path.is_dir():
            path = path / "manifest.json"
        if not path.is_file():
            raise PluginManifestError(f"manifest 不存在: {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise PluginManifestError(f"manifest 读取失败: {e}") from e
        return cls.from_dict(data, app_version=app_version, base_dir=path.parent)

    def entry_path(self) -> Path:
        return _safe_relative(self.entry, self.base_dir, "entry")

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions

    def describe_permissions(self) -> list[dict]:
        return [
            {"permission": p, "hint": PERMISSION_HINTS.get(p, "")}
            for p in self.permissions
        ]


# ==================== 扩展点声明（S1 核心） ====================

@dataclass
class RibbonDeclaration:
    tab: str
    group: str = ""
    button: str = ""
    command: str = ""
    icon: str = ""
    large: bool = False
    order: int = 100


class RibbonAPI:
    """收集插件 Ribbon 贡献；S2 再接到真实 Ribbon。"""

    def __init__(self):
        self.tabs: dict[str, list[RibbonDeclaration]] = {}

    def add_tab(self, title: str, order: int = 100):
        self.tabs.setdefault(title, [])
        return title

    def add_group(self, tab: str, title: str):
        self.tabs.setdefault(tab, [])
        return (tab, title)

    def add_button(self, group, text: str, icon: str = "",
                   command: str = "", large: bool = False):
        tab, group_title = group
        decl = RibbonDeclaration(tab, group_title, text, command, icon, large)
        self.tabs.setdefault(tab, []).append(decl)
        return decl

    def declarations(self) -> list[RibbonDeclaration]:
        return [d for items in self.tabs.values() for d in items]


@dataclass
class TaskPaneDeclaration:
    pane_id: str
    title: str
    side: str = "right"
    factory: Optional[Callable] = field(default=None, repr=False)


class UiAPI:
    def __init__(self):
        self.task_panes: dict[str, TaskPaneDeclaration] = {}

    def add_task_pane(self, pane_id: str, title: str, *,
                      side: str = "right", widget=None):
        if not pane_id or not isinstance(pane_id, str):
            raise ValueError("pane_id 不能为空")
        if side not in _SIDES:
            raise ValueError(f"side 只能是 {sorted(_SIDES)}")
        if pane_id in self.task_panes:
            raise ValueError(f"任务窗格重复: {pane_id}")
        decl = TaskPaneDeclaration(pane_id, title, side, widget)
        self.task_panes[pane_id] = decl
        return decl


class CommandRegistry:
    def __init__(self):
        self._commands: dict[str, dict] = {}

    def register(self, command_id: str, handler: Callable, *,
                 title: str = "", shortcut: str = ""):
        if not command_id or not isinstance(command_id, str):
            raise ValueError("command_id 不能为空")
        if not callable(handler):
            raise TypeError("handler 必须可调用")
        if command_id in self._commands:
            raise ValueError(f"命令重复注册: {command_id}")
        self._commands[command_id] = {
            "handler": handler, "title": title, "shortcut": shortcut,
        }
        return command_id

    def unregister(self, command_id: str):
        self._commands.pop(command_id, None)

    def invoke(self, command_id: str, *args, **kwargs):
        if command_id not in self._commands:
            raise KeyError(f"未知命令: {command_id}")
        return self._commands[command_id]["handler"](*args, **kwargs)

    def get(self, command_id: str):
        return self._commands.get(command_id)

    def ids(self) -> list[str]:
        return sorted(self._commands)


class EventBus:
    def __init__(self):
        self._listeners: dict[str, list[Callable]] = {}

    def on(self, event: str, callback: Callable):
        if not callable(callback):
            raise TypeError("callback 必须可调用")
        self._listeners.setdefault(event, []).append(callback)

    def off(self, event: str, callback: Callable):
        if event in self._listeners and callback in self._listeners[event]:
            self._listeners[event].remove(callback)

    def emit(self, event: str, *args, **kwargs):
        for callback in list(self._listeners.get(event, [])):
            callback(*args, **kwargs)


class DocumentAPI:
    """宿主注入的文档访问；未注入时调用会明确失败，而不是静默假成功。"""

    def __init__(self, host=None):
        self._host = host

    def _need(self, name):
        if self._host is None:
            raise NotImplementedError(
                f"DocumentAPI.{name} 需要宿主注入；S1 只提供契约"
            )
        return self._host

    def read(self):
        return self._need("read").read()

    def selection_text(self) -> str:
        return self._need("selection_text").selection_text()

    def replace_selection(self, text: str):
        return self._need("replace_selection").replace_selection(text)

    def transaction(self, label: str):
        return self._need("transaction").transaction(label)


class AIAPI:
    def __init__(self, runner=None):
        self._runner = runner

    def run(self, task: str, **payload):
        if self._runner is None:
            raise NotImplementedError("AIAPI 需要宿主注入 runner；请先配置 AI")
        return self._runner(task, **payload)


class SettingsAPI:
    def __init__(self, initial=None):
        self._data = dict(initial or {})

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value

    def all(self):
        return dict(self._data)


class PluginContext:
    """插件唯一可依赖的宿主接口。"""

    def __init__(self, manifest: PluginManifest, app_version: str = APP_VERSION_FALLBACK):
        self.manifest = manifest
        self.plugin_id = manifest.id
        self.app_version = app_version
        self.log = logging.getLogger(f"beeoffice.plugin.{manifest.id}")
        self.ribbon = RibbonAPI()
        self.ui = UiAPI()
        self.commands = CommandRegistry()
        self.events = EventBus()
        self.doc = DocumentAPI()
        self.ai = AIAPI()
        self.settings = SettingsAPI()
        self._active = True

    def require_permission(self, permission: str):
        if permission not in ALLOWED_PERMISSIONS:
            raise PluginPermissionError(f"未知权限: {permission}")
        if not self.manifest.has_permission(permission):
            raise PluginPermissionError(
                f"插件 {self.plugin_id} 未声明权限 {permission}"
            )

    def is_active(self) -> bool:
        return self._active

    def dispose(self):
        self._active = False


class BeePlugin:
    """插件基类（新 API）；旧 Plugin 保持兼容。"""

    def activate(self, ctx: PluginContext):
        raise NotImplementedError

    def deactivate(self):
        pass


class LoadedPlugin:
    def __init__(self, plugin, context: PluginContext, manifest: PluginManifest):
        self.plugin = plugin
        self.context = context
        self.manifest = manifest

    def deactivate(self):
        try:
            self.plugin.deactivate()
        finally:
            self.context.dispose()


class PluginLoader:
    """从目录加载 v1 插件；不做 UI 挂载，只返回契约对象。"""

    @staticmethod
    def load(plugin_dir: str | Path, *, app_version: str = APP_VERSION_FALLBACK) -> LoadedPlugin:
        plugin_dir = Path(plugin_dir).resolve()
        manifest = PluginManifest.from_file(plugin_dir, app_version=app_version)
        entry = manifest.entry_path()
        if not entry.is_file():
            raise PluginManifestError(f"entry 不存在: {entry}")
        module_name = "beeoffice_plugin_" + re.sub(r"[^A-Za-z0-9_]", "_", manifest.id)
        spec = importlib.util.spec_from_file_location(module_name, entry)
        if spec is None or spec.loader is None:
            raise PluginManifestError(f"无法加载 entry: {entry}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
            candidates = [
                obj for obj in vars(module).values()
                if isinstance(obj, type) and issubclass(obj, BeePlugin)
                and obj is not BeePlugin
            ]
            if not candidates:
                raise PluginManifestError(
                    "entry 中没有 BeePlugin 子类"
                )
            plugin = candidates[0]()
            context = PluginContext(manifest, app_version)
            plugin.activate(context)
            return LoadedPlugin(plugin, context, manifest)
        except Exception:
            sys.modules.pop(module_name, None)
            raise
