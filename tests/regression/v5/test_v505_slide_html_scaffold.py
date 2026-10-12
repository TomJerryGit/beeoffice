# tests/regression/v5/test_v505_slide_html_scaffold.py
"""
优化规划 §3.3「幻灯片 HTML 模板拼接」的**安全网**：先把 6 处拼装的
**可观测产物**钉住，再谈合并。

背景
----
"幻灯片 HTML 骨架"在 6 处各写了一遍：

  | 位置 | 用途 | 额外内容 |
  |---|---|---|
  | `beeshow_export_mixin._export_pdf`   | PDF  | `@page{size:A4 landscape;margin:0}` + 每页 page-break |
  | `beeshow_export_mixin._export_html`  | HTML | `body{margin:0}` + 动态数字 JS |
  | `beeshow_export_mixin._export_images`| PNG  | 无额外（已有 `test_v505_png_export_artifacts.py` 覆盖） |
  | `beeshow_play_mixin._show_play_slide`| 播放 | 动画 CSS + 控制条 + 动态数字/形变 JS |
  | `beeshow_slide_mixin._show_slide`    | 预览 | 页码 + 动态数字/元素编辑/图片编辑 JS |
  | `beeshow_pptx_engine._wrap_html`     | PPTX | `<base href>` + `.slide{1280x960}` |

为什么这个文件很重要
--------------------
这项消重此前一直没做，理由是"预览/播放要真实 `QWebEngineView` 才能观察，风险高"。
本文件用**轻量 mixin 宿主 + 假视图**把 6 处（PNG 除外，见既有文件）的 HTML
都捕获下来 —— 于是合并前后可以逐项比对，风险才降到可接受。

注意：不要构造真实 `BeeShowView`/`QWebEngineView`。除了慢，本会话沙箱禁止命名
管道会让 Chromium 在 `setHtml()` 处 FATAL 崩溃（见 docs/baseline.md §6.1）。
"""
import types

import pytest

from beeoffice.plugins.beeshow_export_mixin import SLIDE_THEMES

LAYOUT_MARK = "/*LAYOUT_CSS_MARK*/"
THEME_KEY = next(iter(SLIDE_THEMES))


class _Signal:
    def connect(self, *args, **kwargs):
        pass


class _Page:
    """PDF 路径需要 page().loadFinished.connect + printToPdf。"""

    def __init__(self):
        self.loadFinished = _Signal()

    def printToPdf(self, *args, **kwargs):  # noqa: N802
        pass


class _Capture:
    """只记录 setHtml 收到内容的假视图。"""

    def __init__(self, *args, **kwargs):
        self.html = None

    def setHtml(self, html, *args, **kwargs):  # noqa: N802 - Qt 命名
        self.html = html

    def resize(self, *args, **kwargs):
        pass

    def page(self):
        return _Page()


class _Combo:
    """播放路径需要 _anim_combo.currentText()。"""

    def __init__(self, text="淡入"):
        self._text = text

    def currentText(self):  # noqa: N802
        return self._text

    def currentIndex(self):  # noqa: N802
        return 0


class _NotesEditor:
    def blockSignals(self, *a):  # noqa: N802
        pass

    def setPlainText(self, *a):  # noqa: N802
        pass


# ==================== 公共断言 ====================

def _assert_scaffold(html, *, slide_text, require_layout=True):
    """6 处都应满足的骨架特征。"""
    assert html, "没有生成 HTML"
    assert html.startswith("<!DOCTYPE html><html><head>"), (
        f"骨架开头不对: {html[:60]!r}"
    )
    assert 'charset="utf-8"' in html, "缺少 charset（中文会乱码）"
    assert "<style>" in html and "</style></head>" in html, "缺少 <style> 块"
    assert "class=\"slide\"" in html or "class='slide'" in html, (
        "缺少 .slide 容器"
    )
    if require_layout:
        # PPTX 引擎只接收 theme_css，没有版式 CSS（它的画布是固定的 1280x960）
        assert LAYOUT_MARK in html, "版式 CSS 没有被拼进去"
    assert SLIDE_THEMES[THEME_KEY]["css"] in html, "主题 CSS 没有被拼进去"
    assert html.rstrip().endswith("</html>"), "骨架结尾不对"
    if slide_text:
        assert slide_text in html, f"幻灯片内容 {slide_text!r} 没有被拼进去"


