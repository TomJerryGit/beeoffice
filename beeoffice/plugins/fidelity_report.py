# beeoffice/plugins/fidelity_report.py
"""
**保真度提示**：告诉用户"这份文件里有哪些内容我们保不住"。

为什么要有它
------------
本项目的保真度工作（`docs/fidelity.md`）已经查明：有一批**构造**在
导入→导出之间必然丢失或降级。以往它们是**静默**发生的 —— 用户打开、
编辑、导出，然后才发现脚注没了、嵌套表格空了。

竞品普遍不做这件事。主动告知的成本很低，收益是"用户知道哪些地方要自己确认"，
这比"看起来一切正常"诚实得多。

规则从哪来
----------
**全部来自实测，不是推断**（见 `tests/fidelity/test_fidelity_report.py`
里对每一项的往返断言）。实测结果分三档：

内容真正丢失（`high`）：
    嵌套表格、文本框、公式(OMML)、脚注/尾注、批注、旧版 VML 图形、
    图表、OLE 嵌入对象、SmartArt、宏

只丢失"能力"、文字还在（`medium`）：
    目录域（目录文字保留，但不再能"更新目录"）、
    内容控件（文字保留，控件结构消失）、
    修订痕迹（改动内容去向正确，但"谁改的/何时改的"没了）

明确**不报**的（实测证明可保真，报了就是误报）：
    普通段落/标题/列表、表格与合并单元格、图片、超链接（含 HYPERLINK 域）、
    书签、分节与横向页、页眉页脚（含页码域）、段落样式、页面设置、
    修订后的**文字内容**、内容控件里的**文字**
"""
import logging
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

#: 严重程度：high = 内容会丢；medium = 内容在但能力丢
HIGH = "high"
MEDIUM = "medium"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


@dataclass
class LossItem:
    """一项"保不住"的构造。"""

    key: str          # 稳定标识（测试用）
    label: str        # 给用户看的中文名
    count: int        # 出现次数
    effect: str       # 一句话说明后果
    severity: str = HIGH

    def line(self) -> str:
        return f"· {self.label}（{self.count} 处）：{self.effect}"


@dataclass
class FidelityReport:
    """一份文件的保真度提示。"""

    path: str = ""
    kind: str = ""                       # docx / xlsx / pptx / unknown
    items: List[LossItem] = field(default_factory=list)
    note: str = ""                       # 额外说明（例如"可能是加密文档"）

    @property
    def has_losses(self) -> bool:
        return bool(self.items)

    @property
    def high_items(self) -> List[LossItem]:
        return [i for i in self.items if i.severity == HIGH]

    @property
    def has_high_losses(self) -> bool:
        return bool(self.high_items)

    def summary(self) -> str:
        """一句话概括（状态栏用）。"""
        if not self.items:
            return "未发现无法保真的构造"
        high = len(self.high_items)
        total = len(self.items)
        if high:
            return f"⚠️ 有 {high} 类内容无法保留（共 {total} 类需注意）"
        return f"ℹ️ 有 {total} 类内容会降级（文字保留）"

    def detail_lines(self) -> List[str]:
        """明细（对话框用）：先内容丢失，再能力降级。"""
        lines = []
        for item in self.high_items:
            lines.append(item.line())
        for item in self.items:
            if item.severity != HIGH:
                lines.append(item.line())
        return lines


# ==================== DOCX ====================

