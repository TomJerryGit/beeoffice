# tests/test_p0_regression/test_p0_15_large_file_cancel.py
"""
P0-15 回归：大文件分块加载应支持取消。

背景：
  原 LargeFileLoader 无中断机制，大文件（100MB+）加载时用户
  无法中途取消，只能强制关闭窗口。

修复：
  1. LargeFileLoader 新增 cancelled 信号
  2. run() 加载完成后检查 isInterruptionRequested()，
     是则发 cancelled 而非 finished
  3. _load_csv / _load_excel 每处理一块前检查中断
  4. beesheet.py 新增 _cancel_load_btn 与 _cancel_large_file_load 方法

测试策略：
  1. 单元：LargeFileLoader 有 cancelled 信号
  2. 集成：造大 CSV，启动 loader，收到若干块后请求中断，
           用 qtbot.waitSignal 等 cancelled
  3. 边界：BeeSheetView._cancel_large_file_load 无 loader 时不崩
"""
import pytest


# ==================== 信号存在性 ====================

def test_large_file_loader_has_cancelled_signal(qapp):
    """P0-15：LargeFileLoader 应有 cancelled 信号。"""
    from beeoffice.plugins.beesheet_loaders import LargeFileLoader

    assert hasattr(LargeFileLoader, "cancelled"), (
        "P0-15：LargeFileLoader 未定义 cancelled 信号。"
        "用户将无法取消大文件加载"
    )


def test_beesheet_view_has_cancel_widgets(qtbot):
    """P0-15：BeeSheetView 应有取消按钮与取消方法。"""
    from beeoffice.plugins.beesheet import BeeSheetView

    view = BeeSheetView()
    qtbot.addWidget(view)
    try:
        assert hasattr(view, "_cancel_large_file_load"), (
            "P0-15：BeeSheetView 缺少 _cancel_large_file_load 方法"
        )
        assert hasattr(view, "_cancel_load_btn"), (
            "P0-15：BeeSheetView 缺少 _cancel_load_btn 按钮"
        )
    finally:
        view.close()


# ==================== 边界：无 loader 时调用 ====================

def test_cancel_without_loader_does_not_crash(qtbot):
    """P0-15：无 loader 时调 _cancel_large_file_load 不应崩溃。"""
    from beeoffice.plugins.beesheet import BeeSheetView

    view = BeeSheetView()
    qtbot.addWidget(view)
    try:
        # 初始化后 _large_file_loader 应为 None
        view._cancel_large_file_load()   # 不应抛异常
    finally:
        view.close()


# ==================== 真实取消流程 ====================

@pytest.mark.timeout(30)
def test_large_file_loader_cancel_csv(qtbot, tmp_path):
    """
    P0-15：启动 LargeFileLoader，收到若干块后请求中断，
            应发出 cancelled 信号而非 finished。
    """
    from beeoffice.plugins.beesheet_loaders import LargeFileLoader

    # 造一个足够大的 CSV（20 万行，3 列，约 5MB）
    csv_path = tmp_path / "big.csv"
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("a,b,c\n")
        for i in range(200000):
            f.write(f"{i},{i+1},{i+2}\n")

    # chunk_size 尽量小，让中断检查频繁
    loader = LargeFileLoader(str(csv_path), chunk_size=2000)

    chunks_received = []
    finished_called = []
    interrupted = [False]

    def on_chunk(df, idx, total):
        chunks_received.append(idx)
        # 收到第 3 块后请求中断
        if idx >= 2 and not interrupted[0]:
            interrupted[0] = True
            loader.requestInterruption()

    loader.chunk_ready.connect(on_chunk)
    loader.finished_loading.connect(
        lambda df: finished_called.append(True)
    )

    # 等待 cancelled 信号
    with qtbot.waitSignal(loader.cancelled, timeout=15000):
        loader.start()

    # 断言：cancelled 被触发，finished 未被触发
    assert chunks_received, "应至少收到一个 chunk_ready"
    assert not finished_called, (
        "P0-15：取消后不应发 finished_loading 信号。"
        "cancelled 和 finished 应互斥"
    )


def test_large_file_loader_normal_completion(qtbot, tmp_path):
    """
    P0-15 对照测试：不中断时，loader 应正常完成并发出 finished_loading。
    """
    from beeoffice.plugins.beesheet_loaders import LargeFileLoader

    # 造一个小的 CSV
    csv_path = tmp_path / "small.csv"
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("a,b,c\n")
        for i in range(500):
            f.write(f"{i},{i+1},{i+2}\n")

    loader = LargeFileLoader(str(csv_path), chunk_size=1000)

    # 等待 finished 信号
    with qtbot.waitSignal(
        loader.finished_loading, timeout=10000
    ) as blocker:
        loader.start()

    assert blocker.signal_triggered
    df = blocker.args[0]
    assert len(df) == 500, (
        f"P0-15：正常完成应加载 500 行，实际 {len(df)}"
    )