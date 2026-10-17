# -*- coding: utf-8 -*-
"""
蜜演导出验收（产物级，slow）

这两个用例替代"人工点一遍看看"：
    1. PDF 导出：等 printToPdf 真正写完，文件能被 PyMuPDF 打开且含页面文字
    2. PNG 导出：每页一张，且不是空白图

背景：
    修复前 PDF 导出在 printToPdf 之后立刻弹"成功"并 deleteLater；
    图片导出调用不存在的 page.grab()，异常被吞后仍报成功。
"""
import time

import pytest

pytest.importorskip("PySide6.QtWebEngineWidgets")
pytest.importorskip("fitz", reason="需要 PyMuPDF 校验 PDF")
pytest.importorskip("PIL", reason="需要 Pillow 校验图片非空白")

SLIDES = [
    "<h1 style='color:#FFB300'>第一页</h1><p>内容 A</p>",
    "<h1 style='color:#2196F3'>第二页</h1><p>内容 B</p>",
]


@pytest.fixture
def show_view(qtbot):
    from beeoffice.plugins.beeshow import BeeShowView

    view = BeeShowView()
    qtbot.addWidget(view)
    yield view
    try:
        view._stop_play()
    except Exception:
        pass


def _wait_until(qtbot, predicate, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        qtbot.wait(100)
    return predicate()


@pytest.fixture
def silent_dialogs(monkeypatch):
    """拦截文件对话框与消息框，避免用例被模态框卡死。"""
    from beeoffice.plugins import beeshow_export_mixin as m

    captured = {"info": [], "warning": []}
    monkeypatch.setattr(
        m.QMessageBox, "information",
        staticmethod(lambda *a, **k: captured["info"].append(a[1] if len(a) > 1 else "")),
    )
    monkeypatch.setattr(
        m.QMessageBox, "warning",
        staticmethod(lambda *a, **k: captured["warning"].append(a[1] if len(a) > 1 else "")),
    )
    return m, captured


def test_export_pdf_produces_real_pdf(qtbot, tmp_path, silent_dialogs, show_view):
    m, captured = silent_dialogs
    out = tmp_path / "out.pdf"
    m.QFileDialog.getSaveFileName = staticmethod(
        lambda *a, **k: (str(out), "PDF (*.pdf)")
    )
    # BeeShowView 内部有防抖定时器会重算 _slides_html，
    # 必须在调用前立即赋值（放在 fixture 里会被定时器清掉）。
    show_view._slides_html = list(SLIDES)

    show_view._export_pdf()

    ok = _wait_until(
        qtbot,
        lambda: out.exists() and out.stat().st_size > 1000,
        timeout=30,
    )
    assert ok, (
        f"PDF 未生成或过小。提示信息={captured['info']} 警告={captured['warning']}"
    )

    import fitz

    doc = fitz.open(str(out))
    assert doc.page_count >= 1, "PDF 页数为 0"
    text = "".join(page.get_text() for page in doc)
    assert ("第一页" in text) or ("内容 A" in text), (
        f"PDF 里没有幻灯片文字，可能是空白页。实际文本: {text[:200]!r}"
    )
    assert not captured["warning"], f"不应有失败提示: {captured['warning']}"


def test_export_images_are_not_blank(qtbot, tmp_path, silent_dialogs, show_view):
    m, captured = silent_dialogs
    m.QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: str(tmp_path))
    show_view._slides_html = list(SLIDES)

    show_view._export_images()

    ok = _wait_until(
        qtbot,
        lambda: len(list(tmp_path.glob("slide_*.png"))) >= len(SLIDES),
        timeout=60,
    )
    files = sorted(tmp_path.glob("slide_*.png"))
    assert ok, f"只导出 {len(files)} 张。提示={captured['info']} 警告={captured['warning']}"

    from PIL import Image

    for p in files:
        img = Image.open(p).convert("RGB")
        colors = img.getcolors(maxcolors=1_000_000) or []
        total = sum(n for n, _ in colors)
        # 幻灯片大部分是白底，用"非白像素占比"判断是否有真实内容，
        # 而不是数颜色种类（白底 + 标题色 + 文字色 = 3 种，很正常）。
        non_white = sum(n for n, c in colors if c != (255, 255, 255))
        ratio = non_white / max(total, 1)
        assert ratio > 0.001, (
            f"{p.name} 看起来是空白图：非白像素占比 {ratio:.4%}"
            f"（颜色数={len(colors)}）"
        )


def test_export_pptx_produces_real_slides(qtbot, tmp_path, silent_dialogs, show_view):
    """
    PPTX 导出验收（最后一个导出盲区）。

    断言：
      - 文件存在且能被 python-pptx 打开
      - 幻灯片数量与源页数一致
      - 每页至少有一个形状，且首页文字包含标题
    无 Playwright 时应走"仅文本"降级路径，仍须产出可编辑的 PPTX。
    """
    pptx = pytest.importorskip("pptx")

    m, captured = silent_dialogs
    out = tmp_path / "out.pptx"
    m.QFileDialog.getSaveFileName = staticmethod(
        lambda *a, **k: (str(out), "PowerPoint (*.pptx)")
    )
    show_view._slides_html = list(SLIDES)

    show_view._export_pptx()

    ok = _wait_until(
        qtbot,
        lambda: out.exists() and out.stat().st_size > 2000,
        timeout=60,
    )
    assert ok, (
        f"PPTX 未生成或过小。提示={captured['info']} 警告={captured['warning']}"
    )

    prs = pptx.Presentation(str(out))
    assert len(prs.slides) >= 1, "PPTX 里没有幻灯片"
    assert len(prs.slides) == len(SLIDES), (
        f"幻灯片数量不符：期望 {len(SLIDES)}，实际 {len(prs.slides)}"
    )

    texts = []
    for slide in prs.slides:
        assert len(slide.shapes) >= 1, "某页没有任何形状"
        for shape in slide.shapes:
            if shape.has_text_frame:
                texts.append(shape.text_frame.text)
    joined = "\n".join(texts)
    assert "第一页" in joined or "内容 A" in joined, (
        f"PPTX 里没有幻灯片文字，内容可能为空。实际: {joined[:200]!r}"
    )
