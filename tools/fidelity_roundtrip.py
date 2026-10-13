# tools/fidelity_roundtrip.py
"""
保真度往返测量（阶段 A）

它做什么
--------
1. 生成**含丰富结构**的标准测试文件（DOCX / XLSX / PPTX）
2. 用 **BeeOffice 自己的代码路径**做一次往返
3. 用 `tools/ooxml_probe.py` 在往返前后各测一次特征，输出"丢了什么"

**关键：每一处往返都调用产品代码，不重写实现。** 具体调用点见下方
`roundtrip_*` 函数的注释与 `docs/fidelity.md`。

往返的定义
----------
| 格式 | 往返 | 说明 |
|---|---|---|
| DOCX | `import_from_docx()` → Markdown → `export_to_docx()` | **注意：中间经过 Markdown**，这是保真的薄弱点 |
| XLSX | `pd.read_excel(engine=openpyxl)` → `df.to_excel(index=False)` | 即 `beesheet_data_mixin` 的导入/导出路径 |
| PPTX | **无往返** | BeeOffice **没有 PPTX 导入**（只导出），因此只测"导出产物包含什么" |

用法
----
    python tools/fidelity_roundtrip.py                  # 全部，打印报告
    python tools/fidelity_roundtrip.py --json 报告.json # 另存 JSON（供测试消费）
    python tools/fidelity_roundtrip.py --keep 目录      # 保留生成的文件
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.ooxml_probe import compare, probe  # noqa: E402


# ==================== 1. 生成测试文件 ====================

def _make_png(path: Path, color="teal") -> Path:
    from PIL import Image

    Image.new("RGB", (120, 90), color=color).save(str(path))
    return path


def build_docx_fixture(path: Path) -> dict:
    """
    生成含中文标题/正文/表格(含合并)/图片/页边距/页眉页脚/超链接的 DOCX。

    :return: 已写入的特征清单（用于报告对照，不参与判定）
    """
    from docx import Document
    from docx.shared import Cm

    img = _make_png(path.parent / "fixture_docx.png")
    doc = Document()

    doc.add_heading("季度经营分析报告", level=1)
    doc.add_paragraph(
        "本文档用于测量 DOCX 往返保真度，包含中文正文、样式、表格与图片。"
    )
    doc.add_heading("一、核心指标", level=2)
    doc.add_paragraph("以下表格含表头、合并单元格与空单元格。")

    table = doc.add_table(rows=3, cols=3)
    table.style = "Table Grid"
    for ci, text in enumerate(["指标", "本期", "上期"]):
        table.cell(0, ci).text = text
    table.cell(1, 0).text = "营收"
    table.cell(1, 1).text = "1,234"
    table.cell(1, 2).text = ""          # 空单元格
    table.cell(2, 0).merge(table.cell(2, 1)).text = "合计"
    table.cell(2, 2).text = "1,234"

    doc.add_picture(str(img), width=Cm(3.5))

    section = doc.sections[0]
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(2.5)
    section.left_margin = Cm(3.0)
    section.right_margin = Cm(3.0)
    section.header.paragraphs[0].text = "BeeOffice 保真度测试"
    section.footer.paragraphs[0].text = "第 X 页"

    # 超链接：python-docx 无公开 API，用底层 XML 注入
    _add_docx_hyperlink(doc, "BeeOffice 项目主页", "https://example.com")

    doc.save(str(path))
    return {"headers": 1, "footers": 1, "hyperlinks": 1, "images": 1,
            "tables": 1, "merged_cells": 1}


def _add_docx_hyperlink(doc, text, url):
    """在文档末尾加一个真正的 w:hyperlink。"""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    from docx.opc.constants import RELATIONSHIP_TYPE as RT

    para = doc.add_paragraph()
    r_id = para.part.relate_to(
        url, RT.HYPERLINK, is_external=True
    )
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), r_id)

    run = OxmlElement("w:r")
    run_props = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), "0563C1")
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    run_props.append(color)
    run_props.append(underline)
    run.append(run_props)

    t = OxmlElement("w:t")
    t.text = text
    run.append(t)
    link.append(run)
    para._p.append(link)


def build_xlsx_fixture(path: Path) -> dict:
    """
    生成含公式/合并/数字格式/条件格式/冻结窗格/数据验证/图表/定义名称的 XLSX。
    """
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, Reference
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.styles import PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    ws = wb.active
    ws.title = "明细"

    ws.append(["产品", "数量", "单价", "金额"])
    data = [("甲", 10, 12.5), ("乙", 80, 3.2), ("丙", 5, 99.0)]
    for i, (name, qty, price) in enumerate(data, start=2):
        ws.cell(row=i, column=1, value=name)
        ws.cell(row=i, column=2, value=qty)
        ws.cell(row=i, column=3, value=price)
        ws.cell(row=i, column=4, value=f"=B{i}*C{i}")     # 公式

    ws["C2"].number_format = "#,##0.00"
    ws.merge_cells("A6:C6")
    ws["A6"] = "合并标题行"
    ws.freeze_panes = "A2"
    ws.conditional_formatting.add(
        "B2:B4",
        CellIsRule(operator="greaterThan", formula=["50"],
                   fill=PatternFill("solid", fgColor="FFC7CE")),
    )
    dv = DataValidation(type="list", formula1='"甲,乙,丙"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add("E2:E4")

    chart = BarChart()
    chart.add_data(Reference(ws, min_col=2, min_row=1, max_row=4),
                   titles_from_data=True)
    ws.add_chart(chart, "G2")

    summary = wb.create_sheet("汇总")
    # 注意：pandas 固定把工作表**第 1 行**当表头，所以这里要有表头行。
    # "无表头的表会丢首行" 是一个真实约束，已在
    # tests/fidelity/test_beesheet_workbook.py 里单独钉住。
    summary.append(["项目", "值"])
    summary.append(["合计", "=SUM(明细!D2:D4)"])
    wb.save(str(path))
    return {"sheets": 2, "formulas": 4, "merged_ranges": 1,
            "conditional_formatting": 1, "data_validations": 1,
            "freeze_panes": 1, "charts": 1, "defined_names": 0}


def build_pptx_fixture(path: Path) -> dict:
    """生成含标题/正文/表格/图片/备注的 PPTX（用于探测，不做往返）。"""
    from pptx import Presentation
    from pptx.util import Inches

    img = _make_png(path.parent / "fixture_pptx.png", color="orange")
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "保真度测试演示"
    slide.placeholders[1].text = "第一页要点\n第二页要点"

    table = slide.shapes.add_table(
        2, 3, Inches(1), Inches(4), Inches(6), Inches(1.2)
    ).table
    for ci, text in enumerate(["列一", "列二", "列三"]):
        table.cell(0, ci).text = text
    table.cell(1, 0).text = "数据"

    slide.shapes.add_picture(
        str(img), Inches(7), Inches(1), width=Inches(1.5)
    )
    slide.notes_slide.notes_text_frame.text = "这是演讲者备注"

    second = prs.slides.add_slide(prs.slide_layouts[5])
    second.shapes.title.text = "第二页"
    prs.save(str(path))
    return {"slides": 2, "pictures": 1, "tables": 1, "notes_slides": 1}


# ==================== 2. 往返（调用产品代码） ====================

def roundtrip_docx(src: Path, out: Path):
    """
    DOCX 往返：`import_from_docx()` → Markdown → `export_to_docx()`。

    这两个函数就是产品路径：`app._open_docx_file` 与 `_write_docx` 调的就是它们。
    注意中间经过 **Markdown** —— 这是保真的结构性弱点。

    保真度阶段 A：页面设置与页眉页脚**不走 Markdown**，而是像产品那样
    用 `read_docx_extras()` 另读一份、导出时写回
    （产品里由 `app._open_docx_file` → `widget.apply_docx_extras()` 承担）。
    """
    from beeoffice.plugins.bee_export import (
        export_to_docx,
        import_from_docx,
        read_docx_extras,
    )

    md = import_from_docx(str(src))
    extras = read_docx_extras(src)
    ok = export_to_docx(
        md, str(out), page_settings=extras, base_dir=str(src.parent),
        header_text=extras.get("header_text"),
        footer_text=extras.get("footer_text"),
        table_merges=extras.get("table_merges"),
    )
    return ok, {"markdown_chars": len(md or ""),
                "markdown_lines": len((md or "").splitlines()),
                "extras": sorted(k for k, v in extras.items() if v not in ("", None))}


def roundtrip_xlsx(src: Path, out: Path):
    """
    XLSX 往返：走**产品的导入/导出路径**。

    对应 `beesheet.py::_import_file_from_path` 与
    `beesheet_data_mixin._export_xlsx` —— 即
        beesheet_workbook.read_workbook()
        → （编辑）→ beesheet_workbook.sync_active_sheet() + write_workbook()

    2026-10-11 之前这两处是 `pd.read_excel` + `df.to_excel`，实测 9 项特征丢 8 项；
    改为工作簿对象后**工作表数与公式数不再丢失**（仍丢的项见 docs/fidelity.md）。
    """
    from beeoffice.plugins.beesheet_workbook import (
        read_workbook,
        sync_active_sheet,
        write_workbook,
    )

    workbook = read_workbook(src)
    first = workbook.sheets[0]
    sync_active_sheet(workbook, first.name, first.df)
    write_workbook(workbook, out)
    return True, {
        "sheets": len(workbook.sheets),
        "formulas": workbook.formula_count,
    }


# ==================== 3. 测量 ====================

def measure(name, fixture_builder, roundtrip, workdir: Path):
    """生成 → 探测 → 往返 → 再探测。"""
    src = workdir / f"fixture.{name}"
    built = fixture_builder(src)
    before = probe(src)

    result = {
        "name": name, "fixture": str(src), "built_features": built,
        "before": before, "after": None, "roundtrip": None, "error": None,
    }

    if roundtrip is None:
        result["roundtrip"] = {"skipped": True,
                               "reason": "BeeOffice 无此格式的导入路径"}
        return result

    out = workdir / f"roundtrip.{name}"
    try:
        ok, note = roundtrip(src, out)
    except Exception as e:                       # noqa: BLE001 - 报告里要看到原因
        result["error"] = f"{type(e).__name__}: {e}"
        return result

    result["roundtrip"] = {"ok": bool(ok), **note}
    if ok and out.is_file():
        result["after"] = probe(out)
    return result


def measure_all(workdir: Path):
    workdir.mkdir(parents=True, exist_ok=True)
    return [
        measure("docx", build_docx_fixture, roundtrip_docx, workdir),
        measure("xlsx", build_xlsx_fixture, roundtrip_xlsx, workdir),
        measure("pptx", build_pptx_fixture, None, workdir),
    ]


def render_report(results) -> str:
    """把测量结果渲染成 Markdown 报告。"""
    lines = []
    for r in results:
        lines.append(f"\n## {r['name'].upper()}")
        if r["error"]:
            lines.append(f"- **往返失败**：`{r['error']}`")
            continue

        before = r["before"]
        lines.append(
            f"- 测试文件：`{Path(r['fixture']).name}` "
            f"（{before['size']} B）"
        )
        if r["roundtrip"] and r["roundtrip"].get("skipped"):
            lines.append(f"- **跳过往返**：{r['roundtrip']['reason']}")
            lines.append("\n生成文件的内容特征（仅探测，无对照）：")
            lines.append("")
            lines.append("| 特征 | 值 |")
            lines.append("|---|---|")
            for k, v in before["features"].items():
                lines.append(f"| {k} | {v} |")
            continue

        after = r["after"]
        if after is None:
            lines.append("- 往返未产出文件")
            continue

        rows = compare(before, after)
        lost = [x for x in rows if x["status"] == "lost"]
        changed = [x for x in rows if x["status"] == "changed"]
        gained = [x for x in rows if x["status"] == "gained"]
        lines.append(
            f"- 往返后：{after['size']} B；**丢失 {len(lost)} 项 / "
            f"变化 {len(changed)} 项 / 增加 {len(gained)} 项**"
        )
        if r["roundtrip"]:
            extra = {k: v for k, v in r["roundtrip"].items() if k != "ok"}
            if extra:
                lines.append(f"- 中间产物：{extra}")
        lines.append("")
        lines.append("| 状态 | 特征 | 往返前 | 往返后 |")
        lines.append("|---|---|---|---|")
        mark = {"lost": "**丢失**", "gained": "增加", "changed": "变化"}
        for x in rows:
            if x["status"] == "same":
                continue
            lines.append(
                f"| {mark[x['status']]} | `{x['feature']}` | "
                f"{x['before']} | {x['after']} |"
            )
        kept = [x for x in rows if x["status"] == "same"
                and isinstance(x["before"], int) and x["before"] > 0]
        if kept:
            lines.append("")
            lines.append(
                "保留下来的非零特征："
                + "、".join(f"`{x['feature']}`" for x in kept)
            )
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="保真度往返测量")
    ap.add_argument("--json", help="把结果另存为 JSON")
    ap.add_argument("--keep", help="保留生成文件的目录（默认临时目录）")
    args = ap.parse_args(argv)

    if args.keep:
        workdir = Path(args.keep)
        workdir.mkdir(parents=True, exist_ok=True)
        results = measure_all(workdir)
    else:
        with tempfile.TemporaryDirectory(prefix="beeoffice_fidelity_") as td:
            results = measure_all(Path(td))
            _emit(results, args)
            return 0

    _emit(results, args)
    return 0


def _emit(results, args):
    print(render_report(results))
    if args.json:
        Path(args.json).write_text(
            json.dumps(results, ensure_ascii=False, indent=2,
                       default=str),
            encoding="utf-8",
        )
        print(f"\nJSON 已写入 {args.json}")


if __name__ == "__main__":
    sys.exit(main())
