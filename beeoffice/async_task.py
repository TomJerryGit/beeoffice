# beeoffice/async_task.py
"""
异步任务调度器：基于 QThreadPool 将耗时操作移至后台线程
"""
import traceback
import logging
from typing import Callable, Any, Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


class WorkerSignals(QObject):
    """工作线程信号集合"""
    started = Signal()                    # 任务开始
    finished = Signal()                   # 任务结束（无论成功或失败）
    error = Signal(str)                   # 任务出错，携带错误信息
    result = Signal(object)               # 任务成功，携带返回值


class Worker(QRunnable):
    """通用工作线程：在后台执行任意函数"""

    def __init__(self, fn: Callable, *args, **kwargs):
        """
        :param fn: 要执行的函数
        :param args: 位置参数
        :param kwargs: 关键字参数
        """
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.setAutoDelete(True)  # 执行完毕后自动释放

    @Slot()
    def run(self):
        """执行任务"""
        self.signals.started.emit()
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.signals.result.emit(result)
        except Exception as e:
            # 记录完整堆栈
            logging.error(f"异步任务执行失败: {e}\n{traceback.format_exc()}")
            self.signals.error.emit(str(e))
        finally:
            self.signals.finished.emit()


class AsyncTaskManager:
    """异步任务管理器（静态方法调用）"""

    _pool: Optional[QThreadPool] = None

    @classmethod
    def _get_pool(cls) -> QThreadPool:
        """延迟获取全局线程池"""
        if cls._pool is None:
            cls._pool = QThreadPool.globalInstance()
            # 限制最大并发数，避免资源耗尽
            cls._pool.setMaxThreadCount(max(2, cls._pool.maxThreadCount() // 2))
        return cls._pool

    @classmethod
    def run(cls, fn: Callable, *args,
            on_result: Optional[Callable[[Any], None]] = None,
            on_error: Optional[Callable[[str], None]] = None,
            on_finished: Optional[Callable[[], None]] = None,
            on_started: Optional[Callable[[], None]] = None,
            **kwargs) -> Worker:
        """
        在后台线程执行函数

        :param fn: 要执行的函数
        :param args: 位置参数
        :param on_result: 成功回调，接收函数返回值
        :param on_error: 失败回调，接收错误信息字符串
        :param on_finished: 完成回调（无论成功或失败）
        :param on_started: 开始回调
        :param kwargs: 关键字参数
        :return: Worker 实例（可用于取消或引用）

        用法：
            AsyncTaskManager.run(
                import_from_docx, path,
                on_result=lambda md: editor.set_content(md),
                on_error=lambda err: QMessageBox.warning(self, "失败", err),
            )
        """
        worker = Worker(fn, *args, **kwargs)

        # 连接信号
        if on_result:
            worker.signals.result.connect(on_result)
        if on_error:
            worker.signals.error.connect(on_error)
        if on_finished:
            worker.signals.finished.connect(on_finished)
        if on_started:
            worker.signals.started.connect(on_started)

        # 启动
        cls._get_pool().start(worker)
        return worker

    @classmethod
    def wait_for_done(cls, timeout_ms: int = -1) -> bool:
        """
        等待所有任务完成
        :param timeout_ms: 超时毫秒数，-1 表示无限等待
        :return: 是否在超时前完成
        """
        return cls._get_pool().waitForDone(timeout_ms)

    @classmethod
    def active_thread_count(cls) -> int:
        """返回当前活动线程数"""
        return cls._get_pool().activeThreadCount()

    @classmethod
    def set_max_threads(cls, count: int):
        """设置最大线程数"""
        cls._get_pool().setMaxThreadCount(max(1, count))