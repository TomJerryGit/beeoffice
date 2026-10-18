import sys
import traceback
import platform
from pathlib import Path
from datetime import datetime
from beeoffice.i18n import tr


class CrashHandler:
    """全局崩溃处理器：捕获未处理异常，写入日志并提示用户"""

    LOG_DIR = Path.home() / ".beeoffice_logs"
    MAX_LOG_FILES = 20  # 最多保留的崩溃日志数量

    @classmethod
    def install(cls):
        """安装全局异常钩子"""
        sys.excepthook = cls._handle_exception

    @classmethod
    def _handle_exception(cls, exc_type, exc_value, exc_tb):
        """异常处理主函数"""
        # 键盘中断不处理
        if exc_type == KeyboardInterrupt:
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return

        # 确保日志目录存在
        try:
            cls.LOG_DIR.mkdir(parents=True, exist_ok=True)
        except Exception:
            # 如果连日志目录都无法创建，只能打印到标准错误
            traceback.print_exception(exc_type, exc_value, exc_tb)
            return

        # 写入崩溃日志
        log_path = cls._write_log(exc_type, exc_value, exc_tb)

        # 清理旧日志
        cls._cleanup_logs()

        # 尝试在 GUI 中提示用户（仅在 QApplication 存在时）
        cls._show_gui_message(log_path)

    @classmethod
    def _write_log(cls, exc_type, exc_value, exc_tb):
        """将异常信息写入日志文件"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = cls.LOG_DIR / f"crash_{timestamp}.log"

        # 读取版本信息（防止模块加载失败）
        try:
            from beeoffice.__version__ import __version__
        except Exception:
            __version__ = "未知"

        try:
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("=" * 60 + "\n")
                f.write("🐝 蜜蜂办公 崩溃报告\n")
                f.write("=" * 60 + "\n\n")
                f.write(f"版本: {__version__}\n")
                f.write(f"时间: {datetime.now()}\n")
                f.write(f"系统: {platform.platform()}\n")
                f.write(f"Python: {platform.python_version()}\n")
                f.write(f"架构: {platform.machine()}\n")
                f.write(f"处理器: {platform.processor()}\n\n")
                f.write("-" * 60 + "\n")
                f.write("错误详情:\n")
                f.write("-" * 60 + "\n")
                traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
        except Exception as e:
            print(f"写入崩溃日志失败: {e}", file=sys.stderr)

        return log_path

    @classmethod
    def _cleanup_logs(cls):
        """清理旧的崩溃日志，保留最近 MAX_LOG_FILES 份"""
        try:
            log_files = sorted(cls.LOG_DIR.glob("crash_*.log"))
            # 如果超出保留数量，删除最旧的
            if len(log_files) > cls.MAX_LOG_FILES:
                for old_log in log_files[:-cls.MAX_LOG_FILES]:
                    try:
                        old_log.unlink()
                    except Exception:
                        pass
        except Exception as e:
            print(f"清理日志失败: {e}", file=sys.stderr)

    @classmethod
    def _show_gui_message(cls, log_path):
        """在 GUI 环境下弹出提示框"""
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
        except ImportError:
            # 没有 Qt，直接打印到标准错误
            print(f"\n🐝 蜜蜂办公遇到错误，日志已保存至: {log_path}\n", file=sys.stderr)
            return

        # 检查是否存在 QApplication 实例
        app = QApplication.instance()
        if app is None:
            # 无 GUI 环境（如命令行运行），仅打印提示
            print(f"\n🐝 蜜蜂办公遇到错误，日志已保存至: {log_path}\n", file=sys.stderr)
            return

        # 有 GUI 则弹出对话框
        try:
            QMessageBox.critical(
                None,
                tr("auto.crash_handler.a19f00ec", "🐝 蜜蜂遇到了问题"),
                tr("auto.crash_handler.c6aa4bc2", "很抱歉，程序遇到了意外错误。\n\n错误详情已保存至：\n{log_path}\n\n请将此文件发送给开发者以帮助改进。\n邮箱：1265338136@qq.com").format(log_path=log_path)
            )
        except Exception:
            # 弹框失败，仅打印
            print(f"\n🐝 蜜蜂办公遇到错误，日志已保存至: {log_path}\n", file=sys.stderr)