# tests/regression/v5/test_v505_sync_guard.py
"""
优化规划 §3.1 附带发现：云同步的"进行中"守卫**从未生效**。

原缺陷
------
`app._sync_now()` 用

    if self._sync_worker is not None:
        try:
            if self._sync_worker.isRunning():      # ← AsyncTaskManager 的返回值
                ... 提示"同步正在进行中"; return
        except Exception:
            pass                                   # ← 把 AttributeError 吞掉

来判断"是否已经在同步"。但 `AsyncTaskManager.run()` 返回的是
`Worker`（QRunnable），**没有 `isRunning()`** —— 实测确认：

    >>> Worker(lambda: 1).__class__.__mro__[1]  → QRunnable
    >>> hasattr(Worker(lambda: 1), "isRunning") → False

因此该判断每次都抛 AttributeError 并被宽 `except` 静默吞掉，守卫永不生效：
重复点击「立即同步」（或自动同步与手动同步叠加）会**并发启动多次上传**。

修复：改用显式布尔标记 `_sync_in_progress`（进入前置位、结果/错误回调里清除）。

本文件用"桩掉任务启动"的方式做**确定性**行为测试：不起线程、不弹对话框。
"""
import inspect

import pytest

from beeoffice.async_task import AsyncTaskManager, Worker


# ==================== 根因 ====================

def test_async_worker_has_no_isrunning():
    """
    固化根因：QRunnable 没有 isRunning()。若哪天它有了，本测试会失败，
    提醒我们重新审视 `_sync_now` 的守卫实现方式。
    """
    worker = Worker(lambda: None)
    assert not hasattr(worker, "isRunning"), (
        "Worker 现在有 isRunning 了 —— 请重新评估 _sync_now 的守卫"
    )


def test_sync_now_does_not_use_isrunning():
    """修复后不应再对 QRunnable 调 isRunning()。"""
    from beeoffice.app import BeeApp

    src = inspect.getsource(BeeApp._sync_now)
    assert "isRunning" not in src, (
        "仍在调用 QRunnable 上不存在的 isRunning()，守卫会再次失效"
    )
    assert "_sync_in_progress" in src, "应改用显式标记"


def test_sync_flag_is_initialised():
    """标记必须在 __init__ 初始化，否则第一次调用就 AttributeError。"""
    from beeoffice.app import BeeApp

    assert "_sync_in_progress" in inspect.getsource(BeeApp.__init__)


# ==================== 行为：守卫真的会拦住 ====================

@pytest.fixture
def sync_env(app, monkeypatch):
    """
    准备：桩掉云存储与任务启动，记录"是否真的发起了同步"。
    """
    from PySide6.QtWidgets import QMessageBox

    from beeoffice import cloud

    started = []
    infos = []

    class _Storage:
        def upload(self, local, remote):
            return True

    monkeypatch.setattr(cloud, "get_cloud_storage", lambda: _Storage())
    monkeypatch.setattr(
        AsyncTaskManager, "run",
        staticmethod(lambda fn, **k: started.append(True) or object()),
    )
    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(
            QMessageBox, name,
            staticmethod(lambda *a, **k: infos.append(a)),
        )

    app._sync_in_progress = False
    yield app, started, infos
    app._sync_in_progress = False


def test_guard_blocks_reentry(sync_env):
    """标记为"正在同步"时必须直接返回，不发起新的同步。"""
    app, started, infos = sync_env
    app._sync_in_progress = True

    app._sync_now()

    assert started == [], "正在同步时不应再次发起同步（原缺陷会并发上传）"
    assert infos, "应提示「同步正在进行中」"


def test_sync_proceeds_when_idle(sync_env):
    """空闲时应真正发起同步并把标记置位。"""
    app, started, infos = sync_env
    app._sync_in_progress = False

    app._sync_now()

    assert started == [True], "空闲时应发起同步"
    assert app._sync_in_progress is True, "发起后应把标记置位"


def test_second_call_after_first_is_blocked(sync_env):
    """连续两次调用：第二次必须被拦住（这正是原缺陷会并发上传的场景）。"""
    app, started, infos = sync_env

    app._sync_now()      # 第一次：发起
    app._sync_now()      # 第二次：应被守卫拦住

    assert started == [True], f"应只发起一次，实际 {len(started)} 次"
    assert infos, "第二次应给出「同步正在进行中」提示"


def test_flag_cleared_on_result(sync_env, monkeypatch):
    """成功回调必须清除标记，否则同步会永久卡在"进行中"。"""
    from beeoffice.app import BeeApp

    src = inspect.getsource(BeeApp._sync_now)
    # on_result 与 on_error 都应清除标记
    assert src.count("_sync_in_progress = False") >= 2, (
        "on_result / on_error 都应清除 _sync_in_progress"
    )
