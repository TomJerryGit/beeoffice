# beeoffice/plugin_base.py
"""
插件基类：所有插件应继承此类，实现必要接口
"""
import logging
from typing import Optional, List

from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QIcon


class Plugin:
    """插件基类"""

    # 插件元信息（子类应覆盖）
    name: str = "未命名插件"
    version: str = "0.1"
    description: str = ""
    author: str = ""
    icon: Optional[QIcon] = None  # 可以是 QIcon 实例或图标路径字符串

    def __init__(self, parent=None):
        """
        :param parent: 主窗口实例（BeeApp），用于访问 tab_manager、settings 等
        """
        self.parent = parent
        self.widget: Optional[QWidget] = None  # 主界面控件实例（懒加载）
        self._enabled: bool = True

    # ---------- 必须实现的接口 ----------
    def create_widget(self, parent=None) -> QWidget:
        """
        创建主界面控件，返回 QWidget 实例。
        子类必须实现此方法。
        """
        raise NotImplementedError(
            f"插件 {self.name} 未实现 create_widget 方法"
        )

    # ---------- 可选实现的钩子 ----------
    def register_commands(self, command_palette) -> None:
        """
        注册命令到命令面板
        :param command_palette: CommandPalette 实例
        """
        pass

    def register_menus(self, menu_bar) -> None:
        """
        注册菜单到菜单栏
        :param menu_bar: QMenuBar 实例
        """
        pass

    def on_load(self) -> None:
        """插件被加载时调用"""
        logging.info(f"插件已加载: {self.name} v{self.version}")

    def on_close(self) -> None:
        """插件被卸载或程序关闭时调用，用于清理资源"""
        try:
            if self.widget is not None:
                self.widget.deleteLater()
        except Exception as e:
            logging.error(f"关闭插件 {self.name} 失败: {e}")
        finally:
            self.widget = None

    # ---------- 生命周期管理 ----------
    def get_widget_instance(self, parent=None) -> QWidget:
        """
        获取控件实例。如果尚未创建则调用 create_widget 创建，
        否则直接返回已存在的实例。
        """
        if self.widget is None:
            try:
                self.widget = self.create_widget(parent or self.parent)
            except Exception as e:
                logging.error(f"创建插件 {self.name} 的控件失败: {e}")
                raise
        return self.widget

    def is_enabled(self) -> bool:
        """返回插件是否启用"""
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        """设置插件启用状态"""
        self._enabled = bool(enabled)

    # ---------- 元信息 ----------
    def get_info(self) -> dict:
        """返回插件元信息字典，用于插件市场展示"""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "enabled": self._enabled,
        }

    def __repr__(self) -> str:
        return f"<Plugin {self.name} v{self.version}>"