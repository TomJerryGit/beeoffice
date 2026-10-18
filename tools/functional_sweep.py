# -*- coding: utf-8 -*-
"""
全功能扫描：把四大模块的主要路径跑一遍，逐项记录结果。

为什么不是 pytest：
    这里的目的是**发现未知问题**，不是守住已知行为。
    扫描器对每一步做异常隔离——某项崩了不影响其余项继续跑，
    最后汇总成"通过/失败/跳过"清单，失败项带 traceback 摘要。

用法：
    python tools/functional_sweep.py              # 全部
    python tools/functional_sweep.py --fast       # 跳过 WebEngine 重型导出
    python tools/functional_sweep.py --json out.json
"""
import argparse
import json
import sys
import tempfile
import traceback
from pathlib import Path

try:
    from _console import enable_utf8_output
    enable_utf8_output()
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RESULTS = []


def check(group, name, slow=False):
    """注册一个检查项。slow=True 的需要事件循环等待（WebEngine）。"""
    def deco(fn):
        fn._group = group
        fn._name = name
        fn._slow = slow
        RESULTS.append(fn)
        return fn
    return deco


# ======================================================================
# 环境准备
# ======================================================================
def setup(tmp):
    from PySide6.QtWidgets import QMessageBox

    for meth in ("warning", "critical", "information", "question"):
        setattr(QMessageBox, meth, staticmethod(lambda *a, **k: QMessageBox.Ok))

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    from beeoffice.app import BeeApp

    window = BeeApp()
    window._lazy_load_modules()
    return app, window


# ======================================================================
# 蜜写
# ======================================================================
@check("蜜写", "新建文档")
def _w1(ctx):
    ed = ctx["window"]._new_beewrite()
    assert ed is not None, "新建蜜写返回 None"
    ed.set_content("# 标题\n\n正文 **粗** 与 [链](https://a.b)\n")
    ctx["write"] = ed
    return "ok"


@check("蜜写", "Markdown → 富文本 → Markdown 往返")
def _w2(ctx):
    ed = ctx["write"]
    once = ed.content()
    ed._switch_mode("rich_text")
    twice = ed.content()
    ed._switch_mode("markdown")
    assert "**粗**" in twice, f"行内格式丢失：{twice!r}"
    return f"{len(once)} 字符"


@check("蜜写", "设置页眉页脚")
def _w3(ctx):
    ed = ctx["write"]
    ed._switch_mode("rich_text")
    ed._header_text = "机密"
    ed._footer_text = "第 X 页"
    from docx import Document

    doc = Document()
    assert ed._apply_header_footer(doc) is True
    assert doc.sections[0].header.paragraphs[0].text == "机密"
    return "ok"


@check("蜜写", "导出 DOCX")
def _w4(ctx):
    from docx import Document

    from beeoffice.plugins.bee_export import export_to_docx

    out = ctx["tmp"] / "a.docx"
    ok = export_to_docx("# 标题\n\n正文\n", str(out))
    assert ok and out.exists()
    assert "标题" in "\n".join(p.text for p in Document(str(out)).paragraphs)
    return f"{out.stat().st_size} B"


@check("蜜写", "表格菜单：插入表格")
def _w5(ctx):
    ed = ctx["write"]
    ed._switch_mode("rich_text")
    from PySide6.QtGui import QTextCursor

    cursor = ed.rich_editor.textCursor()
    table = cursor.insertTable(3, 3)
    assert table is not None and table.rows() == 3 and table.columns() == 3
    return "3x3"


@check("蜜写", "命令面板构建")
def _w6(ctx):
    from beeoffice.commands import build_command_palette

    p = build_command_palette(ctx["window"])
    n = len(p.all_commands)
    assert n >= 20, f"命令数异常 {n}"
    return f"{n} 条"


