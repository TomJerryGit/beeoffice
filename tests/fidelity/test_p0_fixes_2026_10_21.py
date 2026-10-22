# tests/fidelity/test_p0_fixes_2026_10_21.py
"""
2026-10-21 GUI 实跑发现的三类 P0/P1 的回归测试：

1. **大表阶段 2 回调丢失**（P0）：`_import_file_from_path` 在工作线程执行，
   原先它在工作线程里直接 `AsyncTaskManager.run(load_full)` —— PySide6 的
   AutoConnection 会把完成回调排到"连接时所在线程"的事件循环；工作线程没有
   事件循环 → 30 万行表永远只显示首屏 1000 行。修复：`phase2_requested` 信号
   回主线程后再启动。
2. **稀疏大表样式读回**（P0）：磁盘 2.28 MB 但声明 20 万行的表，原先
   `read_view_styles` 按声明区域扫满 260 万格（119–154 s）。修复：声明行数
   ≥5 万也跳过格式读回。
3. **取消保存被报成失败**（P2）：另存为对话框取消是正常操作，状态栏应显示
   「已取消保存」而不是「保存失败」。
"""
import threading

import pandas as pd

from beeoffice.plugins.beesheet import BeeSheetView
from beeoffice.plugins.beesheet_workbook import (
    SheetData,
    WorkbookData,
)


def _fake_workbook(rows: int) -> WorkbookData:
    df = pd.DataFrame({"编号": list(range(rows)), "值": ["x"] * rows})
    return WorkbookData(
        sheets=[SheetData(name="表", df=df, original_shape=(rows, 2))],
        active="表",
    )


def test_phase2_auto_completes_from_worker_thread(qtbot, tmp_path, monkeypatch):
    """阶段 1 在工作线程跑完后，阶段 2 必须自动补全并替换模型。"""
    view = BeeSheetView()
    qtbot.addWidget(view)
    path = tmp_path / "fake.xlsx"
    path.write_bytes(b"not a real xlsx")  # 只用于路径/扩展名

    # 阶段 1 只读前 PHASE1_ROWS 行；阶段 2 读全量
    def _fake_read_workbook(_path, max_rows=None):
        rows = view.PHASE1_ROWS if max_rows == view.PHASE1_ROWS else 1000
        return _fake_workbook(rows)

    monkeypatch.setattr(
        "beeoffice.plugins.beesheet_workbook.read_workbook",
        _fake_read_workbook,
    )
    monkeypatch.setattr(view, "_should_lazy_load", lambda _p: True)
    monkeypatch.setattr(view, "_load_view_styles_from", lambda *a, **k: None)

    # 模拟产品路径：导入入口在**工作线程**执行（app._open_sheet_file 的做法）
    errors = []

    def _worker():
        try:
            view._import_file_from_path(str(path))
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    worker = threading.Thread(target=_worker, daemon=True)
    worker.start()

    qtbot.waitUntil(
        lambda: not worker.is_alive(), timeout=10000
    )
    assert not errors, errors
    assert view.model.rowCount() >= 1000, "阶段 1 应显示前 500 行"
    assert view.model.is_fully_loaded is False, "阶段 1 后应处于只读部分载入状态"

    # 关键断言：不等手动兜底，后台补全应自己完成（修复前这里永远 False）
    qtbot.waitUntil(
        lambda: view.model.is_fully_loaded and view.model.rowCount() == 1000,
        timeout=10000,
    )
    assert view.model.is_fully_loaded is True
    assert view.model.rowCount() == 1000


def test_sparse_large_sheet_skips_view_style_read(tmp_path, monkeypatch):
    """声明 20 万行的稀疏表不能触发全表样式扫描（P0-2）。"""
    view = BeeSheetView()
    path = tmp_path / "sparse.xlsx"
    path.write_bytes(b"x")

    monkeypatch.setattr(
        "beeoffice.plugins.beesheet_workbook._declared_row_count",
        lambda _p: 200_001,
    )
    called = {"n": 0}

    def _boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("稀疏大表不应读样式")

    monkeypatch.setattr(
        "beeoffice.plugins.beesheet_style_export.read_view_styles", _boom
    )
    view._load_view_styles_from(str(path))
    assert called["n"] == 0


def test_save_canceled_shows_canceled_not_failed(app):
    class _FakeWidget:
        _save_canceled = True

    app._save_widget = lambda _w: False
    app.tab_manager.currentWidget = lambda: _FakeWidget()
    app.status_label.setText("")
    app._save_current()
    assert app.status_label.text() == "已取消保存"


def test_save_failure_still_shows_failed(app):
    class _FakeWidget:
        _save_canceled = False

    app._save_widget = lambda _w: False
    app.tab_manager.currentWidget = lambda: _FakeWidget()
    app.status_label.setText("")
    app._save_current()
    assert app.status_label.text() == "保存失败"
