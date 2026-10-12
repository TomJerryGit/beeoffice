# tests/regression/v5/test_v505_chunk_loader_thread_safety.py
"""
优化规划 §2.4 回归：分块加载的线程安全与进度可见性。

原缺陷（两处，均已实测确认）
-----------------------------
1. **工作线程修改模型**
   `ChunkLoader` 是 QThread，`run()` 直接调用 `model.load_chunk()`，
   也就是在**工作线程**里写 `_loaded_df` / `_loaded_chunks` / `_is_streaming`。
   后果：
     - 与主线程的单元格编辑竞争：用户刚输入的值可能被 `pd.concat` 的
       结果整体覆盖（丢失更新）；
     - `set_full_dataframe()` 会重新绑定 `_loaded_chunks`，工作线程持有旧集合，
       已加载的块被"遗忘"而重复加载。
   修复：拆成 `build_chunk()`（纯读取，工作线程可用）与
   `apply_chunk()`（写模型，只能在主线程），工作线程改为发
   `chunk_ready(ci, df)`，由主线程槽函数合并。

2. **`ChunkLoader.progress` 声明了但从未 emit**
   它唯一的消费者 `beesheet_ui_mixin` → `_on_loading_progress` 负责显示
   进度条，而进度条创建时是 `setVisible(False)`。于是流式加载期间
   **用户完全看不到进度**，`_on_loading_progress` 是死代码。
   修复：按"本批已处理块数 / 本批总块数"在线程本地计数并真的 emit。

`all_loaded` 的判定也从工作线程（原先读 `model.loading_progress`）
移到主线程（`_on_chunk_ready` 里依据 `model.is_streaming`）。
"""
import threading
import time

import pandas as pd
import pytest
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

from beeoffice.plugins.beesheet_loaders import ChunkLoader
from beeoffice.plugins.beesheet_model import SheetDataModel


MAIN_IDENT = None  # 在 fixture 里填充


def _pump_until(predicate, timeout=10.0):
    """跑事件循环直到条件成立。"""
    app = QApplication.instance()
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    app.processEvents()
    return predicate()


@pytest.fixture(autouse=True)
def _record_main_thread(qapp):
    global MAIN_IDENT
    MAIN_IDENT = threading.get_ident()
    yield


@pytest.fixture
def big_model(qapp):
    """> 2 个分块的模型，进入流式加载状态。"""
    rows = SheetDataModel.CHUNK_SIZE * 2 + 100
    df = pd.DataFrame({f"c{i}": range(rows) for i in range(3)})
    model = SheetDataModel()
    model.set_full_dataframe(df)
    assert model.is_streaming, "该模型应处于流式加载状态"
    return model


# ==================== 1. 模型层：读与写分离 ====================

def test_build_chunk_does_not_mutate_model(big_model):
    before_chunks = set(big_model._loaded_chunks)
    before_len = len(big_model._loaded_df)

    chunk = big_model.build_chunk(1)

    assert chunk is not None and len(chunk) > 0
    assert big_model._loaded_chunks == before_chunks, "build_chunk 不应写 _loaded_chunks"
    assert len(big_model._loaded_df) == before_len, "build_chunk 不应写 _loaded_df"


def test_apply_chunk_merges_and_is_idempotent(big_model):
    chunk = big_model.build_chunk(1)
    assert big_model.apply_chunk(1, chunk) is True
    assert 1 in big_model._loaded_chunks

    # 重复应用同一块不应再次合并
    assert big_model.apply_chunk(1, chunk) is False
    # 空块不应被合并
    assert big_model.apply_chunk(2, None) is False


def test_load_chunk_still_works(big_model):
    """保留的同步接口行为不变。"""
    assert big_model.load_chunk(1) is True
    assert big_model.load_chunk(1) is False        # 重复
    assert big_model.load_chunk(9999) is False     # 越界


# ==================== 2. 工作线程不得写模型 ====================

def test_worker_does_not_touch_model_without_main_thread_consumer(big_model):
    """
    只启动加载器、**不连接** chunk_ready：模型必须一点都没被改。

    这是"工作线程改模型"的直接反证。
    """
    before_chunks = set(big_model._loaded_chunks)
    before_len = len(big_model._loaded_df)

    loader = ChunkLoader(big_model)
    loader.add_chunks({1, 2})
    assert _pump_until(
        lambda: not loader._pending_chunks, timeout=10
    ), "加载器未处理完待加载分块"
    loader.stop()
    loader.wait(2000)

    assert big_model._loaded_chunks == before_chunks, (
        "工作线程不应修改 _loaded_chunks"
    )
    assert len(big_model._loaded_df) == before_len, (
        "工作线程不应修改 _loaded_df"
    )