# ==================== 1. PDF 导出 ====================

@pytest.fixture
def export_host(qtbot, monkeypatch):
    from PySide6.QtWidgets import QWidget

    from beeoffice.plugins import beeshow_export_mixin as em

    class _Host(em.ExportMixin, QWidget):
        def __init__(self):
            QWidget.__init__(self)

        def _get_layout_css(self):
            return LAYOUT_MARK

    host = _Host()
    qtbot.addWidget(host)
    host._slides_html = ["<p>SLIDE_A</p>", "<p>SLIDE_B</p>"]
    host._current_theme = THEME_KEY
    host._custom_bg = ""
    host._export_views = []

    monkeypatch.setattr(em, "QWebEngineView", _Capture)
    monkeypatch.setattr(
        em.QMessageBox, "information", staticmethod(lambda *a, **k: None)
    )
    monkeypatch.setattr(
        em.QMessageBox, "warning", staticmethod(lambda *a, **k: None)
    )
    return host


def _captured(monkeypatch, host, tmp_path, method_name, out_name):
    from beeoffice.plugins import beeshow_export_mixin as em

    out = tmp_path / out_name
    monkeypatch.setattr(
        em.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (str(out), "")),
    )
    created = []

    class _RecordingCapture(_Capture):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            created.append(self)

    monkeypatch.setattr(em, "QWebEngineView", _RecordingCapture)
    getattr(host, method_name)()
    return created[-1].html if created else None, out


def test_export_pdf_scaffold(export_host, monkeypatch, tmp_path):
    html, _ = _captured(monkeypatch, export_host, tmp_path,
                        "_export_pdf", "out.pdf")
    _assert_scaffold(html, slide_text="SLIDE_A")
    assert "SLIDE_B" in html, "两页都应在同一份 HTML 里"
    assert "@page{size:A4 landscape;margin:0}" in html, (
        "PDF 骨架缺少 A4 横向页面设置"
    )
    assert "page-break-after:always" in html, "多页之间缺少分页"


# ==================== 2. HTML 导出 ====================

def test_export_html_scaffold(export_host, monkeypatch, tmp_path):
    html, out = _captured(monkeypatch, export_host, tmp_path,
                          "_export_html", "out.html")
    assert html is None, "HTML 导出不走 QWebEngineView（直接写文件）"
    written = out.read_text(encoding="utf-8")
    _assert_scaffold(written, slide_text="SLIDE_A")
    assert "SLIDE_B" in written
    assert "body{margin:0}" in written, "HTML 导出骨架缺少 body{margin:0}"
    assert "@page{" not in written, "HTML 导出不应带 @page（那是 PDF 的）"


# ==================== 3. 预览（SlideMixin） ====================

@pytest.fixture
def preview_host(qtbot):
    from PySide6.QtWidgets import QWidget

    from beeoffice.plugins.beeshow_slide_mixin import SlideMixin

    class _Host(SlideMixin, QWidget):
        def __init__(self):
            QWidget.__init__(self)

        def _get_layout_css(self):
            return LAYOUT_MARK

        def _update_thumbnails(self):
            pass

        def _broadcast_slide(self):
            pass

        def _save_snapshot(self):
            pass

    host = _Host()
    qtbot.addWidget(host)
    host._slides_html = ["<p>PREVIEW_SLIDE</p>", "<p>SECOND</p>"]
    host._slide_titles = ["t1", "t2"]
    host._slides_md = ["md1", "md2"]
    host._current_theme = THEME_KEY
    host._custom_bg = ""
    host._speaker_notes = []
    host._preloaded_slides = set()
    host._notes_editor = _NotesEditor()
    host._slide_label = types.SimpleNamespace(setText=lambda *a: None)
    host._preview = _Capture()
    host._current_slide = 0
    return host


