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


#: 日志降级原因；为 None 表示日志已正常写入文件（供界面提示用）
LOGGING_DEGRADED = None


def setup_logging():
    """
    配置全局日志，输出到文件。

    **日志目录不可写时不能让程序起不来**（P0-A 修复）
    ---------------------------------------------------
    原实现直接调 `logging.basicConfig(filename=...)`，没有任何保护。
    于是下面这些**真实存在**的环境会让程序在**任何界面出现之前**就退出：
      · 企业策略/受管账号把家目录设为只读
      · 漫游配置文件损坏、家目录指向不可用网络位置
      · 磁盘写满
      · 以受限账号或沙箱运行

    实测 traceback（用 `python -m beeoffice.main` 复现）：
        PermissionError: [Errno 13] Permission denied:
        'C:\\Users\\Administrator\\.beeoffice_logs\\app.log'

    现在：优先写文件；失败则**退回只写标准错误**，并记下原因
    （`LOGGING_DEGRADED`），由界面在启动后以状态栏提示 —— 既不会崩，
    也不会让用户对"日志没在记录"一无所知。
    """
    global LOGGING_DEGRADED
    LOGGING_DEGRADED = None

    log_dir = CrashHandler.LOG_DIR
    fmt = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=str(log_dir / "app.log"),
            level=logging.INFO,
            format=fmt,
            encoding='utf-8',
        )
    except Exception as e:  # noqa: BLE001 - 任何原因都不该阻止启动
        LOGGING_DEGRADED = f"{type(e).__name__}: {e}"
        # 无 filename 的 basicConfig 会退回 stderr，程序继续跑
        try:
            logging.basicConfig(level=logging.INFO, format=fmt)
        except Exception:  # noqa: BLE001
            pass
        logging.warning(
            f"日志无法写入 {log_dir}（{LOGGING_DEGRADED}），"
            f"已改为只输出到标准错误；功能不受影响"
        )

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

    # QtWebEngine 要求共享 OpenGL 上下文在 QCoreApplication 创建**之前**设置，
    # 否则会告警：
    #   Attribute Qt::AA_ShareOpenGLContexts must be set before
    #   QCoreApplication is created
    # 并可能伴随渲染异常。这里只设属性、**不** import WebEngine ——
    # 以保持"用到蜜演才加载 QtWebEngine"的懒加载行为（优化规划 §2.1）。
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)

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

    # 设置保存失败必须让用户看见：settings.py 只在注册了回调时才提示，
    # 未注册时仅记日志（见 BeeOffice-优化规划.md §1.2）
    AppSettings.on_save_error = window._on_settings_save_error

    window.show()

    # P0-A：日志目录不可写时，明确告诉用户（而不是默默不记录）
    if LOGGING_DEGRADED:
        try:
            window.status.showMessage(
                f"⚠️ 无法写入日志目录，日志已改为仅输出到控制台："
                f"{LOGGING_DEGRADED}", 15000
            )
        except Exception:  # noqa: BLE001 - 提示失败不影响运行
            pass

    # 处理命令行参数：打开传入的文件
    if len(sys.argv) > 1:
        for filepath in sys.argv[1:]:
            if Path(filepath).exists():
                QTimer.singleShot(200, lambda p=filepath: window._open_recent(p))

    elapsed = time.perf_counter() - t0
    print(f"🐝 蜜蜂办公 v5.0 启动成功！耗时: {elapsed * 1000:.0f}ms")
    logging.info(f"启动完成，耗时: {elapsed * 1000:.0f}ms")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()