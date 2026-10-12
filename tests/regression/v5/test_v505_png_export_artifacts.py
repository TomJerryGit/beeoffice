# tests/regression/v5/test_v505_png_export_artifacts.py
"""
优化规划 §1.5 回归：PNG 序列导出必须真的写出文件，且提示基于真实结果。

原缺陷
------
`beeshow_export_mixin._export_images` 的 loadFinished 回调里写的是

    page.grab().save(...)

而 `page` 是 **QWebEnginePage** —— `grab()` 只存在于 QWidget / QWebEngineView
上（实测 `hasattr(QWebEnginePage, 'grab') is False`）。因此：
  * 必然抛 AttributeError；
  * 被 `except Exception` 吞掉，只在日志里留一行；
  * `finally` 里仍然弹出「导出成功」——**功能完全不存在却报成功**。

本文件用假 QWebEngineView 驱动真实的 `_export_images` 逻辑，断言：
  1. 正常路径确实产出 N 个 PNG 文件，且弹的是成功提示；
  2. 截图失败路径不产出文件、弹的是告警（不再假报成功）；
  3. 顺带锁住"取的是视图而不是 page"这一点（源码级断言）。

不实例化真正的 QWebEngineView，避免 offscreen 下的退出期原生崩溃
（见 docs/baseline.md §6.1）。
"""
import ast
import inspect
import textwrap

import pytest
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget

from beeoffice.plugins import beeshow_export_mixin as export_mod
from beeoffice.plugins.beeshow_constants import SLIDE_THEMES
from beeoffice.plugins.beeshow_export_mixin import ExportMixin


class _FakePage:
    """最小 page：记录 loadFinished 回调，setHtml 时同步触发。"""

    def __init__(self):
        self._callbacks = []

    def loadFinished(self):  # pragma: no cover - 仅用于暴露结构
        raise AssertionError("不应直接调用")

    class _Signal:
        def __init__(self, owner):
            self._owner = owner

        def connect(self, cb):
            self._owner._callbacks.append(cb)

    def signal(self):
        return self._Signal(self)


class _FakeView:
    """假 QWebEngineView：grab() 产出真实 QPixmap，setHtml 同步完成。"""

    null_pixmap = False

    def __init__(self):
        self._page = _FakePage()
        # 让 temp.page().loadFinished.connect(...) 可用
        self._page.loadFinished = self._page.signal()
        self.deleted = False
        self.grab_calls = 0

    def page(self):
        return self._page

    def resize(self, w, h):
        pass

    def setHtml(self, html):
        for cb in list(self._page._callbacks):
            cb(True)

    def grab(self):
        self.grab_calls += 1
        if self.null_pixmap:
            return QPixmap()          # isNull() -> True，模拟截图失败
        pm = QPixmap(8, 8)
        pm.fill()
        return pm

    def deleteLater(self):
        self.deleted = True


class _Host(ExportMixin, QWidget):
    """
    承载 _export_images 所需的最小状态。

    必须是真正的 QWidget：导出逻辑会用 `QTimer(self)` 建"导出中"提示定时器，
    并以 self 作为 QMessageBox 的父窗口。用普通对象会在补丁失效后触发
    TypeError（Qt 会把它记为 event loop 异常）。
    """

    def __init__(self, slides):
        QWidget.__init__(self)
        self._slides_html = list(slides)
        self._current_theme = list(SLIDE_THEMES)[0]
        self._custom_bg = None
        self._export_views = []
        self.statuses = []

    def _get_layout_css(self) -> str:
        return ""

    def _set_status(self, msg, timeout=0):
        self.statuses.append(msg)


@pytest.fixture
def png_env(qapp, tmp_path, monkeypatch):
    """准备：假视图、假目录选择、记录对话框。"""
    info_calls, warn_calls = [], []

    monkeypatch.setattr(export_mod, "QWebEngineView", _FakeView)
    monkeypatch.setattr(
        export_mod.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(tmp_path)),
    )
    monkeypatch.setattr(
        export_mod.QMessageBox, "information",
        staticmethod(lambda *a, **k: info_calls.append(a)),
    )
    monkeypatch.setattr(
        export_mod.QMessageBox, "warning",
        staticmethod(lambda *a, **k: warn_calls.append(a)),
    )
    return tmp_path, info_calls, warn_calls


def test_png_export_writes_one_file_per_slide(png_env):
    """正常路径：每个幻灯片产出一个非空 PNG。"""
    out_dir, info_calls, warn_calls = png_env
    host = _Host(["<p>第一页</p>", "<p>第二页</p>", "<p>第三页</p>"])

    host._export_images()

    produced = sorted(p.name for p in out_dir.glob("slide_*.png"))
    assert produced == ["slide_001.png", "slide_002.png", "slide_003.png"], (
        f"应产出 3 个 PNG，实际: {produced}"
    )
    for p in out_dir.glob("slide_*.png"):
        assert p.stat().st_size > 0, f"{p.name} 是空文件"

    assert info_calls, "全部成功时应给成功提示"
    assert not warn_calls, f"不应出现告警: {warn_calls}"


