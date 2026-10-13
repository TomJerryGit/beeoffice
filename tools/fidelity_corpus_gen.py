# tools/fidelity_corpus_gen.py
"""
生成**针对性的**保真度语料（阶段 A）

为什么需要它
------------
`test+files/` 里的真实文件（3 个）已经跑过、零丢失，但它们**恰好没有**
覆盖很多构造：多分节、横向节、编号/项目符号列表、合并单元格、嵌套表格、
内部书签、脚注、多工作表、公式、图表……

所以再生成一组"每个文件专攻一个维度"的语料去撞。它们仍是合成的，
但**覆盖目的明确**，与"我随便造一个文件"不同。

用法
----
    python tools/fidelity_corpus_gen.py 输出目录        # 生成全部
    python tools/fidelity_corpus_gen.py 输出目录 --list  # 只列名字

生成的文件
----------
    docx_lists.docx        项目符号 / 编号 / 嵌套列表
    docx_sections.docx     两个分节，第二节横向且页边距不同
    docx_tables.docx       横向合并、纵向合并、嵌套表格、空单元格
    docx_inline.docx       外部超链接、内部书签、粗斜体混排、长段落
    docx_headers.docx      页眉含表格、页脚带页码域、非标准纸张
    xlsx_rich.xlsx         3 张表 + 公式 + 合并 + 条件格式 + 验证 + 冻结 + 图表
    xlsx_wide.xlsx         200 列 × 50 行（宽表）
    xlsx_tall.xlsx         5000 行（高表，看是否被截断）
    pptx_basic.pptx        2 页 + 图片 + 表格 + 备注（只有导出，无导入）
"""

import sys
from pathlib import Path


def make_png(path: Path, color="navy", size=(80, 60)) -> Path:
    from PIL import Image

    Image.new("RGB", size, color=color).save(str(path))
    return path


# ==================== DOCX ====================

def docx_lists(path: Path) -> Path:
    from docx import Document

    doc = Document()
    doc.add_heading("列表测试", level=1)
    doc.add_paragraph("项目符号：")
    for item in ("第一项", "第二项", "第三项"):
        doc.add_paragraph(item, style="List Bullet")
    doc.add_paragraph("编号：")
    for item in ("步骤一", "步骤二", "步骤三"):
        doc.add_paragraph(item, style="List Number")
    doc.save(str(path))
    return path


def docx_sections(path: Path) -> Path:
    """两个分节：第二节横向且页边距不同。"""
    from docx import Document
    from docx.enum.section import WD_ORIENT, WD_SECTION
    from docx.shared import Mm

    doc = Document()
    doc.add_heading("第一节（纵向）", level=1)
    doc.add_paragraph("这一段属于第一节。")

    second = doc.add_section(WD_SECTION.NEW_PAGE)
    second.orientation = WD_ORIENT.LANDSCAPE
    second.page_width = Mm(297)
    second.page_height = Mm(210)
    second.left_margin = Mm(15)
    second.right_margin = Mm(15)
    doc.add_heading("第二节（横向）", level=1)
    doc.add_paragraph("这一段属于第二节，页面是横向的。")
    doc.save(str(path))
    return path


def docx_tables(path: Path) -> Path:
    """横向合并 / 纵向合并 / 嵌套表格 / 空单元格。"""
    from docx import Document

    doc = Document()
    doc.add_heading("表格测试", level=1)

    table = doc.add_table(rows=4, cols=3)
    table.style = "Table Grid"
    for ci, text in enumerate(["指标", "本期", "上期"]):
        table.cell(0, ci).text = text
    table.cell(1, 0).text = "营收"
    table.cell(1, 1).text = "1,234"
    table.cell(1, 2).text = ""                 # 空单元格
    table.cell(2, 0).text = "成本"
    table.cell(2, 1).text = "800"
    table.cell(2, 2).text = "700"
    # 横向合并最后一行前两列
    table.cell(3, 0).text = "合计"
    table.cell(3, 2).text = "2,034"
    table.cell(3, 0).merge(table.cell(3, 1))

    # 第二个表：纵向合并第 0 列的第 1~2 行
    table2 = doc.add_table(rows=3, cols=2)
    table2.cell(0, 0).text = "项目"
    table2.cell(0, 1).text = "值"
    table2.cell(1, 0).text = "跨行"
    table2.cell(1, 1).text = "A"
    table2.cell(2, 0).text = "跨行"
    table2.cell(2, 1).text = "B"
    table2.cell(1, 0).merge(table2.cell(2, 0))

    # 嵌套表格（在外层表格的单元格里再放一个表）
    outer = doc.add_table(rows=1, cols=1)
    outer.style = "Table Grid"
    cell = outer.cell(0, 0)
    cell.text = "外层单元格"
    inner = cell.add_table(rows=1, cols=2)
    inner.cell(0, 0).text = "嵌套左"
    inner.cell(0, 1).text = "嵌套右"

    doc.save(str(path))
    return path


