# tests/regression/v5/test_v505_async_callback_thread_affinity.py
"""
优化规划 §2.3 回归：异步回调必须在**主线程**执行。

结论：**本代码库不需要修改**——实测两条异步路径的回调本来就在主线程。
本文件的作用是把这条不变量锁住，防止将来被破坏。

为什么会有"回调跑到工作线程"的担忧
----------------------------------
`AsyncTaskManager.run(..., on_result=lambda v: editor.set_content(v))` 里的
回调是**普通 Python 可调用对象**（lambda / 闭包），没有 QObject 作为接收者。
Qt 的连接语义在这种情况下取决于发送者的线程归属：`WorkerSignals` 与各 QThread
对象都是**在主线程创建**的，因此工作线程 emit 时 AutoConnection 判定为
"跨线程"，走队列投递，最终在主线程的事件循环里执行回调。

实测（本文件就是把这些实测固化成断言）：

| 路径 | 机制 | on_result / on_finished 等回调线程 |
|---|---|---|
| `AsyncTaskManager.run` | QRunnable + WorkerSignals | 主线程 ✅ |
| `LargeFileLoader` | QThread + 裸闭包回调 | 主线程 ✅ |
| `ChunkLoader` | QThread | 主线程 ✅（另有专项测试） |

风险点（值得知道）：这条不变量依赖"信号对象在主线程创建"。如果哪天有人
在工作线程里创建 `WorkerSignals`/QThread 子类实例，或调用 `moveToThread`，
连接会退化为**直接调用**，回调就真的跑在工作线程里、去改 QWidget 了。
本文件的断言会在那时失败。
"""
import threading
import time

import pytest
from PySide6.QtWidgets import QApplication

from beeoffice.async_task import AsyncTaskManager


def _pump_until(predicate, timeout=15.0):
    app = QApplication.instance()
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    # 再多跑一会儿，让队列里的其余回调送达
    end = time.time() + 0.5
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)
    return predicate()


@pytest.fixture
def main_ident(qapp):
    return threading.get_ident()


# ==================== AsyncTaskManager ====================

def test_async_task_callbacks_run_on_main_thread(main_ident):
    seen = {}

    AsyncTaskManager.run(
        lambda: 42,
        on_started=lambda: seen.setdefault("started", threading.get_ident()),
        on_result=lambda v: seen.update(result=v, result_ident=threading.get_ident()),
        on_finished=lambda: seen.setdefault("finished", threading.get_ident()),
    )
    assert _pump_until(lambda: "finished" in seen), "回调未送达"

    assert seen.get("result") == 42
    for key in ("started", "result_ident", "finished"):
        assert seen.get(key) == main_ident, (
            f"{key} 不在主线程执行：{seen.get(key)} != {main_ident}"
        )


def test_async_task_error_callback_runs_on_main_thread(main_ident):
    seen = {}

    def boom():
        raise RuntimeError("故意失败")

    AsyncTaskManager.run(
        boom,
        on_error=lambda msg: seen.update(msg=msg, ident=threading.get_ident()),
    )
    assert _pump_until(lambda: "ident" in seen), "error 回调未送达"

    assert seen["ident"] == main_ident, (
        f"on_error 不在主线程执行：{seen['ident']} != {main_ident}"
    )
    assert "故意失败" in seen["msg"]


def test_work_function_runs_off_main_thread(main_ident):
    """回调在主线程，但**工作函数**必须在别的线程（否则异步没有意义）。"""
    seen = {}

    AsyncTaskManager.run(
        lambda: seen.setdefault("work", threading.get_ident()) or 1
    )
    assert _pump_until(lambda: "work" in seen), "工作函数未执行"

    assert seen["work"] != main_ident, "工作函数竟在主线程执行，异步失效"


# ==================== QThread 型 worker ====================

def test_large_file_loader_callbacks_run_on_main_thread(main_ident, tmp_path):
    """
    真实场景：`load_large_file()` 用**裸闭包**连接这些信号，
    闭包里直接操作 `self._progress_bar` / `self.table_view.setModel()` /
    `QMessageBox`。若它们跑在工作线程，就是跨线程操作 QWidget。
    """
    from beeoffice.plugins.beesheet_loaders import LargeFileLoader

    csv_path = tmp_path / "big.csv"
    with open(csv_path, "w", encoding="utf-8") as fh:
        fh.write("a,b\n")
        for i in range(1500):
            fh.write(f"{i},{i * 2}\n")

    seen = {}
    loader = LargeFileLoader(str(csv_path), chunk_size=300)
    loader.chunk_ready.connect(
        lambda *a: seen.setdefault("chunk_ready", threading.get_ident())
    )
    loader.progress_updated.connect(
        lambda p: seen.setdefault("progress_updated", threading.get_ident())
    )
    loader.finished_loading.connect(
        lambda df: seen.setdefault("finished_loading", threading.get_ident())
    )
    loader.error_occurred.connect(
        lambda e: seen.setdefault("error_occurred", threading.get_ident())
    )
    loader.start()

    assert _pump_until(
        lambda: "finished_loading" in seen or "error_occurred" in seen
    ), "加载未结束"
    loader.wait(3000)

    assert "error_occurred" not in seen, "加载意外失败"
    assert seen.get("finished_loading") == main_ident, (
        f"finished_loading 不在主线程：{seen.get('finished_loading')} != {main_ident}"
    )
    if "chunk_ready" in seen:
        assert seen["chunk_ready"] == main_ident, "chunk_ready 不在主线程"


def test_chunk_loader_callbacks_run_on_main_thread(main_ident, qapp):
    """ChunkLoader 的信号消费者同样是主线程对象/裸闭包。"""
    import pandas as pd

    from beeoffice.plugins.beesheet_loaders import ChunkLoader
    from beeoffice.plugins.beesheet_model import SheetDataModel

    rows = SheetDataModel.CHUNK_SIZE * 2 + 10
    model = SheetDataModel()
    model.set_full_dataframe(
        pd.DataFrame({"a": range(rows), "b": range(rows)})
    )

    seen = {}
    loader = ChunkLoader(model)
    loader.chunk_ready.connect(
        lambda ci, df: seen.setdefault("chunk_ready", threading.get_ident())
    )
    loader.progress.connect(
        lambda p: seen.setdefault("progress", threading.get_ident())
    )
    loader.add_chunks({1})

    assert _pump_until(lambda: "progress" in seen and "chunk_ready" in seen), (
        f"回调未送达：{seen}"
    )
    loader.stop()
    loader.wait(2000)

    assert seen["chunk_ready"] == main_ident, (
        f"chunk_ready 不在主线程：{seen['chunk_ready']} != {main_ident}"
    )
    assert seen["progress"] == main_ident, (
        f"progress 不在主线程：{seen['progress']}"
    )
