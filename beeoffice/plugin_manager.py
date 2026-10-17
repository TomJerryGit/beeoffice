# beeoffice/plugin_manager.py
"""
插件管理器：负责扫描、加载、管理所有插件
"""
import importlib
import inspect
import logging
import pkgutil
from pathlib import Path
from typing import List, Dict, Any

from beeoffice.plugin_base import Plugin, USER_PLUGIN_MARKER


class PluginManager:
    """插件管理器"""

    def __init__(self, parent=None):
        """
        :param parent: 主窗口实例（BeeApp）
        """
        self.parent = parent
        self.plugins: List[Plugin] = []          # 插件实例列表
        self.plugin_info: List[Dict[str, Any]] = []  # 插件元信息列表
        self._loaded = False

    # ---------- 发现插件 ----------
    def discover_plugins(self) -> None:
        """
        扫描 beeoffice/plugins 包，寻找 Plugin 子类。

        v5.0.6（性能）：**只导入真正的插件模块**。

        背景：原实现 import 目录下每一个模块（86 个），把 Mixin、引擎、
        对话框全部拉进来——连带 pandas / numpy / PyMuPDF / matplotlib。
        实测该步骤耗时 **7.9 秒**，而且发生在窗口 show() 之后的 50ms，
        表现为"窗口出来了但点不动"。

        判定规则（见 _is_plugin_module）：
          1. 内置插件包装器：文件名以 `_plugin` 结尾；
          2. 用户插件：文件首行带 USER_PLUGIN_MARKER（插件市场安装）。
        其余模块在被真正使用到时才 import。
        """
        plugins_path = Path(__file__).parent / "plugins"
        if not plugins_path.exists():
            logging.warning(f"插件目录不存在: {plugins_path}")
            return

        skipped = 0
        imported = 0
        for module_info in pkgutil.iter_modules([str(plugins_path)]):
            name = module_info.name
            # 跳过内部模块（以 _ 开头的模块，如 __init__、_helper 等）
            if name.startswith("_"):
                continue
            if not self._is_plugin_module(plugins_path, name):
                skipped += 1
                continue
            module_name = f"beeoffice.plugins.{name}"
            try:
                module = importlib.import_module(module_name)
                self._register_plugins_from_module(module)
                imported += 1
            except Exception as e:
                logging.error(f"加载插件模块 {module_name} 失败: {e}")

        logging.info(
            f"插件扫描完成：导入 {imported} 个，跳过 {skipped} 个非插件模块"
        )

    @staticmethod
    def _is_plugin_module(plugins_path: Path, name: str) -> bool:
        """判断某个模块是否需要在启动时导入（见 discover_plugins 说明）。"""
        if name.endswith("_plugin"):
            return True
        candidate = plugins_path / f"{name}.py"
        try:
            with open(candidate, "r", encoding="utf-8", errors="ignore") as f:
                head = f.read(4096)
            return head.lstrip("\ufeff").startswith(USER_PLUGIN_MARKER)
        except OSError:
            return False

    def _register_plugins_from_module(self, module) -> None:
        """从模块中查找 Plugin 子类并实例化"""
        for name, obj in inspect.getmembers(module, inspect.isclass):
            # 必须是 Plugin 的子类，且不能是 Plugin 本身
            if not issubclass(obj, Plugin) or obj is Plugin:
                continue
            # 跳过在其他模块中导入的 Plugin 子类（只处理当前模块定义的）
            if obj.__module__ != module.__name__:
                continue
            try:
                plugin = obj(parent=self.parent)
                self.plugins.append(plugin)
                self.plugin_info.append({
                    "name": plugin.name,
                    "version": plugin.version,
                    "description": plugin.description,
                    "author": plugin.author,
                    "enabled": plugin.is_enabled(),
                    "instance": plugin,
                })
                logging.info(f"发现插件: {plugin.name} v{plugin.version}")
            except Exception as e:
                logging.error(f"实例化插件 {name} 失败: {e}")

    # ---------- 加载插件 ----------
    def load_plugins(self) -> None:
        """加载所有已发现的插件（调用注册命令和生命周期钩子）"""
        if self._loaded:
            logging.warning("插件已加载，跳过重复调用")
            return

        for plugin in self.plugins:
            # 调用 on_load 钩子
            try:
                plugin.on_load()
            except Exception as e:
                logging.error(f"插件 {plugin.name} on_load 失败: {e}")

            # 注册命令到命令面板（延迟到命令面板实际打开时再注册）
            # 这里不直接注册，由 commands.py 在构建时遍历插件注册
            # 但也可以在此处进行预注册（若命令面板为全局单例）

        self._loaded = True
        logging.info(f"共加载 {len(self.plugins)} 个插件")

    # ---------- 查询接口 ----------
    def get_plugin_by_name(self, name: str) -> Plugin:
        """根据名称查找插件"""
        for plugin in self.plugins:
            if plugin.name == name:
                return plugin
        return None

    def get_plugin_info_by_name(self, name: str) -> Dict[str, Any]:
        """根据名称查找插件元信息"""
        for info in self.plugin_info:
            if info["name"] == name:
                return info
        return None

    def get_enabled_plugins(self) -> List[Plugin]:
        """返回所有已启用的插件"""
        return [p for p in self.plugins if p.is_enabled()]

    def count(self) -> int:
        """返回插件总数"""
        return len(self.plugins)

    # ---------- 卸载插件 ----------
    def unload_plugin(self, name: str) -> bool:
        """卸载指定插件"""
        plugin = self.get_plugin_by_name(name)
        if not plugin:
            return False
        try:
            plugin.on_close()
        except Exception as e:
            logging.error(f"插件 {name} 卸载失败: {e}")
        try:
            self.plugins.remove(plugin)
        except ValueError:
            pass
        # 移除元信息
        self.plugin_info = [info for info in self.plugin_info if info["name"] != name]
        logging.info(f"已卸载插件: {name}")
        return True

    # ---------- 关闭全部插件 ----------
    def close_all(self) -> None:
        """关闭所有插件，释放资源"""
        for plugin in list(self.plugins):
            try:
                plugin.on_close()
            except Exception as e:
                logging.error(f"关闭插件 {plugin.name} 失败: {e}")

    def __repr__(self) -> str:
        return f"<PluginManager: {len(self.plugins)} plugins>"