def test_png_export_reports_failure_instead_of_fake_success(png_env, monkeypatch):
    """
    截图失败时：不产出文件、弹告警、**不**弹成功。
    这正是原缺陷的反面（原实现哪怕一张都没写出来也报成功）。
    """
    out_dir, info_calls, warn_calls = png_env

    class _NullView(_FakeView):
        null_pixmap = True

    monkeypatch.setattr(export_mod, "QWebEngineView", _NullView)

    host = _Host(["<p>只有一页</p>"])
    host._export_images()

    assert list(out_dir.glob("slide_*.png")) == [], "失败时不应留下文件"
    assert warn_calls, "失败必须给出告警"
    assert not info_calls, "失败时绝不能报成功"


def test_success_message_states_real_count(png_env):
    """成功提示应带上真实张数，便于用户核对。"""
    out_dir, info_calls, _ = png_env
    host = _Host(["<p>a</p>", "<p>b</p>"])
    host._export_images()

    text = " ".join(str(x) for call in info_calls for x in call)
    assert "2" in text, f"成功提示里应含张数，实际: {text}"


def test_export_uses_view_grab_not_page_grab():
    """
    用 AST 锁住这个具体缺陷：必须对**视图**取图。

    不能用纯文本搜索——方法内部有解释该缺陷的注释（其中会出现
    `page.grab()` 字样），文本断言会被注释误导。这里只检查真正的调用节点。

    `QWebEnginePage` 上根本没有取图能力（实测 hasattr 为 False），
    一旦回退成对 page 取图，本断言立刻失败。
    """
    src = textwrap.dedent(inspect.getsource(ExportMixin._export_images))
    tree = ast.parse(src)

    grab_receivers = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "grab"):
            receiver = node.func.value
            grab_receivers.append(getattr(receiver, "id", type(receiver).__name__))

    assert "view" in grab_receivers, (
        f"应对视图取图，实际调用接收者: {grab_receivers}"
    )
    assert "page" not in grab_receivers, (
        f"不应再对 QWebEnginePage 取图，实际: {grab_receivers}"
    )

    # 必须检查取图结果是否为空，否则失败会被当成成功
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert "isNull" in attrs, "应检查 pixmap 是否为空（isNull）"
    assert "save" in attrs, "应检查 save() 的返回值"


def test_export_cleans_up_view_references(png_env):
    """导出结束后不应在 _export_views 里留下引用（原实现会泄漏 WebEngine 视图）。"""
    out_dir, _, _ = png_env
    host = _Host(["<p>a</p>"])
    host._export_images()
    assert host._export_views == []


def test_loading_hint_is_cancelled_when_export_finishes(png_env):
    """
    "导出中" 提示必须在导出完成时被停掉。

    原先该定时器建在**循环之后**，而快速渲染下 capture() 在循环里就已跑完，
    停表语句因此是空操作 → 导出结束 3 秒后仍会弹「正在生成图片，请稍候…」，
    提示与事实相反；在 headless/自动化环境里这个模态框会把进程卡死
    （实测 pytest 超时）。
    """
    out_dir, info_calls, warn_calls = png_env
    host = _Host(["<p>第一页</p>", "<p>第二页</p>"])
    host._export_images()

    timer = getattr(host, "_export_hint_timer", None)
    assert timer is not None, "应建立提示定时器"
    assert not timer.isActive(), (
        "导出已完成，'导出中'提示定时器仍在计时——导出后会弹出误导提示"
    )


def test_loading_hint_fires_while_export_still_running(png_env):
    """
    反面：若导出很慢（快照尚未完成），提示定时器应处于活动状态，
    即"还在导出"时提示是合理且必要的。
    """
    out_dir, _, _ = png_env
    host = _Host(["<p>a</p>", "<p>b</p>"])

    # 让假视图不回调 loadFinished，模拟"渲染还没完成"
    class _PendingView(_FakeView):
        def setHtml(self, html):
            pass   # 不触发 capture

    import beeoffice.plugins.beeshow_export_mixin as em
    orig = em.QWebEngineView
    em.QWebEngineView = _PendingView
    try:
        host._export_images()
    finally:
        em.QWebEngineView = orig

    assert host._export_hint_timer.isActive(), (
        "导出尚未完成时，'导出中'提示应保持活动"
    )
    host._export_hint_timer.stop()   # 清理，避免测试后弹出模态框
