# beeoffice/plugin_manager.py
"""
插件管理器：负责扫描、加载、管理所有插件

v5.0.8 性能修复（优化规划 §2.1）：
  原实现对 beeoffice/plugins/ 下**全部** 84 个模块逐个
  importlib.import_module()。其中只有 4 个是插件壳（*_plugin.py），
  其余 80 个是编辑器实现模块——把 pandas / matplotlib / PyMuPDF /
  QtWebEngine 统统拉起来。实测 discover_plugins() 需 2487 ms
  （冷启动 9110 ms），而这段代码由 app.py 在窗口 show() 之后用
  QTimer 在主线程同步执行，于是界面冻结约 7~9 秒。

  实测数据（同一环境）：
    - pkgutil.iter_modules 扫描 84 个模块名     10.6 ms
    - import 4 个 *_plugin.py 壳模块            1~3 ms/个，且不拉任何重依赖
    （重依赖都在各插件的 create_widget() 里延迟导入）

  因此只要**不 import 那 80 个实现模块**即可，无需改动插件架构。
"""
import importlib
import inspect
import logging
import pkgutil
from pathlib import Path
from typing import List, Dict, Any

from beeoffice.plugin_base import Plugin

#: 约定：插件模块文件名以 `_plugin.py` 结尾
#: （beewrite_plugin / beesheet_plugin / beeshow_plugin / pdf_annotator_plugin）
PLUGIN_FILENAME_SUFFIX = "_plugin"

#: 兜底信号：非约定命名的模块，若源码里出现 `(Plugin)`（子类声明）也视为候选。
#: 这里只**读取文件文本**，不执行模块，因此不会拉起依赖。
PLUGIN_SOURCE_MARKER = "(Plugin)"


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
        self.plugins_path = Path(__file__).parent / "plugins"
        # 最近一次发现过程的统计（供测试与诊断使用）
        self.last_discovery_stats: Dict[str, Any] = {}

    # ---------- 发现插件 ----------
    def iter_plugin_module_names(self) -> List[str]:
        """
        扫描 plugins 包，返回**可能是插件**的模块短名（全程不 import）。

        判断依据（两个廉价信号）：
          1. 文件名以 `_plugin` 结尾 —— 本项目内置插件的约定；
          2. 其余模块读源码找 `(Plugin)` 子类声明 —— 避免插件作者换文件名被漏掉。

        以 _ 开头的模块（__init__ 等）一律跳过。
        """
        if not self.plugins_path.exists():
            return []

        candidates: List[str] = []
        scanned = 0
        for module_info in pkgutil.iter_modules([str(self.plugins_path)]):
            name = module_info.name
            scanned += 1
            if name.startswith("_"):
                continue
            if name.endswith(PLUGIN_FILENAME_SUFFIX):
                candidates.append(name)
            elif self._source_declares_plugin(self.plugins_path / f"{name}.py"):
                candidates.append(name)

        self.last_discovery_stats = {
            "scanned": scanned,
            "candidates": len(candidates),
            "skipped": scanned - len(candidates),
        }
        return candidates

    @staticmethod
    def _source_declares_plugin(path: Path) -> bool:
        """只读文件文本判断是否声明了 Plugin 子类（不执行模块）。"""
        try:
            if not path.is_file():
                return False
            return PLUGIN_SOURCE_MARKER in path.read_text(
                encoding="utf-8", errors="ignore"
            )
        except Exception:
            # 读不了就当不是插件，交给下一次启动/log 排查
            return False

    def discover_plugins(self) -> None:
        """扫描 beeoffice/plugins 包，寻找并实例化 Plugin 子类。

        只 import 候选插件模块（见 iter_plugin_module_names），
        不再为了找插件而把整个 plugins 目录 import 一遍。
        """
        if not self.plugins_path.exists():
            logging.warning(f"插件目录不存在: {self.plugins_path}")
            return

        names = self.iter_plugin_module_names()
        logging.debug(
            f"插件扫描：共 {self.last_discovery_stats.get('scanned', 0)} 个模块，"
            f"候选 {len(names)} 个，跳过 "
            f"{self.last_discovery_stats.get('skipped', 0)} 个实现模块"
        )

        for short_name in names:
            module_name = f"beeoffice.plugins.{short_name}"
            try:
                module = importlib.import_module(module_name)
                self._register_plugins_from_module(module)
            except Exception as e:
                logging.error(f"加载插件模块 {module_name} 失败: {e}")

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