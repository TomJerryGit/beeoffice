# tests/fidelity/test_p0_pdf_export.py
"""
P0 修复：「导出 PDF」改走 **Qt 打印路径**，并在三个模块分流。

## 背景（我实测过）
原先三个入口都收敛到 `bee_export.export_to_pdf`，而它内部是
`from weasyprint import HTML`；**weasyprint 在 requirements.txt 里被注释掉**
（还注明 Windows 需要 GTK）→ 默认安装下必然失败：
我实测 `export_to_pdf('# 标题', out)` → 返回 **False**、**文件不存在**。
蜜写里点"导出 PDF"失败；蜜算/蜜演点它弹"当前文档不支持导出 PDF"。
而打印走 Qt `QPrinter` 一直是可用的 —— 用户只能绕道"打印→Microsoft Print to PDF"。

## 修法
三个模块各实现 `export_pdf(path)`：
· 蜜写：把要打印的 QTextDocument 打到 `PdfFormat` 的 QPrinter；
· 蜜算：复用打印用的 `_render_sheet_to()`；
· 蜜演：复用 WebEngine 的 `printToPdf`（并接 `pdfPrintingFinished` 报**真实**结果）。
`app._export_pdf` 不再要求蜜写专有的 `get_rendered_content()`，而是按模块分流。

## 本文件守的
1. **真的产出 PDF**（存在、非空、页数 ≥ 1）——而不是"调用了就算过"；
2. 三模块都有 `export_pdf`；不支持的控件给**明确提示**（且不再甩锅 WeasyPrint）；
3. 蜜演只能做类级校验（本沙箱 QtWebEngine 初始化即失败）。
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _pdf_pages(path) -> int:
    import fitz

    doc = fitz.open(str(path))
    try:
        return doc.page_count
    finally:
        doc.close()


# ==================== 1. 三个模块都提供 export_pdf ====================

def test_all_three_modules_expose_export_pdf():
    from beeoffice.plugins.beesheet import BeeSheetView
    from beeoffice.plugins.beeshow import BeeShowView
    from beeoffice.plugins.beewrite import BeeWriteEditor

    for cls in (BeeWriteEditor, BeeSheetView, BeeShowView):
        assert callable(getattr(cls, "export_pdf", None)), (
            f"{cls.__name__} 缺少 export_pdf → 全局「导出 PDF」对它仍会弹不支持"
        )


# ==================== 2. 真的产出 PDF（不依赖 WeasyPrint）====================

def test_beewrite_export_pdf_writes_a_real_file(qtbot, tmp_path):
    from beeoffice.plugins.beewrite import BeeWriteEditor

    editor = BeeWriteEditor()
    qtbot.addWidget(editor)
    target = tmp_path / "文档.pdf"
    try:
        editor.set_content("# 标题\n\n正文内容。\n\n## 第二节\n\n更多内容。")
        qtbot.wait(30)

        assert editor.export_pdf(str(target)) is True
        assert target.exists(), "export_pdf 返回 True 但没有产出文件"
        assert target.stat().st_size > 0, "产出的 PDF 是空文件"
        assert _pdf_pages(target) >= 1
    finally:
        editor.close()


def test_beesheet_export_pdf_writes_a_real_file(qtbot, tmp_path):
    from beeoffice.plugins.beesheet import BeeSheetView

    view = BeeSheetView()
    qtbot.addWidget(view)
    target = tmp_path / "表格.pdf"
    try:
        view.current_sheet_name = "测试表"
        view.model.set_full_dataframe(
            pd.DataFrame({"名称": ["甲", "乙", "丙"], "数量": [1, 2, 3]})
        )
        qtbot.wait(30)

        assert view.export_pdf(str(target)) is True
        assert target.exists() and target.stat().st_size > 0
        assert _pdf_pages(target) >= 1
    finally:
        view.close()


def test_beesheet_export_pdf_respects_fit_mode(qtbot, tmp_path):
    """导出的 PDF 页数应与**打印计划**一致（与字体无关的不变量）。"""
    from beeoffice.plugins.beesheet import BeeSheetView
    from beeoffice.plugins.beesheet_print_mixin import FIT_WIDTH

    view = BeeSheetView()
    qtbot.addWidget(view)
    target = tmp_path / "多页.pdf"
    try:
        view.current_sheet_name = "大表"
        view.model.set_full_dataframe(
            pd.DataFrame({f"c{i}": range(200) for i in range(4)})
        )
        view._print_fit = FIT_WIDTH
        qtbot.wait(30)

        assert view.export_pdf(str(target)) is True
        from PySide6.QtPrintSupport import QPrinter

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        geom = view._print_geometry(printer)
        plan = view._build_print_plan(
            view._collect_print_data(), geom["usable_w"], geom["body_h"],
            geom["px"], fit=FIT_WIDTH,
        )
        assert _pdf_pages(target) == len(plan["pages"])
    finally:
        view.close()


# ==================== 3. 全局入口按模块分流 ====================

def test_export_pdf_dispatches_to_widget(qtbot, app, monkeypatch, tmp_path):
    """有 `export_pdf` 的控件：应当**被调用**，且传的是用户选定的路径。"""
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from beeoffice.plugins.beesheet import BeeSheetView

    view = BeeSheetView()
    qtbot.addWidget(view)
    app.tab_manager.addTab(view, "蜜算")
    app.tab_manager.setCurrentWidget(view)

    target = tmp_path / "out.pdf"
    calls = []
    view.export_pdf = lambda path: calls.append(path) or True
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (str(target), "")),
    )
    warned = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: warned.append(a)))

    app._export_pdf()

    assert calls == [str(target)], f"没有把路径交给控件的 export_pdf：{calls}"
    assert not warned, f"成功却弹了警告：{warned}"
    view.close()


def test_export_pdf_without_support_gives_clear_hint(qtbot, app, monkeypatch):
    """不支持导出的控件：给明确提示，并且**不再**说"可能需要 WeasyPrint"。"""
    from PySide6.QtWidgets import QMessageBox, QWidget

    plain = QWidget()
    qtbot.addWidget(plain)
    app.tab_manager.addTab(plain, "纯文本框")
    app.tab_manager.setCurrentWidget(plain)

    shown = []
    monkeypatch.setattr(
        QMessageBox, "information",
        staticmethod(lambda parent, title, text, *a, **k: shown.append(text)),
    )

    app._export_pdf()

    assert shown, "不支持的控件应当给提示（不能静默）"
    joined = " ".join(shown)
    assert "打印" in joined, "提示里应给出可用的替代路径（打印预览）"
    assert "WeasyPrint" not in joined, "不该再把责任甩给已弃用的 WeasyPrint"
    plain.close()


def test_export_pdf_reports_failure_honestly(qtbot, app, monkeypatch, tmp_path):
    """控件返回 False 时必须提示失败（不能假装成功）。"""
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from beeoffice.plugins.beesheet import BeeSheetView

    view = BeeSheetView()
    qtbot.addWidget(view)
    app.tab_manager.addTab(view, "蜜算")
    app.tab_manager.setCurrentWidget(view)
    view.export_pdf = lambda path: False

    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (str(tmp_path / "x.pdf"), "")),
    )
    warned = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: warned.append(a)))

    app._export_pdf()

    assert warned, "export_pdf 返回 False 却没有提示失败"
    view.close()