def test_preview_scaffold(preview_host):
    preview_host._show_slide(0)

    html = preview_host._preview.html
    _assert_scaffold(html, slide_text="PREVIEW_SLIDE")
    assert '<div class="slide-number">1/2</div>' in html, (
        "预览应显示页码 当前/总数"
    )


def test_preview_page_number_follows_index(preview_host):
    preview_host._show_slide(1)
    assert '<div class="slide-number">2/2</div>' in preview_host._preview.html


# ==================== 4. 播放（PlayMixin） ====================

@pytest.fixture
def play_host(qtbot):
    from PySide6.QtWidgets import QWidget

    from beeoffice.plugins.beeshow_play_mixin import PlayMixin

    class _Host(PlayMixin, QWidget):
        def __init__(self):
            QWidget.__init__(self)

        def _get_layout_css(self):
            return LAYOUT_MARK

        def _broadcast_slide(self):
            pass

    host = _Host()
    qtbot.addWidget(host)
    host._slides_html = ["<p>PLAY_SLIDE</p>"]
    host._current_slide = 0
    host._current_theme = THEME_KEY
    host._custom_bg = ""
    host._play_window = _Capture()
    host._anim_combo = _Combo()
    import time as _time

    host._start_time = _time.time()
    host._paused = False
    host._elapsed_before_pause = 0.0
    return host


def test_play_scaffold(play_host):
    play_host._show_play_slide()

    html = play_host._play_window.html
    _assert_scaffold(html, slide_text="PLAY_SLIDE")


# ==================== 5. PPTX（纯函数） ====================

def test_pptx_wrap_html_scaffold():
    from beeoffice.plugins.beeshow_pptx_engine import PPTXEngine

    html = PPTXEngine()._wrap_html(
        "<p>PPTX_FRAGMENT</p>",
        theme_css=SLIDE_THEMES[THEME_KEY]["css"],
        bg_color="#FFFFFF",
        base_href="file:///C:/tmp/media/",
    )
    _assert_scaffold(html, slide_text="PPTX_FRAGMENT", require_layout=False)
    assert '<base href="file:///C:/tmp/media/">' in html, (
        "PPTX 骨架必须注入 <base href>，否则相对路径图片解析不到"
    )
    assert ".slide{width:1280px;height:960px;}" in html, (
        "PPTX 测量用固定画布尺寸丢失"
    )
    assert "body{margin:0" in html


def test_pptx_wrap_html_without_base_href():
    from beeoffice.plugins.beeshow_pptx_engine import PPTXEngine

    html = PPTXEngine()._wrap_html("<p>x</p>", theme_css="", bg_color="#000")
    assert "<base" not in html, "没有 base_href 时不应注入空的 <base>"
    assert "background:#000" in html


# ==================== 6. 反向确认：这套断言确实有牙齿 ====================

def test_scaffold_assertion_can_fail():
    """
    把骨架断言喂给一份"被改坏"的 HTML，它必须报错 ——
    否则这些测试会退化成恒真（§4.2 的教训）。
    """
    broken = (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        "<style>body{margin:0}</style></head>"
        '<body><div class="slide">x</div></body></html>'
    )
    with pytest.raises(AssertionError):
        _assert_scaffold(broken, slide_text="x")


def test_scaffold_assertion_can_fail_on_missing_slide_content():
    """内容没被拼进去时也必须失败。"""
    from beeoffice.plugins.beeshow_pptx_engine import PPTXEngine

    html = PPTXEngine()._wrap_html(
        "<p>REAL</p>", theme_css="", bg_color="#000"
    )
    with pytest.raises(AssertionError):
        _assert_scaffold(html, slide_text="NOT_THERE", require_layout=False)