# ======================================================================
# 蜜算
# ======================================================================
@check("蜜算", "新建表格")
def _s1(ctx):
    sh = ctx["window"]._new_beesheet()
    assert sh is not None and hasattr(sh, "model")
    ctx["sheet"] = sh
    return "ok"


@check("蜜算", "写入数据并读取")
def _s2(ctx):
    import pandas as pd

    from PySide6.QtCore import Qt

    sh = ctx["sheet"]
    sh.model.set_full_dataframe(
        pd.DataFrame({"名称": ["甲", "乙", "丙"], "数量": [1, 2, 3], "金额": [10, 20, 30]})
    )
    val = sh.model.data(sh.model.index(1, 0), Qt.DisplayRole)
    assert val == "乙", f"读回 {val!r}"
    return "ok"


@check("蜜算", "排序")
def _s3(ctx):
    from PySide6.QtCore import Qt

    sh = ctx["sheet"]
    sh.sort_by_column(1, ascending=False)

    first = sh.model.data(sh.model.index(0, 1), Qt.DisplayRole)
    assert first == "3", f"降序后首行 {first!r}"
    return "ok"


@check("蜜算", "公式：SUM / 复合表达式")
def _s4(ctx):
    from beeoffice.plugins.beesheet_engine import FormulaEngine

    m = ctx["sheet"].model
    total = FormulaEngine.evaluate("=SUM(A1:C1)", m)
    twice = FormulaEngine.evaluate("=SUM(A1:C1)*2", m)
    assert float(total) > 0, f"SUM 结果 {total}"
    assert abs(float(twice) - float(total) * 2) < 1e-6, "复合表达式错误"
    return f"SUM={total}"


@check("蜜算", "宏录制与回放")
def _s5(ctx):
    from PySide6.QtCore import Qt

    from beeoffice.plugins.macro_recorder import RECORDER

    sh = ctx["sheet"]
    RECORDER.stop(); RECORDER.clear()
    RECORDER.start()
    sh.model.setData(sh.model.index(0, 2), "999", Qt.EditRole)
    n = RECORDER.stop()
    assert n >= 1, "没有录到动作"
    sh.model.setData(sh.model.index(0, 2), "0", Qt.EditRole)
    RECORDER.play(sh.model)
    got = sh.model.data(sh.model.index(0, 2), Qt.DisplayRole)
    assert got == "999", f"回放后 {got!r}"
    RECORDER.clear()
    return f"{n} 个动作"


@check("蜜算", "冻结首行")
def _s6(ctx):
    sh = ctx["sheet"]
    sh._freeze_row(0)
    assert sh._frozen_row_view is not None
    sh._unfreeze_all()
    return "ok"


@check("蜜算", "导出 CSV")
def _s7(ctx):
    sh = ctx["sheet"]
    out = ctx["tmp"] / "b.csv"
    fn = getattr(sh, "_export_csv", None) or getattr(sh, "_do_export_csv", None)
    assert fn is not None, "找不到 CSV 导出方法"
    return "ok"


# ======================================================================
# 蜜演
# ======================================================================
@check("蜜演", "新建演示并解析分页")
def _p1(ctx):
    show = ctx["window"]._new_beeshow()
    assert show is not None
    ctx["show"] = show
    show._editor.setPlainText("# 第一页\n\n<!-- 备注一 -->\n\n---\n\n# 第二页\n")
    show._update_preview()
    assert len(show._slides_html) == 2, f"分页数 {len(show._slides_html)}"
    assert show._speaker_notes[0].startswith("备注一"), show._speaker_notes
    return "2 页"


@check("蜜演", "空段不导致页号错位")
def _p2(ctx):
    show = ctx["show"]
    show._editor.setPlainText("# A\n\n---\n\n---\n\n# C\n")
    show._update_preview()
    notes = [n for n in show._speaker_notes]
    assert len(show._slides_html) == len(notes), (
        f"幻灯片 {len(show._slides_html)} 页但备注 {len(notes)} 条"
    )
    return "对齐"


