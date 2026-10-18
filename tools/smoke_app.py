# -*- coding: utf-8 -*-
"""
冷启动冒烟：一条命令走完"用户真正会做的前几步"。

为什么需要它（2026-10-18 的真实事故）：
    · run.bat 走系统 Python 3.8，启动即崩（logging.encoding 参数）；
    · 首次运行引导浮层挡住窗口且没有退出通道，鼠标键盘全失效。
    这两类问题单测都发现不了——单测只验证"能创建"，不验证"能用"。

本脚本做的事：
    1. 创建 QApplication + BeeApp，加载插件
    2. 依次新建蜜写 / 蜜算 / 蜜演 / PDF 批注
    3. 导出一个小 DOCX，并重新打开校验
    4. 构建命令面板
    每步打印 ✓ / ✗，任意失败则以退出码 1 结束。

用法：
    python tools/smoke_app.py            # 完整冒烟
    python tools/smoke_app.py --quick    # 只到"四个模块能新建"
"""
import sys
import tempfile
from pathlib import Path

try:
    from _console import enable_utf8_output
    enable_utf8_output()
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _silence_dialogs():
    """把模态框替换成记录器，避免冒烟被弹窗卡死。"""
    from PySide6.QtWidgets import QMessageBox, QFileDialog

    seen = {"warn": [], "info": []}
    for name, bucket in (("warning", "warn"), ("critical", "warn"),
                         ("information", "info")):
        setattr(
            QMessageBox, name,
            staticmethod(lambda *a, _b=bucket, **k: seen[_b].append(
                a[1] if len(a) > 1 else ""
            )),
        )
    return seen


def main(argv):
    quick = "--quick" in argv
    lite = "--lite" in argv
    results = []

    def check(name, fn):
        try:
            detail = fn()
            results.append((name, True, str(detail) if detail else ""))
        except Exception as e:
            results.append((name, False, f"{type(e).__name__}: {e}"))

    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    seen = _silence_dialogs()

    from beeoffice.app import BeeApp

    window = None

    def build_app():
        nonlocal window
        window = BeeApp()
        # 直接触发插件加载，不等 50ms 定时器
        window._lazy_load_modules()
        return f"plugins={len(window.plugins)}"

    check("创建主窗口并加载插件", build_app)
    if window is None:
        _report(results)
        return 1

    def check_plugins():
        minimum = 3 if lite else 4
        assert len(window.plugins) >= minimum, (
            f"只发现 {len(window.plugins)} 个插件（期望 ≥{minimum}）"
        )
        return f"{len(window.plugins)} 个"

    check("插件数量", check_plugins)

    tmp = Path(tempfile.mkdtemp(prefix="bee_smoke_"))

    # ---- 蜜写 ----
    def new_write():
        editor = window._new_beewrite()
        assert editor is not None
        editor.set_content("# 冒烟测试\n\n正文内容\n")
        return "已新建并写入内容"

    check("新建蜜写文档", new_write)

    def export_md():
        from beeoffice.plugins.bee_export import export_to_docx
        out = tmp / "smoke.md.docx"
        ok = export_to_docx("# 冒烟测试\n\n正文内容\n", str(out))
        assert ok, "export_to_docx 返回 False"
        assert out.exists() and out.stat().st_size > 0, "文件未生成"
        from docx import Document
        doc = Document(str(out))
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "冒烟测试" in text, f"DOCX 内容异常: {text[:80]!r}"
        return f"{out.stat().st_size} bytes"

    if not quick:
        check("导出 DOCX 并回读", export_md)

    # ---- 蜜算 ----
    def new_sheet():
        sheet = window._new_beesheet()
        assert sheet is not None and hasattr(sheet, "model")
        return f"列数={sheet.model.columnCount()}"

    check("新建蜜算表格", new_sheet)

    # ---- 蜜演 ----
    def new_show():
        show = window._new_beeshow()
        assert show is not None and hasattr(show, "_slides_html")
        return "已就绪"

    if lite:
        print("  · 精简版：跳过蜜演检查")
    else:
        check("新建蜜演演示", new_show)

    # ---- PDF 批注 ----
    def new_pdf():
        from beeoffice.plugins.pdf_annotator import PDFAnnotator
        annotator = PDFAnnotator()
        annotator.deleteLater()
        return "已创建"

    check("创建 PDF 批注窗口", new_pdf)

    # ---- 命令面板 ----
    def check_palette():
        from beeoffice.commands import build_command_palette
        palette = build_command_palette(window)
        n = len(palette.all_commands)
        assert n >= 20, f"只注册了 {n} 条命令"
        return f"{n} 条命令"

    check("构建命令面板", check_palette)

    check("全程无告警弹窗", lambda: _assert_no_warnings(seen))

    try:
        window.close()
    except Exception:
        pass

    _report(results)
    return 0 if all(ok for _, ok, _ in results) else 1


def _assert_no_warnings(seen):
    assert not seen["warn"], f"出现告警弹窗: {seen['warn']}"
    return "无"


def _report(results):
    print("\n" + "=" * 52)
    print("  冷启动冒烟结果")
    print("=" * 52)
    for name, ok, detail in results:
        mark = "✓" if ok else "✗"
        print(f"  {mark} {name}" + (f"  ({detail})" if detail else ""))
    failed = [r for r in results if not r[1]]
    print("-" * 52)
    print(f"  通过 {len(results) - len(failed)} / {len(results)}")
    print("=" * 52 + "\n")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
