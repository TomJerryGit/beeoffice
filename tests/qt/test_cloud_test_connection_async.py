# -*- coding: utf-8 -*-
"""
云存储设置：测试连接不得阻塞 GUI（P1-38）

缺陷：
    `_test_connection()` 在 GUI 线程里同步调用 `requests.get(..., timeout=10)`，
    网络慢或断网时整个窗口卡死最长 10 秒。

修复：
    参数校验留在主线程，真正的网络调用交给 AsyncTaskManager 线程池，
    结果与异常都通过队列回到主线程再弹窗。
"""
import pytest

pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture
def dialog(qtbot):
    from beeoffice.cloud_settings import CloudSettingsDialog

    dlg = CloudSettingsDialog()
    qtbot.addWidget(dlg)
    yield dlg
    try:
        dlg.close()
    except Exception:
        pass


def test_schedules_network_call_on_worker(qtbot, dialog, monkeypatch):
    """点击"测试连接"只应调度任务，不直接发起网络请求。"""
    from beeoffice.async_task import AsyncTaskManager

    scheduled = []

    def fake_run(fn, *args, **kwargs):
        scheduled.append((fn, args, kwargs))

    monkeypatch.setattr(AsyncTaskManager, "run", staticmethod(fake_run))

    dialog.type_combo.setCurrentIndex(0)          # WebDAV
    dialog.url_edit.setText("https://example.com/dav")

    dialog._test_connection()

    assert scheduled, "没有通过 AsyncTaskManager 调度，说明仍在 GUI 线程同步请求"
    fn = scheduled[0][0]
    assert fn == dialog._probe_connection, f"调度的不是探测函数: {fn}"
    # 调度期间按钮应被禁用，防止用户连点发起多个请求
    assert dialog.test_btn.isEnabled() is False


def test_probe_requires_url(qtbot, dialog, monkeypatch):
    """地址为空时直接提示，不调度任务。"""
    from beeoffice.async_task import AsyncTaskManager

    scheduled = []
    monkeypatch.setattr(
        AsyncTaskManager, "run",
        staticmethod(lambda fn, *a, **k: scheduled.append(fn)),
    )
    monkeypatch.setattr(
        "PySide6.QtWidgets.QMessageBox.warning",
        staticmethod(lambda *a, **k: None),
    )

    dialog.type_combo.setCurrentIndex(0)
    dialog.url_edit.setText("")
    dialog._test_connection()

    assert not scheduled, "地址为空时不应发起网络请求"


def test_probe_function_returns_codes(monkeypatch):
    """worker 侧只返回状态码，翻译留给界面层。"""
    import requests

    class _Resp:
        status_code = 200

    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp())

    from beeoffice.cloud_settings import CloudSettingsDialog
    assert CloudSettingsDialog._probe_connection("onedrive", "tok") == "onedrive"
    assert CloudSettingsDialog._probe_connection("googledrive", "tok") == "googledrive"
