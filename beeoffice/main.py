# beeoffice/main.py
import sys
import time
import locale
import platform
import warnings
import logging
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer

from beeoffice.crash_handler import CrashHandler
from beeoffice.__version__ import __version__


def setup_logging():
    """配置全局日志，输出到文件"""
    log_dir = CrashHandler.LOG_DIR
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "app.log"

    # 注意：logging.basicConfig(encoding=...) 是 Python 3.9 才支持的参数，
    # 在 3.8 上会直接抛 ValueError: Unrecognised argument(s): encoding，
    # 表现为"双击 run.bat 闪退"。这里显式构造 FileHandler，
    # 既兼容 3.8，又能保证中文日志按 UTF-8 写入。
    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h, logging.FileHandler):
            return  # 避免重复添加

    handler = logging.FileHandler(str(log_file), encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    root.setLevel(logging.INFO)
    root.addHandler(handler)

    logging.info("=" * 50)
    logging.info("🐝 蜜蜂办公启动")
    logging.info("=" * 50)


def main():
    # 配置日志
    setup_logging()

    # Python 3.12+ 兼容：忽略弃用警告
    if sys.version_info >= (3, 12):
        warnings.filterwarnings('ignore', category=DeprecationWarning)

    # 安装崩溃处理器
    CrashHandler.install()
    # 清理旧的崩溃日志（保留最近20份）
    CrashHandler._cleanup_logs()

    t0 = time.perf_counter()

    # 高 DPI 适配
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # 中文路径兼容
    try:
        locale.setlocale(locale.LC_ALL, '')
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("BeeOffice")
    app.setOrganizationName("TomJerryGit")

    # macOS 字体回退
    if platform.system() == 'Darwin':
        from PySide6.QtGui import QFont
        QFont.insertSubstitution('.AppleSystemUIFont', 'PingFang SC')

    # 加载设置
    from beeoffice.settings import AppSettings
    settings = AppSettings()

    # 设置语言
    from beeoffice.i18n import set_language
    set_language(settings.language)

    # 延迟导入主窗口，减少启动时的模块加载量
    from beeoffice.app import BeeApp
    window = BeeApp()
    # 把进程起点交给主窗口：_lazy_load_modules 完成后会打印总耗时，
    # 这样打开日志就能看到"真正可交互"的时间，而不是只到 show()。
    window._startup_t0 = t0
    window.show()

    # 处理命令行参数：打开传入的文件
    if len(sys.argv) > 1:
        for filepath in sys.argv[1:]:
            if Path(filepath).exists():
                QTimer.singleShot(200, lambda p=filepath: window._open_recent(p))

    elapsed = time.perf_counter() - t0
    print(f"🐝 蜜蜂办公 v{__version__} 启动成功！耗时: {elapsed * 1000:.0f}ms")
    logging.info(f"启动完成，耗时: {elapsed * 1000:.0f}ms")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()