def _docx_items(names: List[str], root, nsmap) -> List[LossItem]:
    """按实测结论判定 DOCX 里各项构造。"""
    from lxml import etree                                    # noqa: F401

    def count(tag, within=None):
        scope = root if within is None else within
        return len(scope.findall(f".//{tag}"))

    items: List[LossItem] = []

    # ---- 脚注/尾注/批注：必须按**实际引用**判定，不能"部件存在就算" ----
    # ⚠️ 踩过的坑：**每个 DOCX 默认都带 word/footnotes.xml 与 word/endnotes.xml**
    # （通常只含分隔符脚注，id 为 -1/0）。第一版按"部件存在"判定，
    # 结果 7 份已实测零丢失的真实文档里有 3 份被误报 —— 用户会被吓到。
    footnote_refs = count(f"{W}footnoteReference")
    if footnote_refs:
        items.append(LossItem(
            "footnote", "脚注", footnote_refs,
            "脚注内容与正文里的脚注标记都不会保留", HIGH))

    endnote_refs = count(f"{W}endnoteReference")
    if endnote_refs:
        items.append(LossItem(
            "endnote", "尾注", endnote_refs,
            "尾注内容与标记都不会保留", HIGH))

    comment_refs = count(f"{W}commentReference")
    if comment_refs:
        items.append(LossItem(
            "comment", "批注", comment_refs,
            "批注内容不会保留（被批注的文字会保留）", HIGH))

    # ---- 独立部件：这些"有就是有"，不存在默认空部件的情况 ----
    if any(n.endswith("vbaProject.bin") for n in names):
        items.append(LossItem(
            "macro", "宏（VBA）", 1,
            "宏代码不会保留，导出的文件不再能运行宏", HIGH))
    if any("/embeddings/" in n for n in names):
        items.append(LossItem(
            "ole", "嵌入对象（OLE）", 1,
            "嵌入的 Excel/Visio 等对象不会保留", HIGH))
    if any("/diagrams/" in n for n in names):
        items.append(LossItem(
            "smartart", "SmartArt 图形", 1,
            "SmartArt 图形不会保留", HIGH))
    if any("/charts/" in n for n in names):
        items.append(LossItem(
            "chart", "图表", 1,
            "图表不会保留（数据表会保留）", HIGH))

    # ---- 正文内联构造：按实测计数 ----
    textboxes = count(f"{W}txbxContent")
    if textboxes:
        items.append(LossItem(
            "textbox", "文本框", textboxes,
            "文本框里的文字与图形整块丢失", HIGH))

    equations = count(f"{M}oMath")
    if equations:
        items.append(LossItem(
            "equation", "公式（OMML）", equations,
            "公式内容丢失（不是变成图片，是直接没有）", HIGH))

    # 嵌套表格：某个 w:tbl 的后代里还有 w:tbl
    nested = 0
    for table in root.findall(f".//{W}tbl"):
        if any(child is not table for child in table.iter(f"{W}tbl")):
            nested += 1
    if nested:
        items.append(LossItem(
            "nested_table", "嵌套表格", nested,
            "单元格里的表格整块丢失（外层表格保留）", HIGH))

    vml = count(f"{W}pict")
    if vml:
        items.append(LossItem(
            "legacy_graphics", "旧版图形（VML）", vml,
            "旧版图形/形状不会保留", HIGH))

    # ---- 能力降级：文字保留 ----
    toc = 0
    for instr in root.findall(f".//{W}instrText"):
        if instr.text and "TOC" in instr.text.upper():
            toc += 1
    if toc:
        items.append(LossItem(
            "toc_field", "目录域", toc,
            "目录文字会保留，但不再是域——导出后无法“更新目录”", MEDIUM))

    controls = count(f"{W}sdt")
    if controls:
        items.append(LossItem(
            "content_control", "内容控件", controls,
            "控件里的文字会保留，控件结构（下拉/日期选择等）消失", MEDIUM))

    revisions = count(f"{W}ins") + count(f"{W}del")
    if revisions:
        items.append(LossItem(
            "revision", "修订痕迹", revisions,
            "改动后的文字会保留，但“谁改的/何时改的”不再可查", MEDIUM))

    return items


# ==================== XLSX ====================