def test_model_mutation_happens_on_main_thread(big_model):
    """
    模拟视图接线：chunk_ready → 主线程 apply_chunk。
    断言合并发生在主线程，而取数据发生在工作线程。
    """
    build_threads = []
    apply_threads = []

    def spy_build(ci):
        build_threads.append(threading.get_ident())
        return _real_build(ci)

    def spy_apply(ci, df):
        apply_threads.append(threading.get_ident())
        return _real_apply(ci, df)

    _real_build = big_model.build_chunk
    _real_apply = big_model.apply_chunk
    big_model.build_chunk = spy_build
    big_model.apply_chunk = spy_apply

    class Host(QObject):
        """等价于 BeeSheetView 的接线（主线程对象）。"""

        def __init__(self):
            super().__init__()
            self.loader = ChunkLoader(big_model, self)
            self.loader.chunk_ready.connect(self.on_ready)

        def on_ready(self, ci, df):
            if big_model.apply_chunk(ci, df):
                big_model.layoutChanged.emit()

    host = Host()
    host.loader.add_chunks({1, 2})
    assert _pump_until(
        lambda: not host.loader._pending_chunks and len(apply_threads) >= 2,
        timeout=10,
    ), f"未完成合并：apply_threads={apply_threads}"
    host.loader.stop()
    host.loader.wait(2000)

    assert build_threads, "应调用过 build_chunk"
    assert all(t == MAIN_IDENT for t in apply_threads), (
        f"模型合并不在主线程！apply_threads={apply_threads}, 主线程={MAIN_IDENT}"
    )
    assert any(t != MAIN_IDENT for t in build_threads), (
        "取数据应在工作线程进行（否则等于没做后台加载）"
    )


# ==================== 3. progress 必须真的发出（死信号回归） ====================

def test_progress_signal_is_actually_emitted(big_model):
    """
    原缺陷：`ChunkLoader.progress` 声明了但从不 emit，
    导致进度条永远隐藏、`_on_loading_progress` 是死代码。
    """
    values = []

    class Host(QObject):
        def __init__(self):
            super().__init__()
            self.loader = ChunkLoader(big_model, self)
            self.loader.progress.connect(values.append)
            self.loader.chunk_ready.connect(
                lambda ci, df: big_model.apply_chunk(ci, df)
            )

    host = Host()
    host.loader.add_chunks({1, 2})
    assert _pump_until(lambda: values and values[-1] >= 1.0, timeout=10), (
        f"progress 未被发出或未到 1.0：{values}"
    )
    host.loader.stop()
    host.loader.wait(2000)

    assert values, "progress 一次都没有发出（死信号缺陷复发）"
    assert all(0.0 <= v <= 1.0 for v in values), f"进度值越界: {values}"
    assert values[-1] == pytest.approx(1.0), "结束时进度应为 1.0（用于隐藏进度条）"


def test_loader_emits_chunk_ready_with_data(big_model):
    received = []

    class Host(QObject):
        def __init__(self):
            super().__init__()
            self.loader = ChunkLoader(big_model, self)
            self.loader.chunk_ready.connect(
                lambda ci, df: received.append((ci, df))
            )

    host = Host()
    host.loader.add_chunks({1})
    assert _pump_until(lambda: len(received) >= 1, timeout=10), "未收到 chunk_ready"
    host.loader.stop()
    host.loader.wait(2000)

    ci, df = received[0]
    assert ci == 1
    assert df is not None and len(df) == SheetDataModel.CHUNK_SIZE


# ==================== 4. 视图层：进度条真的会显示 ====================

def test_view_progress_bar_reacts_to_progress(qtbot):
    """
    用真实 BeeSheetView 验证：进度 < 1.0 时进度条显示，= 1.0 时隐藏。

    注意用 `isHidden()` 而不是 `isVisible()`：`isVisible()` 要求整条祖先链
    都可见，而测试里窗口从未 show()，因此它恒为 False，无法区分
    "被显式隐藏"与"父窗口没显示"。`isHidden()` 只反映显式隐藏状态。

    原缺陷下这个测试会失败——因为 progress 从不发出，
    `_on_loading_progress` 从不被调用，进度条一直处于显式隐藏状态。
    """
    from beeoffice.plugins.beesheet import BeeSheetView

    view = BeeSheetView()
    qtbot.addWidget(view)

    assert view._progress_bar.isHidden() is True, "初始应被显式隐藏"

    view._on_loading_progress(0.5)
    assert view._progress_bar.isHidden() is False, "加载中进度条不应处于隐藏状态"
    assert view._progress_bar.value() == 50

    view._on_loading_progress(1.0)
    assert view._progress_bar.isHidden() is True, "加载完成应隐藏"


def test_view_has_chunk_ready_wired_to_main_thread_handler(qtbot):
    """视图必须把 chunk_ready 接到 _on_chunk_ready（而不是直接改模型）。"""
    from beeoffice.plugins.beesheet import BeeSheetView

    view = BeeSheetView()
    qtbot.addWidget(view)

    assert hasattr(view, "_on_chunk_ready"), "缺少主线程合并槽函数"
    # 加载器不应再有旧的 all_loaded / chunk_loaded 连接
    assert not hasattr(view._chunk_loader, "all_loaded"), (
        "all_loaded 已改为主线程判定，不应再是加载器信号"
    )
