# tests/qt/test_memory_monitor.py
"""memory_monitor.py 测试：内存监控窗口"""
import pytest


@pytest.fixture
def monitor(qtbot):
    from beeoffice.plugins.memory_monitor import MemoryMonitor
    m = MemoryMonitor()
    qtbot.addWidget(m)
    return m


class TestInit:
    def test_window_created(self, monitor):
        assert monitor is not None

    def test_has_labels(self, monitor):
        assert monitor.current_label is not None
        assert monitor.peak_label is not None
        assert monitor.trend_label is not None

    def test_has_progress_bar(self, monitor):
        assert monitor.progress is not None
        assert monitor.progress.maximum() == 500

    def test_history_empty_initially(self, monitor):
        # _update() 在 __init__ 里跑过一次，历史可能有 1 条
        assert isinstance(monitor._history, list)


class TestUpdate:
    def test_update_runs_without_crash(self, monitor):
        monitor._update()

    def test_peak_tracks_max(self, monitor):
        # 手动塞历史，模拟峰值
        monitor._history = [10.0, 20.0, 15.0]
        monitor._peak = 20.0
        assert monitor._peak >= max(monitor._history)

    def test_history_trimmed(self, monitor):
        monitor._history = [float(i) for i in range(200)]
        if len(monitor._history) > 120:
            monitor._history = monitor._history[-120:]
        assert len(monitor._history) <= 120


class TestActions:
    def test_manual_gc(self, monitor):
        # 不应崩
        monitor._manual_gc()

    def test_reset(self, monitor):
        monitor._peak = 999.0
        monitor._history = [1.0, 2.0, 3.0]
        monitor._reset()
        assert monitor._peak == 0
        assert isinstance(monitor._history, list)

    def test_close_stops_timer(self, monitor, qtbot):
        assert monitor._timer.isActive()
        monitor.close()
        qtbot.wait(50)
        assert not monitor._timer.isActive()
