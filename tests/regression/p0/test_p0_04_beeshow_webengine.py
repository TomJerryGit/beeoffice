# tests/test_p0_regression/test_p0_04_beeshow_webengine.py
"""
P0-4 回归：蜜演导出 PDF / 图片序列时应保持 QWebEngineView 引用。

背景：
  原 _export_pdf / _export_images 里用局部变量 temp = QWebEngineView()，
  函数返回后 temp 被 GC，导致异步的 printToPdf / grab 失败。
  表现为"随机失败"——取决于 GC 时机。

修复：
  新增 self._export_views = []，所有临时视图 append 进去，
  渲染回调完成后再 remove + deleteLater。
  closeEvent 兜底清理残留视图。

测试策略：
  1. 结构断言：_export_views 是 list，__init__ 后为空
  2. 行为断言：调 _export_pdf 后，_export_views 里应有 1 个 QWebEngineView
     （若改回局部变量，这里会是空列表）
  3. closeEvent 清理断言
"""


def test_export_views_initialized_as_list(beeshow_view):
    """P0-4：_export_views 应是 list，初始为空。"""
    assert hasattr(beeshow_view, "_export_views")
    assert isinstance(beeshow_view._export_views, list)
    assert beeshow_view._export_views == []


def test_export_pdf_holds_view_reference(
    beeshow_view, monkeypatch, tmp_path
):
    """
    P0-4：_export_pdf 期间应把临时 QWebEngineView 放入 _export_views。

    若改回局部变量实现，_export_views 在调用后仍为空，本测试失败。
    """
    from PySide6.QtWidgets import QFileDialog
    from PySide6.QtWebEngineWidgets import QWebEngineView

    out = tmp_path / "test.pdf"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (str(out), "")),
    )

    beeshow_view._slides_html = ["<h1>A</h1>"]

    # 调用 _export_pdf —— 异步 loadFinished 在测试环境不一定触发，
    # 因此 _export_views 里应仍有 1 个（尚未清理）
    beeshow_view._export_pdf()

    assert len(beeshow_view._export_views) >= 1, (
        "P0-4：_export_pdf 应立即把临时 view 放入 _export_views，"
        "否则视图会在函数返回后被 GC"
    )
    assert isinstance(beeshow_view._export_views[0], QWebEngineView)

    # 手动清理，避免 WebEngine profile 警告
    for v in list(beeshow_view._export_views):
        try:
            v.setParent(None)
            v.deleteLater()
        except Exception:
            pass
    beeshow_view._export_views.clear()


def test_close_event_clears_export_views(beeshow_view, qtbot):
    """P0-4：closeEvent 应清理残留的导出视图。"""
    from PySide6.QtGui import QCloseEvent
    from PySide6.QtWebEngineWidgets import QWebEngineView

    # 手动塞一个残留 view
    tmp_view = QWebEngineView()
    beeshow_view._export_views.append(tmp_view)

    # 直接触发 closeEvent，不真正关闭 widget
    beeshow_view.closeEvent(QCloseEvent())
    qtbot.wait(50)

    assert beeshow_view._export_views == [], (
        "P0-4：closeEvent 应清空 _export_views"
    )