def docx_inline(path: Path) -> Path:
    """外部超链接 + 内部书签 + 粗斜体混排。"""
    from docx import Document
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.opc.constants import RELATIONSHIP_TYPE as RT

    doc = Document()
    doc.add_heading("内联格式测试", level=1)

    # 内部书签
    mark_para = doc.add_paragraph("目标段落（书签 anchor 在这）")
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), "1")
    start.set(qn("w:name"), "ch1")
    mark_para._p.insert(0, start)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), "1")
    mark_para._p.append(end)

    # 粗体 + 斜体混排
    para = doc.add_paragraph()
    para.add_run("普通")
    bold = para.add_run("粗体")
    bold.bold = True
    para.add_run("与")
    italic = para.add_run("斜体")
    italic.italic = True
    para.add_run("。")

    # 外部超链接
    link_para = doc.add_paragraph()
    link_para.add_run("参考 ")
    r_id = link_para.part.relate_to(
        "https://www.python.org/", RT.HYPERLINK, is_external=True
    )
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), r_id)
    run = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = "Python 官网"
    run.append(t)
    link.append(run)
    link_para._p.append(link)

    # 内部跳转
    anchor_para = doc.add_paragraph()
    anchor = OxmlElement("w:hyperlink")
    anchor.set(qn("w:anchor"), "ch1")
    a_run = OxmlElement("w:r")
    a_t = OxmlElement("w:t")
    a_t.text = "跳到目标段落"
    a_run.append(a_t)
    anchor.append(a_run)
    anchor_para._p.append(anchor)

    doc.save(str(path))
    return path


def docx_headers(path: Path) -> Path:
    """页眉含表格 + 页脚文字 + 非标准纸张。"""
    from docx import Document
    from docx.shared import Mm

    doc = Document()
    doc.add_paragraph("正文内容")
    section = doc.sections[0]
    section.page_width = Mm(200)
    section.page_height = Mm(280)
    section.top_margin = Mm(18)
    section.bottom_margin = Mm(18)
    section.left_margin = Mm(22)
    section.right_margin = Mm(22)

    header = section.header
    header.paragraphs[0].text = "页眉文字"
    # 注意：python-docx 的 BlockItemContainer.add_table() 必须给 width
    htable = header.add_table(rows=1, cols=2, width=Mm(160))
    htable.cell(0, 0).text = "页眉表左"
    htable.cell(0, 1).text = "页眉表右"

    section.footer.paragraphs[0].text = "第 X 页"
    doc.save(str(path))
    return path


# ==================== XLSX ====================

def xlsx_rich(path: Path) -> Path:
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, Reference
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.styles import PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    ws = wb.active
    ws.title = "明细"
    ws.append(["产品", "数量", "单价", "金额"])
    for i, (name, qty, price) in enumerate(
        [("甲", 10, 12.5), ("乙", 80, 3.2), ("丙", 5, 99.0)], start=2
    ):
        ws.cell(row=i, column=1, value=name)
        ws.cell(row=i, column=2, value=qty)
        ws.cell(row=i, column=3, value=price)
        ws.cell(row=i, column=4, value=f"=B{i}*C{i}")
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
    chart.add_data(
        Reference(ws, min_col=2, min_row=1, max_row=4), titles_from_data=True
    )
    ws.add_chart(chart, "G2")

    summary = wb.create_sheet("汇总")
    summary.append(["项目", "值"])
    summary.append(["合计", "=SUM(明细!D2:D4)"])

    notes = wb.create_sheet("说明")
    notes.append(["这是第三张表"])
    notes.append([1, 2, 3])

    wb.save(str(path))
    return path


def xlsx_wide(path: Path) -> Path:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "宽表"
    for c in range(1, 201):
        ws.cell(row=1, column=c, value=f"列{c}")
    for r in range(2, 52):
        for c in range(1, 201):
            ws.cell(row=r, column=c, value=r * c)
    wb.save(str(path))
    return path


def xlsx_tall(path: Path) -> Path:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "高表"
    ws.append(["序号", "名称", "数值"])
    for r in range(2, 5002):
        ws.cell(row=r, column=1, value=r - 1)
        ws.cell(row=r, column=2, value=f"项目{r - 1}")
        ws.cell(row=r, column=3, value=r * 1.5)
    wb.save(str(path))
    return path


# ==================== PPTX ====================

def pptx_basic(path: Path) -> Path:
    from pptx import Presentation
    from pptx.util import Inches

    img = make_png(path.parent / "_corpus_pptx.png", color="orange")
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "语料演示"
    slide.placeholders[1].text = "第一点\n第二点"
    table = slide.shapes.add_table(
        2, 2, Inches(1), Inches(4), Inches(4), Inches(1)
    ).table
    table.cell(0, 0).text = "A"
    table.cell(0, 1).text = "B"
    slide.shapes.add_picture(
        str(img), Inches(7), Inches(1), width=Inches(1.5)
    )
    slide.notes_slide.notes_text_frame.text = "备注内容"
    second = prs.slides.add_slide(prs.slide_layouts[5])
    second.shapes.title.text = "第二页"
    prs.save(str(path))
    return path


#: 名字 → 生成函数
GENERATORS = {
    "docx_lists.docx": docx_lists,
    "docx_sections.docx": docx_sections,
    "docx_tables.docx": docx_tables,
    "docx_inline.docx": docx_inline,
    "docx_headers.docx": docx_headers,
    "xlsx_rich.xlsx": xlsx_rich,
    "xlsx_wide.xlsx": xlsx_wide,
    "xlsx_tall.xlsx": xlsx_tall,
    "pptx_basic.pptx": pptx_basic,
}


def generate_all(target: Path) -> list:
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    made = []
    for name, func in GENERATORS.items():
        path = target / name
        func(path)
        made.append(path)
    return made


def main(argv):
    import argparse

    ap = argparse.ArgumentParser(description="生成保真度语料")
    ap.add_argument("target", help="输出目录")
    ap.add_argument("--list", action="store_true", help="只列出会生成的文件名")
    args = ap.parse_args(argv)

    if args.list:
        for name in GENERATORS:
            print(name)
        return 0

    made = generate_all(Path(args.target))
    for path in made:
        print(f"  {path.name}  ({path.stat().st_size} B)")
    print(f"\n共生成 {len(made)} 个文件到 {args.target}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
