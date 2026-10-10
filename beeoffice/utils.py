# beeoffice/utils.py
"""通用工具函数模块"""
import os
import sys
import platform
import logging
from pathlib import Path


def get_memory_usage() -> float:
    """
    获取当前进程的内存使用量（MB）
    返回 -1 表示无法获取
    """
    try:
        import psutil
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024
    except ImportError:
        logging.warning("未安装 psutil，无法获取内存使用")
        return -1
    except Exception as e:
        logging.error(f"获取内存使用失败: {e}")
        return -1


def print_memory(tag: str = ""):
    """打印当前内存占用（仅调试模式下输出）"""
    if not __debug__:
        return
    mb = get_memory_usage()
    if mb > 0:
        logging.debug(f"🐝 内存 [{tag}]: {mb:.1f} MB")


def normalize_path(path: str) -> str:
    r"""
    规范化路径：
    - Windows 下处理超过 260 字符的长路径（添加 \\\\?\\ 前缀）
    - 统一路径分隔符
    """
    if not path:
        return path
    try:
        if platform.system() == 'Windows' and len(path) > 260:
            if not path.startswith('\\\\?\\'):
                return '\\\\?\\' + os.path.abspath(path)
        return path
    except Exception as e:
        logging.error(f"路径规范化失败: {e}")
        return path


def safe_filename(name: str) -> str:
    """
    将字符串转为安全的文件名：
    - 移除 Windows/Linux 下不合法的字符
    - 限制长度不超过 200 字符
    """
    if not name:
        return "untitled"
    illegal_chars = '<>:"/\\|?*'
    for ch in illegal_chars:
        name = name.replace(ch, '_')
    # 移除控制字符
    name = ''.join(c for c in name if ord(c) >= 32)
    name = name.strip().rstrip('.')
    if not name:
        name = "untitled"
    return name[:200]


def human_readable_size(size_bytes: int) -> str:
    """将字节数转为人类可读的大小字符串"""
    if size_bytes < 0:
        return "未知"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def ensure_dir(path) -> bool:
    """确保目录存在，返回是否成功"""
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logging.error(f"创建目录失败 {path}: {e}")
        return False


def get_app_data_dir() -> Path:
    """获取应用数据目录（跨平台）"""
    home = Path.home()
    if platform.system() == 'Windows':
        base = Path(os.environ.get('APPDATA', home))
    elif platform.system() == 'Darwin':
        base = home / 'Library' / 'Application Support'
    else:
        base = Path(os.environ.get('XDG_DATA_HOME', home / '.local' / 'share'))
    app_dir = base / 'BeeOffice'
    ensure_dir(app_dir)
    return app_dir


def is_frozen() -> bool:
    """判断是否在 PyInstaller 打包后的环境中运行"""
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')


def get_resource_path(relative_path: str) -> str:
    """
    获取资源文件的绝对路径，兼容打包和源码运行：
    - 打包后：使用 sys._MEIPASS
    - 源码运行：使用当前文件所在目录
    """
    if is_frozen():
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).parent.parent
    return str(base / relative_path)