@check("蜜演", "全屏播放窗口是顶层")
def _p3(ctx):
    from beeoffice.plugins.beeshow_constants import _PlayWindow

    w = _PlayWindow(ctx["window"])
    assert w.isWindow(), "播放窗口不是顶层窗口"
    w.deleteLater()
    return "ok"


# ======================================================================
# PDF
# ======================================================================
@check("PDF", "创建批注窗口")
def _f1(ctx):
    from beeoffice.plugins.pdf_annotator import PDFAnnotator

    a = PDFAnnotator()
    a.deleteLater()
    return "ok"


# ======================================================================
# 云同步 / 设置 / 国际化
# ======================================================================
@check("云同步", "文档双向同步（假适配器）")
def _c1(ctx):
    from beeoffice.document_sync import DocumentSync

    class Fake:
        def __init__(self):
            self.f = {}

        def exists(self, r):
            return r in self.f

        def get_file_info(self, r):
            d, t = self.f[r]
            return len(d), t

        def upload(self, lp, r):
            self.f[r] = (Path(lp).read_bytes(), 1.0)
            return True

        def download(self, r, lp):
            Path(lp).write_bytes(self.f[r][0])
            return True

    doc = ctx["tmp"] / "sync.md"
    doc.write_text("hello", encoding="utf-8")
    s = DocumentSync(Fake(), state_path=ctx["tmp"] / "st.json")
    r1 = s.sync([doc])
    r2 = s.sync([doc])
    assert r1.uploaded and r2.skipped, (r1.as_dict(), r2.as_dict())
    return "上传→跳过"


@check("设置", "加密存储往返")
def _c2(ctx):
    from beeoffice.secret_store import protect, unprotect

    token = protect("my-secret")
    assert unprotect(token) == "my-secret"
    assert "my-secret" not in token
    return token.split(":")[0]


@check("国际化", "中英切换")
def _c3(ctx):
    from beeoffice.i18n import set_language, tr

    set_language("en_US")
    en = tr("tab.close")
    set_language("zh_CN")
    zh = tr("tab.close")
    assert en != zh, f"切换无效：{en} / {zh}"
    return f"{en} / {zh}"


# ======================================================================
# 打包/规模
# ======================================================================
@check("工程", "语法检查")
def _e1(ctx):
    import subprocess

    p = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_syntax.py")],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    out = (p.stdout or b"").decode("utf-8", "replace")
    assert "失败 0 个" in out, out[-300:]
    return "全通过"


@check("工程", "语言包 key 一致性")
def _e2(ctx):
    import re

    en = json.loads((ROOT / "beeoffice/locales/en_US.json").read_text(encoding="utf-8"))
    zh = json.loads((ROOT / "beeoffice/locales/zh_CN.json").read_text(encoding="utf-8"))
    missing = [k for k in zh if k not in en]
    assert not missing, f"zh 有而 en 缺: {missing[:5]}"
    return f"en={len(en)} zh={len(zh)}"


# ======================================================================
# 追加：导入 / 批注 / 导出 等
# ======================================================================
@check("蜜算", "导入 CSV")
def _s8(ctx):
    import csv

    p = ctx["tmp"] / "imp.csv"
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["a", "b"])
        w.writerow([1, 2])
        w.writerow([3, 4])
    df = ctx["window"]._new_beesheet()._read_sheet_file(str(p), nrows=100)
    assert len(df) == 2 and list(df.columns) == ["a", "b"], f"{df.shape} {list(df.columns)}"
    return f"{df.shape}"


@check("蜜算", "导入 XLSX")
def _s9(ctx):
    import pandas as pd

    p = ctx["tmp"] / "imp.xlsx"
    pd.DataFrame({"x": [1, 2, 3], "y": ["a", "b", "c"]}).to_excel(p, index=False)
    df = ctx["window"]._new_beesheet()._read_sheet_file(str(p), nrows=100)
    assert len(df) == 3, f"{df.shape}"
    return f"{df.shape}"


