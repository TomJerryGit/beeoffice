# beeoffice/utils.py
"""通用工具函数模块"""
import os
import sys
import json
import uuid
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


def atomic_write_text(path, text: str, encoding: str = "utf-8") -> bool:
    """
    原子写入文本文件。

    先写入同目录下的临时文件并 fsync，再用 os.replace() 覆盖目标。
    这样任何中途失败（磁盘满、权限、编码错误）都不会破坏原有文件——
    目标文件要么是旧的完整内容，要么是新的完整内容，不会出现被截断的空文件。

    实现说明（重要）：临时文件用 ``open(tmp, "x")`` 独占创建，
    **不要**用 ``tempfile.mkstemp()``。mkstemp 内部走 ``os.open()``，
    当目标目录不可写（受限账户、被安全软件/沙箱拦截等）时，实测该调用路径
    会**无限期阻塞**；而 ``open()`` 会在毫秒级抛出 PermissionError。
    保存设置这类调用发生在 UI 线程上，"卡死"比"失败"严重得多，
    因此这里选择能快速失败的那条路径。

    :return: 是否写入成功
    """
    target = Path(path)
    tmp_path = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        # 同目录 + 独占创建 + 唯一名字：既保证 os.replace 的原子性
        # （同一文件系统），又不会覆盖或撞上已存在的文件。
        tmp_path = target.parent / (
            f".{target.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
        )
        with open(tmp_path, "x", encoding=encoding) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, target)
        return True
    except Exception as e:
        logging.error(f"原子写入失败（原文件保持不变） {target}: {e}")
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        return False


def atomic_write_json(path, obj, indent: int = 2) -> bool:
    """
    原子写入 JSON 文件。

    注意序列化在打开目标文件**之前**完成，因此序列化异常只会让写入失败，
    绝不会留下一个被截断的空文件（这正是 AppSettings.save() 原有的缺陷）。
    """
    try:
        text = json.dumps(obj, indent=indent, ensure_ascii=False)
    except Exception as e:
        logging.error(f"JSON 序列化失败（目标文件未改动） {path}: {e}")
        return False
    return atomic_write_text(path, text)


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