def _xlsx_items(names: List[str], root) -> List[LossItem]:
    """
    蜜算走"打开源工作簿只更新值"，所以文件层面的东西大多**保留**。
    只报实测确实不行的：宏、外部链接，以及蜜算**显示不了**的透视表/图表工作表。
    """
    items: List[LossItem] = []

    if any(n.endswith("vbaProject.bin") for n in names):
        items.append(LossItem(
            "macro", "宏（VBA）", 1,
            "宏代码会保留在文件里，但蜜算里不显示也不能运行", MEDIUM))
    if any("/externalLinks/" in n for n in names):
        items.append(LossItem(
            "external_link", "外部链接", 1,
            "引用其他工作簿的链接蜜算不会更新", MEDIUM))
    if any("/pivotTables/" in n or "/pivotCache/" in n for n in names):
        items.append(LossItem(
            "pivot", "数据透视表", 1,
            "透视表在文件里保留，但蜜算里显示为普通数值、不能刷新", MEDIUM))
    if any("/chartsheets/" in n for n in names):
        items.append(LossItem(
            "chartsheet", "图表工作表", 1,
            "图表工作表蜜算无法显示或编辑", MEDIUM))
    return items


# ==================== 入口 ====================

def analyze_file(path) -> FidelityReport:
    """
    分析一份文件，返回保真度提示。

    **绝不抛异常**：这是一个"提示"功能，任何失败都应静默降级为"无提示"，
    不能因为它让打开/导出失败。
    """
    path = Path(path)
    report = FidelityReport(path=str(path))

    try:
        suffix = path.suffix.lower()
        report.kind = suffix.lstrip(".")

        if suffix in (".doc", ".xls", ".ppt"):
            report.note = (
                f"这是旧版二进制格式（{suffix}）。蜜蜂办公没有对应的读取路径，"
                f"建议先用 WPS/Office 另存为 .docx/.xlsx/.pptx 再打开。"
            )
            return report
        if suffix == ".pptx":
            report.note = (
                "蜜演目前只支持**导出** PPTX，不支持导入。"
                "打开 .pptx 需要先转为其他形式。"
            )
            return report
        if suffix not in (".docx", ".xlsx"):
            return report

        if not zipfile.is_zipfile(path):
            with open(path, "rb") as handle:
                magic = handle.read(8)
            if magic[:4] == b"\xd0\xcf\x11\xe0":
                report.note = (
                    "这不是 OOXML 包（看起来是加密文档或旧版二进制格式），"
                    "无法读取其内部构造。"
                )
            else:
                report.note = "文件不是有效的 Office 文档包，无法分析。"
            return report

        from lxml import etree

        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if suffix == ".docx":
                root = etree.fromstring(archive.read("word/document.xml"))
                report.items = _docx_items(names, root, None)
            else:
                root = etree.fromstring(archive.read("xl/workbook.xml"))
                report.items = _xlsx_items(names, root)
    except Exception as e:  # noqa: BLE001 - 提示失败不能影响正常流程
        logging.debug(f"[fidelity_report] 分析失败（忽略）: {e}")
        report.items = []
    return report


def format_report(report: FidelityReport, filename: str = "") -> str:
    """把报告渲染成给用户看的纯文本。"""
    title = filename or Path(report.path).name
    if report.note and not report.items:
        return f"{title}\n\n{report.note}"

    parts = [f"{title}\n"]
    if report.note:
        parts.append(report.note + "\n")
    if not report.items:
        parts.append("未发现无法保真的构造。")
        return "\n".join(parts)

    lines = report.detail_lines()
    parts.append("以下内容无法完整保留：\n")
    parts.extend(lines)
    parts.append(
        "\n说明：蜜蜂办公会尽量保留能表达的内容；"
        "上面这些构造在导出时会丢失或降级，请自行确认。"
    )
    return "\n".join(parts)


def should_prompt_before_export(report: Optional[FidelityReport]) -> bool:
    """
    导出前是否要弹提示？

    只在**真会丢内容**（high）或**有明确说明**时提示；纯 medium 的降级不打扰用户。
    """
    if report is None:
        return False
    return report.has_high_losses or bool(report.note)