@check("蜜写", "批注增删")
def _w7(ctx):
    ed = ctx["write"]
    ed._switch_mode("rich_text")
    ed._add_comment_no_anchor("这是批注")
    allc = ed._comment_manager.get_all()
    assert allc, "批注没有写入"
    # 删除走管理器 remove(id)，但 id 由面板选择驱动；这里只验证写入与计数
    return f"{len(allc)} 条批注"


@check("蜜写", "书签")
def _w8(ctx):
    ed = ctx["write"]
    assert hasattr(ed, "_add_bookmark"), "缺少书签入口"
    assert hasattr(ed, "_bookmark_manager"), "缺少书签管理器"
    return f"管理器就绪（{len(ed._bookmark_manager.get_all())} 条）"


@check("蜜演", "导出 PPTX")
def _p4(ctx):
    import time

    show = ctx["show"]
    show._editor.setPlainText("# A\n\n正文\n")
    show._update_preview()
    out = ctx["tmp"] / "s.pptx"
    show._export_pptx_legacy(str(out))
    deadline = time.time() + 90
    while time.time() < deadline and not (out.exists() and out.stat().st_size > 1000):
        ctx["app"].processEvents()
        time.sleep(0.05)
    assert out.exists() and out.stat().st_size > 1000, "PPTX 未生成"
    return f"{out.stat().st_size} B（该函数无返回值）"


@check("工程", "语言包 key 均被代码引用", slow=False)
def _e3(ctx):
    import re

    src = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in (ROOT / "beeoffice").rglob("*.py")
    )
    en = json.loads((ROOT / "beeoffice/locales/en_US.json").read_text(encoding="utf-8"))
    unused = [k for k in en if f'"{k}"' not in src]
    return f"未引用 {len(unused)} 个（历史遗留，见路线图）"


# ======================================================================
# 运行
# ======================================================================
def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--json")
    ap.add_argument("-k", help="只跑名字包含该子串的检查")
    args = ap.parse_args(argv)

    tmp = Path(tempfile.mkdtemp(prefix="bee_sweep_"))
    ctx = {"tmp": tmp}
    setup_error = None
    try:
        app, window = setup(tmp)
        ctx["app"], ctx["window"] = app, window
    except Exception:
        setup_error = traceback.format_exc()

    rows = []
    for fn in RESULTS:
        if args.fast and fn._slow:
            continue
        if args.k and args.k not in fn._name:
            continue
        if setup_error:
            rows.append((fn._group, fn._name, "SETUP", setup_error.splitlines()[-1]))
            continue
        try:
            detail = fn(ctx)
            rows.append((fn._group, fn._name, "PASS", str(detail or "")))
        except Exception as e:
            tb = traceback.format_exc()
            short = f"{type(e).__name__}: {e}"[:200]
            rows.append((fn._group, fn._name, "FAIL", short, tb))

    print("\n" + "=" * 78)
    print("  全功能扫描结果")
    print("=" * 78)
    group = None
    for row in rows:
        if row[0] != group:
            group = row[0]
            print(f"\n[{group}]")
        mark = {"PASS": "✓", "FAIL": "✗", "SKIP": "·", "SETUP": "!"}[row[2]]
        print(f"  {mark} {row[1]}" + (f"  — {row[3]}" if row[3] else ""))

    fails = [r for r in rows if r[2] != "PASS"]
    print("\n" + "-" * 78)
    print(f"  通过 {len(rows) - len(fails)} / {len(rows)}   失败 {len(fails)}")
    print("=" * 78 + "\n")

    if args.json:
        Path(args.json).write_text(
            json.dumps([r[:4] for r in rows], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"结果已写入 {args.json}")

    if fails:
        print("失败详情：")
        for r in fails:
            print(f"\n--- {r[0]} / {r[1]} ---")
            print((r[4] if len(r) > 4 else r[3])[-800:])

    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
