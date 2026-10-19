# beeoffice/plugins/bee_export.py
"""
蜜写导出模块：Markdown → HTML / DOCX / PDF / 目录 / 对比 / GIF
以及 DOCX → Markdown 的导入功能

依赖（可选）：
  - markdown      Markdown 渲染
  - python-docx   DOCX 读写
  - beautifulsoup4 HTML 解析
  - Pillow        GIF 生成
  - WeasyPrint    PDF 导出（可选）

v5.0.2 图片导入修复：
  - import_from_docx 现在会提取 DOCX 内嵌图片
    - 支持 DrawingML（现代 Word）：<w:drawing>/<a:blip r:embed="rIdX"/>
    - 支持 VML（旧版 Word）：<w:pict>/<v:imagedata r:id="rIdX"/>
    - 图片导出到 <docx同名>_media/ 目录
    - Markdown 使用相对路径引用
  - 新增 _extract_para_images 辅助函数

v5.0.2 增强（本次）：
  - import_from_docx 新增：
    - 表格单元格图片提取（遍历 doc.tables）
    - 页眉/页脚图片提取（遍历 section.header/footer）
  - _extract_para_images 增强：
    - 添加详细调试日志（logging.debug）
    - 记录每个图片的 rId、扩展名、保存路径、文件大小
  - 新增 _iter_table_paragraphs 遍历表格单元格段落
  - 新增 _iter_header_footer_paragraphs 遍历页眉页脚段落
"""

import re
import os
import logging
import difflib
from pathlib import Path

from beeoffice.plugins.image_utils import (
    normalize_image_ref,
    resolve_image_path,
)
from beeoffice.utils import atomic_replace

# ==================== 可选依赖导入 ====================
try:
    import markdown
    HAS_MARKDOWN = True
except ImportError:
    HAS_MARKDOWN = False

try:
    # 这段的目的只是**探测 python-docx 是否可用**（HAS_DOCX），
    # 所以只导入后面真的用到的名字：Inches / WD_ALIGN_PARAGRAPH 全文件未使用
    # （第十一批 F401 清理核实；若将来用到，F821 门禁会立刻报出来）。
    from docx import Document
    from docx.shared import Pt, RGBColor, Cm
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# ==================== 常量 ====================
DOCX_DEFAULT_STYLE = "Normal"

# XML 命名空间（DOCX 图片解析使用）
_NS_DRAWINGML = (
    "http://schemas.openxmlformats.org/drawingml/2006/main"
)
_NS_RELATIONSHIPS = (
    "http://schemas.openxmlformats.org/officeDocument/"
    "2006/relationships"
)
_NS_VML = "urn:schemas-microsoft-com:vml"
_NS_WORD = (
    "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
)

# 支持的图片扩展名
_SUPPORTED_IMAGE_EXTS = {
    'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'emf', 'wmf', 'tiff'
}


# ==================== Markdown 渲染辅助 ====================
def _md_to_html(md_text):
    """Markdown 转 HTML 片段（含表格、代码块扩展）"""
    if not HAS_MARKDOWN:
        # 没有 markdown 库时，简单转义包裹
        escaped = (md_text.replace("&", "&amp;")
                          .replace("<", "&lt;")
                          .replace(">", "&gt;"))
        return f"<pre>{escaped}</pre>"
    return markdown.markdown(
        md_text,
        extensions=[
            'tables',
            'fenced_code',
            'codehilite',
            'toc',
            'nl2br',
            'sane_lists',
        ]
    )


def _md_to_html_full(md_text, title="BeeOffice 文档"):
    """Markdown 转完整 HTML 文档"""
    body = _md_to_html(md_text)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
    body {{
        font-family: -apple-system, "Segoe UI", "微软雅黑", sans-serif;
        max-width: 900px;
        margin: 0 auto;
        padding: 40px 20px;
        line-height: 1.8;
        color: #333;
    }}
    h1, h2, h3, h4, h5, h6 {{
        color: #E65100;
        margin-top: 1.5em;
        margin-bottom: 0.5em;
    }}
    h1 {{ border-bottom: 2px solid #FFB300; padding-bottom: 8px; }}
    h2 {{ border-bottom: 1px solid #FFE0B2; padding-bottom: 6px; }}
    pre {{
        background: #F5F5F5;
        padding: 12px 16px;
        border-radius: 6px;
        overflow-x: auto;
        border-left: 4px solid #FFB300;
    }}
    code {{
        background: #F5F5F5;
        padding: 2px 6px;
        border-radius: 3px;
        font-family: Consolas, Monaco, monospace;
        color: #D32F2F;
    }}
    table {{
        border-collapse: collapse;
        margin: 16px 0;
        width: 100%;
    }}
    th, td {{
        border: 1px solid #DDD;
        padding: 8px 12px;
        text-align: left;
    }}
    th {{ background: #FFF3E0; color: #E65100; font-weight: bold; }}
    tr:nth-child(even) {{ background: #FAFAFA; }}
    blockquote {{
        border-left: 4px solid #FFB300;
        padding-left: 16px;
        color: #666;
        font-style: italic;
        margin: 16px 0;
    }}
    img {{ max-width: 100%; height: auto; }}
    hr {{
        border: none;
        border-top: 1px solid #DDD;
        margin: 24px 0;
    }}
</style>
</head>
<body>
{body}
</body>
</html>"""


# ==================== 导出 Markdown ====================
def export_to_md(content):
    """
    Markdown 导出（本质是规范化处理）
    :param content: Markdown 文本
    :return: 规范化的 Markdown 文本
    """
    if content is None:
        return ""
    # 统一换行符
    text = content.replace("\r\n", "\n").replace("\r", "\n")
    # 去除文件末尾多余空白
    text = text.rstrip() + "\n"
    return text


# ==================== 导出 HTML ====================
def export_to_html(content, output_path):
    """
    Markdown 导出为 HTML 文件
    :param content: Markdown 文本
    :param output_path: 输出路径
    :return: 是否成功
    """
    try:
        # 提取标题
        title = "BeeOffice 文档"
        for line in content.split("\n"):
            m = re.match(r"^#\s+(.+)", line.strip())
            if m:
                title = m.group(1).strip()
                break

        html = _md_to_html_full(content, title)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        return True
    except Exception as e:
        logging.error(f"HTML 导出失败: {e}")
        return False


# ==================== 页面设置（单位：mm） ====================
#: 纸张尺寸（毫米）
PAPER_SIZES_MM = {
    "A4": (210, 297),
    "A3": (297, 420),
    "A5": (148, 210),
    "Letter": (216, 279),
    "Legal": (216, 356),
}


def apply_page_settings(doc, page_settings):
    """
    把页面设置应用到 docx 文档的第一个 section。

    **单位约定：页边距与纸张尺寸一律为毫米（mm）**（优化规划 §2.2）。
    页面设置对话框以厘米显示（存储值 /10）；DOCX 与 PDF 两条导出路径都直接
    按 mm 使用，不要再做 px→mm 换算。

    本函数是**唯一实现**，Markdown 路径（`export_to_docx`）与富文本路径
    （`ExportMixin._rich_to_docx`）共用。历史上 Markdown 路径完全没有应用
    页面设置，导致"导出 Word"的纸张与页边距取决于编辑器当时处于哪种模式。

    :param doc: python-docx 的 Document
    :param page_settings: dict，可含 paper / orientation / margin_*
    :return: 是否成功应用
    """
    if not page_settings:
        return False
    try:
        from docx.shared import Mm
        from docx.enum.section import WD_ORIENT

        w, h = PAPER_SIZES_MM.get(
            page_settings.get("paper", "A4"), PAPER_SIZES_MM["A4"]
        )
        landscape = page_settings.get("orientation") == "landscape"
        if landscape:
            w, h = h, w

        # 保真度阶段 A：允许显式指定精确尺寸（导入非标准纸张时必须，
        # 否则 5 种命名纸张之外的一律被当成 A4 —— 那是一次静默改变）。
        # 约定：page_width_mm / page_height_mm 是**已考虑方向之后**的最终尺寸。
        try:
            if page_settings.get("page_width_mm") \
                    and page_settings.get("page_height_mm"):
                w = float(page_settings["page_width_mm"])
                h = float(page_settings["page_height_mm"])
        except (TypeError, ValueError):
            pass

        section = doc.sections[0]
        section.page_width = Mm(w)
        section.page_height = Mm(h)
        section.top_margin = Mm(page_settings.get("margin_top", 25.4))
        section.bottom_margin = Mm(page_settings.get("margin_bottom", 25.4))
        section.left_margin = Mm(page_settings.get("margin_left", 31.7))
        section.right_margin = Mm(page_settings.get("margin_right", 31.7))
        section.orientation = (
            WD_ORIENT.LANDSCAPE if landscape else WD_ORIENT.PORTRAIT
        )
        return True
    except Exception as e:
        logging.warning(f"应用页面设置失败（使用文档默认值）: {e}")
        return False


def _read_table_merges(doc):
    """
    读出表格的合并信息（保真度阶段 A 最后一项）。

    Markdown 表格语法**表达不了合并**，所以导入时把它记下来（坐标用
    **网格列号**，与 `w:tblGrid` 对齐），导出时再还原。

    :return: [{"table": i, "row": r, "col": c, "colspan": n, "rowspan": m,
               "text": "合并后的文字"}, ...]
             `row`/`col` 为 0 起；`colspan`/`rowspan` 至少为 1。
    """
    from docx.oxml.ns import qn

    merges = []
    for t_idx, table in enumerate(doc.tables):
        tbl = table._tbl
        rows = tbl.findall(qn("w:tr"))
        # (起始行, 起始列) → 记录，用于累计纵向合并
        pending = {}

        for r_idx, tr in enumerate(rows):
            col = 0
            for tc in tr.findall(qn("w:tc")):
                tcPr = tc.find(qn("w:tcPr"))
                colspan = 1
                vmerge = None
                if tcPr is not None:
                    gs = tcPr.find(qn("w:gridSpan"))
                    if gs is not None:
                        try:
                            colspan = int(gs.get(qn("w:val")) or 1)
                        except (TypeError, ValueError):
                            colspan = 1
                    vm = tcPr.find(qn("w:vMerge"))
                    if vm is not None:
                        vmerge = vm.get(qn("w:val")) or "continue"

                text = "".join(
                    t.text or "" for t in tc.iter(qn("w:t"))
                ).strip()

                if vmerge == "continue":
                    # 纵向合并的延续行：给起始记录加一行跨度
                    record = pending.get((None, col))
                    if record is not None:
                        record["rowspan"] += 1
                elif vmerge == "restart" or colspan > 1:
                    record = {
                        "table": t_idx, "row": r_idx, "col": col,
                        "colspan": colspan, "rowspan": 1, "text": text,
                    }
                    merges.append(record)
                    if vmerge == "restart":
                        pending[(None, col)] = record

                col += colspan

    return merges


def _read_nested_tables(doc):
    """
    读出**嵌套表格**（单元格里的表格）——保真度阶段 A 的收尾项。

    为什么必须走 extras：Markdown 表格语法**表达不了嵌套**，
    导入→导出后内层表格会**整块消失**（实测：表 2→1、内层文字一并丢失）。
    而合并单元格、书签、分节都已经在用这条路，所以这里沿用同一套做法。

    **保真范围（如实说明）**：只保 **结构 + 文字**（几行几列、每格文字）。
    内层的**字符格式/边框/底色不保** —— 那需要把整段 OOXML 搬过去，
    与本项目"用 extras 记语义、导出时重建"的既有取舍一致。
    只处理**一层**嵌套（更深的层级跳过，避免记录结构无限膨胀）。

    :return: [{"table": i, "row": r, "col": c,
               "cells": [[文字, ...], ...]}, ...]
             `table` 是**顶层**表格序号；`row`/`col` 是顶层表格里的 0 起坐标。
    """
    from docx.oxml.ns import qn

    records = []
    for t_idx, table in enumerate(doc.tables):
        # 用 XML 直接数行/列，避免 `table.rows` 在异常结构上抛错
        trs = table._tbl.findall(qn("w:tr"))
        for r_idx, tr in enumerate(trs):
            col = 0
            for tc in tr.findall(qn("w:tc")):
                tcPr = tc.find(qn("w:tcPr"))
                colspan = 1
                if tcPr is not None:
                    gs = tcPr.find(qn("w:gridSpan"))
                    if gs is not None:
                        try:
                            colspan = int(gs.get(qn("w:val")) or 1)
                        except (TypeError, ValueError):
                            colspan = 1

                nested = tc.find(qn("w:tbl"))
                if nested is not None:
                    cells = []
                    for nested_tr in nested.findall(qn("w:tr")):
                        row_cells = []
                        for nested_tc in nested_tr.findall(qn("w:tc")):
                            text = "".join(
                                t.text or ""
                                for t in nested_tc.iter(qn("w:t"))
                            ).strip()
                            row_cells.append(text)
                        cells.append(row_cells)
                    if cells:
                        records.append({
                            "table": t_idx, "row": r_idx, "col": col,
                            "cells": cells,
                        })
                col += colspan
    return records


def apply_nested_tables(doc, nested_tables):
    """
    把嵌套表格还原到导出的文档上（`_read_nested_tables` 的逆操作）。

    做法：找到顶层单元格 → 在它里面 `add_table` → 写入文字。
    单元格里原有的空段落保留（Word 要求单元格内至少有一个段落）。

    :return: 成功还原的嵌套表格数
    """
    if not nested_tables:
        return 0

    from docx.oxml.ns import qn

    applied = 0
    for record in nested_tables:
        try:
            t_idx = int(record.get("table", 0))
            if t_idx < 0 or t_idx >= len(doc.tables):
                continue
            table = doc.tables[t_idx]
            row = int(record.get("row", 0))
            col = int(record.get("col", 0))
            cells = record.get("cells") or []
            if not cells:
                continue

            trs = table._tbl.findall(qn("w:tr"))
            if row < 0 or row >= len(trs):
                continue
            tcs = trs[row].findall(qn("w:tc"))
            if col < 0 or col >= len(tcs):
                continue

            target = table.cell(row, col)
            # 若已存在嵌套表（重复还原），先跳过，避免叠加
            if target.tables:
                continue

            n_rows = len(cells)
            n_cols = max(len(r) for r in cells)
            nested = target.add_table(rows=n_rows, cols=n_cols)
            for r, row_cells in enumerate(cells):
                for c in range(n_cols):
                    text = row_cells[c] if c < len(row_cells) else ""
                    if text:
                        nested.cell(r, c).text = text
            applied += 1
        except Exception as e:  # noqa: BLE001 - 单个表失败不该让导出整体失败
            logging.debug(f"还原嵌套表格失败（已跳过）：{e}")
    return applied


def apply_table_merges(doc, table_merges):
    """
    把合并信息还原到导出的文档上。

    `python-docx` 的 `merge()` 会把两个单元格的**文字拼接**起来，所以合并后
    用记录里的原文覆盖，避免出现"合计合计"。

    :param doc: python-docx 的 Document
    :param table_merges: `read_docx_extras()` 返回的 table_merges
    :return: 成功应用的合并数
    """
    if not table_merges:
        return 0

    from docx.oxml.ns import qn

    applied = 0
    for record in table_merges:
        try:
            t_idx = int(record.get("table", 0))
            if t_idx < 0 or t_idx >= len(doc.tables):
                continue
            table = doc.tables[t_idx]

            row = int(record.get("row", 0))
            col = int(record.get("col", 0))
            rowspan = max(1, int(record.get("rowspan", 1)))
            colspan = max(1, int(record.get("colspan", 1)))
            if rowspan == 1 and colspan == 1:
                continue

            n_rows = len(table._tbl.findall(qn("w:tr")))
            grid = len(table.columns)
            if row + rowspan > n_rows or col + colspan > grid:
                logging.debug(
                    f"跳过越界的合并（表 {t_idx} {row},{col} "
                    f"{rowspan}x{colspan}；表 {n_rows} 行 {grid} 列）"
                )
                continue

            first = table.cell(row, col)
            last = table.cell(row + rowspan - 1, col + colspan - 1)
            merged = first.merge(last)

            text = record.get("text", "")
            if text:
                # merge() 会拼接文字；用原文覆盖，避免重复
                merged.text = text
            applied += 1
        except Exception as e:  # noqa: BLE001 - 单个表格失败不应中断导出
            logging.warning(f"应用表格合并失败: {e}")

    return applied


def _read_sections(doc):
    """
    读出**每个分节**的页面属性与它在文档中的位置（保真度阶段 A）。

    为什么不能只读第一节：`docx_sections.docx` 这类文档有 2 个分节（第二节横向），
    原先往返后 `sections 2 → 1` —— 用户可见后果是**横向页变成纵向**。

    OOXML 的表示：每个分节的 `w:sectPr` 挂在**该节最后一个段落**的
    `w:pPr` 里；最后一节的 `sectPr` 挂在 body 上。

    **定位用文字而不是段落索引**：持有 `sectPr` 的段落常常是**空段落**
    （`add_section()` 就是新建一个空段承载它），而空段落在 Markdown 里会丢
    （实测顶层段落 5 → 4）。所以记录"该节最后一个**非空**段落的文字"作锚点，
    导出时按文字定位，才是稳的。

    :return: [{"end_paragraph": int|None, "after_text": str,
               "page_width_mm", "page_height_mm", "orientation",
               "margin_top/bottom/left/right"}, ...]
    """
    from docx.oxml.ns import qn

    paragraphs = list(doc.paragraphs)

    def _locate(sectPr):
        """返回持有该 sectPr 的段落索引；body 级的返回 None。"""
        for idx, para in enumerate(paragraphs):
            pPr = para._p.find(qn("w:pPr"))
            if pPr is None:
                continue
            found = pPr.find(qn("w:sectPr"))
            if found is not None and found is sectPr:
                return idx
        return None

    def _mm(length):
        try:
            return round(float(length.mm), 2)
        except Exception:
            return None

    def _last_non_empty_text(before_idx):
        """向上找该节最后一个非空段落的文字（作为定位锚点）。"""
        for idx in range(before_idx, -1, -1):
            text = (paragraphs[idx].text or "").strip()
            if text:
                return text
        return ""

    sections = []
    for sect in doc.sections:
        width = _mm(sect.page_width)
        height = _mm(sect.page_height)
        landscape = bool(width and height and width > height)

        end_paragraph = _locate(sect._sectPr)
        sections.append({
            "end_paragraph": end_paragraph,
            "after_text": (
                _last_non_empty_text(end_paragraph)
                if end_paragraph is not None else ""
            ),
            "page_width_mm": width,
            "page_height_mm": height,
            "orientation": "landscape" if landscape else "portrait",
            "margin_top": _mm(sect.top_margin),
            "margin_bottom": _mm(sect.bottom_margin),
            "margin_left": _mm(sect.left_margin),
            "margin_right": _mm(sect.right_margin),
        })

    return sections


def apply_sections(doc, sections):
    """
    按记录重建分节（保真度阶段 A）。

    定位策略：优先按 `after_text`（该节最后一个非空段落的文字）匹配，匹配不到
    再退回 `end_paragraph` 索引。前者对"空段落丢失导致的索引偏移"免疫。

    :return: 成功重建的分节数（不含最后一节）
    """
    if not sections:
        return 0

    from copy import deepcopy

    from docx.oxml.ns import qn

    applied = 0
    paragraphs = list(doc.paragraphs)

    # 用 body 级的 sectPr 作为骨架：它已含 pgSz/pgMar/cols/docGrid 等，
    # 只改尺寸与边距即可，避免手搓出不符合 schema 的 sectPr。
    try:
        base = doc.sections[-1]._sectPr
    except Exception:
        return 0

    for record in sections[:-1]:
        target = None

        after_text = (record.get("after_text") or "").strip()
        if after_text:
            for para in paragraphs:
                if (para.text or "").strip() == after_text:
                    target = para
                    break

        if target is None:
            idx = record.get("end_paragraph")
            if isinstance(idx, int) and 0 <= idx < len(paragraphs):
                target = paragraphs[idx]

        if target is None:
            logging.debug(f"找不到分节锚点，跳过: {record}")
            continue

        try:
            new_sect = deepcopy(base)
            _fill_sect_pr(new_sect, record, qn)
            pPr = target._p.get_or_add_pPr()
            for existing in pPr.findall(qn("w:sectPr")):
                pPr.remove(existing)
            pPr.append(new_sect)
            applied += 1
        except Exception as e:  # noqa: BLE001 - 单个分节失败不应中断导出
            logging.warning(f"重建分节失败: {e}")

    # 最后一节：填 body 级的 sectPr
    try:
        _fill_sect_pr(base, sections[-1], qn)
    except Exception as e:  # noqa: BLE001
        logging.warning(f"应用最后一节属性失败: {e}")

    return applied


def _fill_sect_pr(sectPr, record, qn):
    """把纸张尺寸/方向/页边距写进一个 sectPr（mm → twips）。"""
    from docx.oxml import OxmlElement
    from docx.shared import Mm

    width = record.get("page_width_mm")
    height = record.get("page_height_mm")
    if width and height:
        pgSz = sectPr.find(qn("w:pgSz"))
        if pgSz is None:
            pgSz = OxmlElement("w:pgSz")
            sectPr.insert(0, pgSz)
        pgSz.set(qn("w:w"), str(int(Mm(float(width)).twips)))
        pgSz.set(qn("w:h"), str(int(Mm(float(height)).twips)))
        if record.get("orientation") == "landscape":
            pgSz.set(qn("w:orient"), "landscape")
        else:
            pgSz.attrib.pop(qn("w:orient"), None)

    pgMar = sectPr.find(qn("w:pgMar"))
    if pgMar is None:
        pgMar = OxmlElement("w:pgMar")
        sectPr.append(pgMar)
    for key, attr in (
        ("margin_top", "w:top"), ("margin_bottom", "w:bottom"),
        ("margin_left", "w:left"), ("margin_right", "w:right"),
    ):
        value = record.get(key)
        if value is not None:
            pgMar.set(qn(attr), str(int(Mm(float(value)).twips)))


def _read_bookmarks(doc):
    """
    读出文档里的书签（保真度阶段 A）。

    为什么需要：Markdown 没有书签语法。实测 7 份真实教程里有 **5 份**带书签，
    往返后 `bookmarks 1 → 0`。

    ⚠️ **但那些书签名全是 `_GoBack`** —— Word 的"上次编辑位置"内部标记，
    **不是用户内容**，丢失它不会让任何链接变成死链。这一点我最初判断错了
    （以为多半是目录锚点 `_Toc…`），已更正到 docs/fidelity.md。
    即便如此仍然**原样保留**：本工作的目标是"往返不改动用户的文件"，而
    `_GoBack` 是文件的一部分；顺带也让"书签"这个指标保持可比。
    真正的用户书签（`_Toc…`、自定义锚点）同样走这条通路。

    定位方式与分节一致：记下"书签所在段落的文字"作锚点。Markdown 无法表达
    段内偏移，所以还原时放在**该段落开头** —— 对目录锚点（书签本来就在标题
    段首）是完全正确的；对段中书签是近似。

    :return: [{"name": str, "paragraph_text": str, "prev_text": str,
               "index": int}, ...]
             `prev_text` 是"最近的前一个非空段落"，用于**书签落在空段落里**的情况
             （实测两份真实文档的 `_GoBack` 就是空的；空段落在 Markdown 里会丢，
             此时索引锚点必然失效）。
    """
    from docx.oxml.ns import qn

    paragraphs = list(doc.paragraphs)

    bookmarks = []
    for para_idx, para in enumerate(paragraphs):
        starts = para._p.findall(qn("w:bookmarkStart"))
        if not starts:
            continue

        # 最近的前一个非空段落（供空段落锚点使用）
        prev_text = ""
        for back in range(para_idx - 1, -1, -1):
            candidate = (paragraphs[back].text or "").strip()
            if candidate:
                prev_text = candidate
                break

        for start in starts:
            name = start.get(qn("w:name")) or ""
            if not name:
                continue
            bookmarks.append({
                "name": name,
                "paragraph_text": (para.text or "").strip(),
                "prev_text": prev_text,
                "index": para_idx,
            })
    return bookmarks


def apply_bookmarks(doc, bookmarks):
    """
    按记录写回书签（`w:bookmarkStart` / `w:bookmarkEnd`）。

    - 定位：优先按 `paragraph_text` 匹配（对空段落丢失导致的索引偏移免疫），
      找不到再退回 `index`；都找不到就跳过（记 debug 日志）。
    - 位置：插在该段**开头**（在 `w:pPr` 之后，否则 schema 不合法）。

    :return: 成功写回的书签数
    """
    if not bookmarks:
        return 0

    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    paragraphs = list(doc.paragraphs)
    applied = 0
    next_id = 1000        # 避开源文档可能用过的 id

    for record in bookmarks:
        target = None

        text = (record.get("paragraph_text") or "").strip()
        if text:
            for para in paragraphs:
                if (para.text or "").strip() == text:
                    target = para
                    break

        if target is None:
            # 书签落在**空段落**里（真实文档的 `_GoBack` 就是这样）：空段落在
            # Markdown 里会丢，索引必然失效。退化为"挂到最近的前一个非空段落之后"。
            prev_text = (record.get("prev_text") or "").strip()
            if prev_text:
                for pos, para in enumerate(paragraphs):
                    if (para.text or "").strip() == prev_text:
                        target = (
                            paragraphs[pos + 1]
                            if pos + 1 < len(paragraphs) else para
                        )
                        break

        if target is None:
            idx = record.get("index")
            if isinstance(idx, int) and 0 <= idx < len(paragraphs):
                target = paragraphs[idx]

        if target is None:
            logging.debug(f"找不到书签锚点，跳过: {record}")
            continue

        try:
            bookmark_id = str(next_id)
            next_id += 1

            start = OxmlElement("w:bookmarkStart")
            start.set(qn("w:id"), bookmark_id)
            start.set(qn("w:name"), str(record.get("name") or ""))

            end = OxmlElement("w:bookmarkEnd")
            end.set(qn("w:id"), bookmark_id)

            p = target._p
            pPr = p.find(qn("w:pPr"))
            # 必须插在 pPr 之后（pPr 必须是 w:p 的第一个子元素），
            # 并且**跳过已有的 bookmarkStart** —— 否则同一段落里的多个书签
            # 会因每次插在同一位置而**顺序颠倒**（实测 b1,b2 → b1,b3,b2）。
            children = list(p)
            pos = (children.index(pPr) + 1) if pPr is not None else 0
            while pos < len(children) \
                    and children[pos].tag == qn("w:bookmarkStart"):
                pos += 1
            p.insert(pos, start)
            p.append(end)
            applied += 1
        except Exception as e:  # noqa: BLE001 - 单个书签失败不应中断导出
            logging.warning(f"写回书签失败: {e}")

    return applied


def _read_paragraph_styles(doc):
    """
    读出**非默认样式**的段落（保真度阶段 A）。

    实测 7 份真实教程里 3 份用了内置样式，且都很有意义：

    | 样式 | 命中 | 作用 |
    |---|---|---|
    | `HTML Preformatted` | 41 段（`yum源更新.docx`） | Word 给预格式化/代码文本的**等宽**样式 |
    | `Normal (Web)` | 2 段 ×2 份 | Word 的网页版式 Normal |

    丢失后果：技术文档里 41 段代码记录退化成普通正文，等宽版式全丢。

    :return: [{"style": 样式名, "paragraph_text": str, "index": int}, ...]
    """
    records = []
    for idx, para in enumerate(doc.paragraphs):
        try:
            name = para.style.name
        except Exception:
            continue
        if not name or name == "Normal":
            continue
        records.append({
            "style": name,
            "paragraph_text": _paragraph_text(para).strip(),
            "index": idx,
        })
    return records


def _style_name_of(style_element) -> str:
    from docx.oxml.ns import qn

    name_el = style_element.find(qn("w:name"))
    if name_el is None:
        return ""
    return name_el.get(qn("w:val")) or ""


def _read_style_definitions(doc, names):
    """
    把需要的样式**定义**序列化出来（含 `w:basedOn` 链）。

    为什么必须搬定义：python-docx 的默认模板里**没有** `HTML Preformatted` /
    `Normal (Web)`（实测默认模板 164 个样式里都没有），只记名字的话导出时
    `doc.styles[name]` 直接 KeyError，样式装不回去。

    :return: {样式名: w:style 元素的 XML 字符串}
    """
    from lxml import etree
    from docx.oxml.ns import qn

    by_name, by_id = {}, {}
    for style in doc.styles.element.findall(qn("w:style")):
        style_id = style.get(qn("w:styleId")) or ""
        if style_id:
            by_id[style_id] = style
        name = _style_name_of(style)
        if name:
            by_name[name] = style

    definitions = {}
    pending = list(names)
    while pending:
        name = pending.pop()
        if name in definitions or name not in by_name:
            continue
        style = by_name[name]
        try:
            definitions[name] = etree.tostring(style, encoding="unicode")
        except Exception:
            continue
        # basedOn 用的是 styleId，需要换成名字继续追
        based_on = style.find(qn("w:basedOn"))
        if based_on is not None:
            base_style = by_id.get(based_on.get(qn("w:val")) or "")
            base_name = _style_name_of(base_style) if base_style is not None \
                else ""
            if base_name:
                pending.append(base_name)
    return definitions


def apply_paragraph_styles(doc, records, definitions=None):
    """
    把段落样式装回导出的文档。

    两步：
      1. **先注入样式定义**（`definitions`）—— 目标模板里可能没有这些样式；
         注入时若 `w:styleId` 撞车则改名，若同名样式已存在则跳过。
      2. 按锚点定位段落（文字 → 索引）并设置样式。

    :return: 成功应用样式的段落数
    """
    if not records:
        return 0

    from docx.oxml import parse_xml
    from docx.oxml.ns import qn

    styles_root = doc.styles.element
    existing_names = {_style_name_of(s) for s in
                      styles_root.findall(qn("w:style"))}
    existing_ids = {s.get(qn("w:styleId")) for s in
                    styles_root.findall(qn("w:style"))}

    # ---- 1. 注入定义 ----
    for name, xml in (definitions or {}).items():
        if not name or name in existing_names:
            continue
        try:
            # ⚠️ 必须用 python-docx 自己的解析器：`lxml.etree.fromstring` 造出的
            # 是裸 `_Element`，没有 python-docx 元素类的 `.type` 属性，
            # `doc.styles[...]` 会抛 AttributeError（曾被宽 except 吞掉、静默返回 0）。
            element = parse_xml(xml)
        except Exception as e:
            logging.debug(f"样式定义解析失败（跳过）{name}: {e}")
            continue

        style_id = element.get(qn("w:styleId")) or ""
        if style_id in existing_ids:
            new_id = f"{style_id}_copy"
            suffix = 2
            while new_id in existing_ids:
                new_id = f"{style_id}_copy{suffix}"
                suffix += 1
            element.set(qn("w:styleId"), new_id)

        # basedOn 若指向目标里不存在的 id，去掉它，避免悬空引用
        based_on = element.find(qn("w:basedOn"))
        if based_on is not None \
                and (based_on.get(qn("w:val")) or "") not in existing_ids:
            element.remove(based_on)

        styles_root.append(element)
        existing_names.add(name)
        existing_ids.add(element.get(qn("w:styleId")))

    # ---- 2. 应用 ----
    paragraphs = list(doc.paragraphs)
    applied = 0
    # 记录已用过的段落：正文里常有**内容完全相同**的段落（实测 41 段代码记录里
    # 就有重复），只按"第一个文字相同"去匹配会让它们全部落到同一段上，
    # 导致 43 段里只有 36 段装上样式。
    used = set()

    for record in records:
        target = None
        position = None

        text = (record.get("paragraph_text") or "").strip()
        if text:
            for pos, para in enumerate(paragraphs):
                if pos in used:
                    continue
                if _paragraph_text(para).strip() == text:
                    target, position = para, pos
                    break

        if target is None:
            idx = record.get("index")
            if isinstance(idx, int) and 0 <= idx < len(paragraphs) \
                    and idx not in used:
                target, position = paragraphs[idx], idx

        if target is None:
            continue

        try:
            target.style = doc.styles[record.get("style")]
            if position is not None:
                used.add(position)
            applied += 1
        except KeyError:
            logging.debug(f"目标文档没有样式 {record.get('style')!r}，跳过")
        except Exception as e:  # noqa: BLE001
            logging.debug(f"应用段落样式失败: {e}")

    return applied


# ==================== 导入侧：读取页面设置与页眉页脚 ====================
def read_docx_extras(docx_path):
    """
    读取 DOCX 里**Markdown 表达不了**的信息（保真度阶段 A）。

    为什么需要单独一个函数：`import_from_docx()` 的返回值是 Markdown 字符串，
    而 Markdown 没有"页面设置/页眉页脚"这些概念 —— 信息在第一步就丢了。
    实测症状：往返后 `page_margins` 变成 python-docx 默认 1 英寸、
    `header_parts` / `footer_parts` 直接归零（部件根本不存在）。

    调用方（`app._open_docx_file`）把它交给编辑器的 `apply_docx_extras()`，
    导出时再原样写回，从而**绕开 Markdown** 传递这些信息。

    :return: dict；解析失败时返回 {}（调用方按"无扩展信息"处理）
    """
    if not HAS_DOCX:
        return {}
    try:
        doc = Document(str(docx_path))
        section = doc.sections[0]

        def _mm(length):
            try:
                return round(float(length.mm), 2)
            except Exception:
                return None

        width = _mm(section.page_width)
        height = _mm(section.page_height)

        # 方向：宽 > 高 视为横向；纸张名字按"未旋转"的尺寸匹配
        landscape = bool(width and height and width > height)
        if landscape:
            short, long_ = height, width
        else:
            short, long_ = width, height

        paper = ""
        for name, (pw, ph) in PAPER_SIZES_MM.items():
            if short is not None and long_ is not None \
                    and abs(short - pw) <= 1 and abs(long_ - ph) <= 1:
                paper = name
                break

        def _text(part):
            # 用 _paragraph_text 而不是 p.text：页脚的页码在**域**里，
            # p.text 返回空串（实测 3 份真实文档的页脚都因此被当成空的）
            try:
                return "\n".join(
                    _paragraph_text(p) for p in part.paragraphs
                    if _paragraph_text(p).strip()
                ).strip()
            except Exception:
                return ""

        # 页眉/页脚**部件 XML**：优先整段搬运，以保留域（页码）与内容控件
        # （python-docx 不进入 w:sdt，文字提取会得到空串）。
        header_xml = footer_xml = ""
        try:
            if not section.header.is_linked_to_previous:
                candidate = _serialize_part(section.header)
                if candidate and not _part_has_external_refs(candidate):
                    header_xml = candidate
            if not section.footer.is_linked_to_previous:
                candidate = _serialize_part(section.footer)
                if candidate and not _part_has_external_refs(candidate):
                    footer_xml = candidate
        except Exception as e:
            logging.debug(f"序列化页眉页脚失败，退回文字: {e}")

        extras = {
            "paper": paper or "A4",
            "page_width_mm": width,
            "page_height_mm": height,
            "orientation": "landscape" if landscape else "portrait",
            "margin_top": _mm(section.top_margin),
            "margin_bottom": _mm(section.bottom_margin),
            "margin_left": _mm(section.left_margin),
            "margin_right": _mm(section.right_margin),
            "header_text": _text(section.header),
            "footer_text": _text(section.footer),
            "header_xml": header_xml,
            "footer_xml": footer_xml,
            "table_merges": _read_table_merges(doc),
            "nested_tables": _read_nested_tables(doc),
            "sections": _read_sections(doc),
            "bookmarks": _read_bookmarks(doc),
            "paragraph_styles": _read_paragraph_styles(doc),
            "style_definitions": _read_style_definitions(
                doc,
                {r["style"] for r in _read_paragraph_styles(doc)},
            ),
        }
        # 去掉解析不到的项（None），让调用方的默认值生效
        return {k: v for k, v in extras.items() if v is not None}
    except Exception as e:
        logging.warning(f"读取 DOCX 扩展信息失败: {e}")
        return {}


#: 序列化/反序列化页眉页脚部件时需要声明的前缀（源文件里可能用到任意一个）
_PART_NAMESPACES = (
    "xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\" "
    "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" "
    "xmlns:wp=\"http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing\" "
    "xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" "
    "xmlns:pic=\"http://schemas.openxmlformats.org/drawingml/2006/picture\" "
    "xmlns:wps=\"http://schemas.microsoft.com/office/word/2010/wordprocessingShape\" "
    "xmlns:wpg=\"http://schemas.microsoft.com/office/word/2010/wordprocessingGroup\" "
    "xmlns:mc=\"http://schemas.openxmlformats.org/markup-compatibility/2006\" "
    "xmlns:v=\"urn:schemas-microsoft-com:vml\""
)


def _serialize_part(part) -> str:
    """
    把页眉/页脚部件的子元素序列化成字符串。

    为什么整段搬运而不是只取文字：实测 3 份真实文档的页脚把页码放在
    **嵌套的 `w:sdt`（内容控件）**里，而 python-docx **不进入 `w:sdt`** ——
    `section.footer.paragraphs` 只返回一个空段落，于是文字提取得到空串、
    整个页脚部件都不写。搬运 XML 可以连域（PAGE / NUMPAGES）与内容控件一起保留。
    """
    from lxml import etree

    try:
        element = part._element
    except Exception:
        return ""

    chunks = []
    for child in element:
        try:
            chunks.append(etree.tostring(child, encoding="unicode"))
        except Exception:
            return ""
    return "".join(chunks)


def _part_has_external_refs(xml: str) -> bool:
    """
    部件里是否有**关系引用**（图片等）。

    这类内容不能只靠搬家 XML —— 关系 id 在新文档里不存在，搬过去会变成悬空引用
    （Word 会报文档损坏）。检出后改用"文字"路径，宁少勿坏。
    """
    for token in ('r:id="', 'r:embed="', 'r:link="'):
        if token in xml:
            return True
    return False


def apply_header_footer(doc, header_text=None, footer_text=None,
                        header_xml="", footer_xml=""):
    """
    写回页眉/页脚。

    **优先按 XML 搬运**（`header_xml`/`footer_xml`）—— 这样域（页码）与内容控件
    都能保留；仅在部件含关系引用（图片）或解析失败时退回"只写文字"。

    空字符串视为"不写"，避免把用户原本没有的页眉变成空段落。
    """
    if not any((header_text, footer_text, header_xml, footer_xml)):
        return False

    from docx.oxml import parse_xml

    section = doc.sections[0]
    applied = False

    for attr, xml, text in (
        ("header", header_xml, header_text),
        ("footer", footer_xml, footer_text),
    ):
        if not xml and not text:
            continue
        try:
            part = getattr(section, attr)

            if xml:
                # 断开"继承上一节"，从而生成一个真实的部件
                part.is_linked_to_previous = False
                # 同样必须用 python-docx 的解析器，否则搬进去的是裸 lxml 元素，
                # 后续 python-docx 的 API（part.paragraphs 等）会用不了
                wrapper = parse_xml(
                    f"<w:root {_PART_NAMESPACES}>{xml}</w:root>"
                )
                element = part._element
                for child in list(element):
                    element.remove(child)
                for child in wrapper:
                    element.append(child)
                applied = True
                continue

            # 退路：只写文字
            paragraphs = part.paragraphs
            if paragraphs:
                paragraphs[0].text = text
            else:
                part.add_paragraph(text)
            applied = True
        except Exception as e:  # noqa: BLE001 - 页眉页脚失败不应中断导出
            logging.warning(f"写入{attr}失败: {e}")

    return applied


# ==================== 导出 DOCX ====================
def export_to_docx(content, output_path, page_settings=None, base_dir=None,
                   header_text=None, footer_text=None, table_merges=None,
                   sections=None, bookmarks=None,
                   header_xml="", footer_xml="",
                   paragraph_styles=None, style_definitions=None,
                   nested_tables=None):
    """
    Markdown 导出为 DOCX 文件

    :param content: Markdown 文本
    :param output_path: 输出路径
    :param page_settings: 页面设置（单位 mm，见 apply_page_settings）。
        为 None 时沿用 python-docx 默认模板（保持向后兼容）。
    :param base_dir: Markdown 所在目录，用于解析**相对图片路径**
        （优化规划 §2.6）。为 None 时相对路径按当前工作目录解析。
    :param header_text: 页眉文字（保真度阶段 A）。为 None/空串时不写页眉。
    :param footer_text: 页脚文字，同上。
    :param table_merges: 表格合并信息（`read_docx_extras()` 的 table_merges）。
        Markdown 表格语法表达不了合并，故**绕开 Markdown** 传递。
    :param sections: 分节信息（`read_docx_extras()` 的 sections）。为 None 时
        按 `page_settings` 只设置第一节（原行为）。
    :param bookmarks: 书签信息（`read_docx_extras()` 的 bookmarks）。
    :param paragraph_styles: 段落样式信息（`read_docx_extras()` 的
        paragraph_styles）。
    :param style_definitions: 样式**定义**（`read_docx_extras()` 的
        style_definitions）——目标模板里往往没有这些样式（实测默认模板
        164 个样式里没有 `HTML Preformatted`），必须连定义一起注入。
    :return: 是否成功
    """
    if not HAS_DOCX:
        logging.error("python-docx 未安装，无法导出 DOCX")
        return False

    # 优化规划 §3.3：markdown 与 beautifulsoup4 在 requirements.txt 里是**必需**
    # 依赖，因此"缺依赖时逐行转换"的降级实现 `_write_plain_to_docx()` 实际不可达
    # （38 行、零测试覆盖）。已删除：缺依赖时明确失败，而不是悄悄产出一份
    # 低保真的 DOCX —— 后者会让用户以为导出成功了。
    if not (HAS_BS4 and HAS_MARKDOWN):
        logging.error(
            "DOCX 导出需要 markdown 与 beautifulsoup4（requirements.txt 中的"
            "必需依赖）。缺少时不再降级为逐行转换，而是明确失败。"
        )
        return False

    try:
        # 用 HTML 中间层解析
        html = _md_to_html(content)
        soup = BeautifulSoup(html, "html.parser")
        doc = Document()
        _write_html_to_docx(soup, doc, base_dir=base_dir)

        # 页面设置（优化规划 §2.2）：此前 Markdown 路径完全没有应用，
        # 于是导出的纸张是 python-docx 模板默认值，与富文本路径不一致。
        # 保真度阶段 A：若有**多分节**记录，则按分节重建（它会一并处理第一节）；
        # 否则退回原来的单节应用方式。
        if sections:
            apply_sections(doc, sections)
        else:
            apply_page_settings(doc, page_settings)

        # 页眉页脚（保真度阶段 A）：原先**整个部件都不存在**，
        # 因为导入侧只返回 Markdown，信息没有承载者。
        # 优先按部件 XML 搬运（保留页码域与内容控件），退回文字。
        apply_header_footer(
            doc, header_text, footer_text,
            header_xml=header_xml, footer_xml=footer_xml,
        )

        # 表格合并（保真度阶段 A 最后一项）：Markdown 表格语法表达不了合并，
        # 因此由导入时记录的 table_merges 还原。
        apply_table_merges(doc, table_merges)

        # 嵌套表格（阶段 A 收尾）：Markdown 更表达不了"单元格里的表格"，
        # 不还原就会整块消失（实测 表 2→1、内层文字一并丢）。
        apply_nested_tables(doc, nested_tables)

        # 书签（阶段 A）：Markdown 无书签语法，实测 5/7 份真实文档带书签；
        # 丢失会让指向它的内部跳转变成死链。
        apply_bookmarks(doc, bookmarks)

        # 段落样式（阶段 A）：实测 41 段代码记录用的是内置等宽样式
        # `HTML Preformatted`，而 python-docx 默认模板里**没有**这个样式，
        # 所以必须连**样式定义**一起搬（否则 doc.styles[name] 直接 KeyError）。
        apply_paragraph_styles(doc, paragraph_styles, style_definitions)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        # P0 止血：先写同目录临时文件再原子替换 —— 写到一半崩溃不会把
        # 用户原有的 docx 留成半份（审计 §4.3 G2）。
        with atomic_replace(output_path) as tmp_path:
            doc.save(str(tmp_path))
        return True
    except Exception as e:
        logging.error(f"DOCX 导出失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def _write_html_to_docx(soup, doc, base_dir=None):
    """将 BeautifulSoup 树写入 docx 文档

    :param base_dir: Markdown 所在目录，用于解析相对图片路径（优化规划 §2.6）
    """
    for element in soup.children:
        _write_element(element, doc, base_dir=base_dir)


def _resolve_image_path(src, base_dir=None):
    """
    把 Markdown / HTML 里的图片地址解析成本地可读路径。

    优化规划 §2.6：MD→DOCX 原先**完全丢弃图片**（`<img>` 既没有分支处理，
    其 `get_text()` 又是空串，于是被静默跳过），导出的 Word 里图片全没了。

    优化规划 §3.3：规范化与"逐个候选目录"的逻辑统一走 `image_utils`
    （原先这里自行 `urlparse`，会把 Windows 盘符 `D:` 当成 URL scheme 而**丢掉
    盘符** —— 本机工作区恰好在 D 盘，于是这个缺陷被"同盘巧合"掩盖了）。

    支持：绝对路径、相对路径（相对 Markdown 所在目录，其次当前目录）、
    `file:///C:/...` 与 `%20` 转义。
    远程 http(s) 图片不联网下载，返回 None（由调用方给出可见占位）。
    """
    if not src:
        return None

    lowered = str(src).strip().lower()
    if lowered.startswith(("http://", "https://")):
        return None

    normalized = normalize_image_ref(src)
    if not normalized:
        return None

    # 相对路径：先相对 Markdown 所在目录，再相对当前工作目录
    base_dirs = [base_dir, "."] if base_dir else ["."]
    resolved, _ = resolve_image_path(
        normalized, base_dirs, home_fallback=False
    )
    return resolved


def _add_hyperlink(paragraph, url, text):
    """
    在段落中插入**真正可点击**的超链接。

    python-docx 没有公开的超链接 API，需要自己拼 `w:hyperlink` 与外部关系。
    优化规划 §2.6：原实现只把链接文字染成蓝色加下划线，`href` 直接丢失，
    导出的 Word 里链接既不可点、也看不出指向哪里。
    """
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.opc.constants import RELATIONSHIP_TYPE as RT

    r_id = paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True)

    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)

    new_run = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")

    color = OxmlElement("w:color")
    color.set(qn("w:val"), "1565C0")
    rPr.append(color)

    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    rPr.append(underline)

    new_run.append(rPr)
    text_el = OxmlElement("w:t")
    text_el.text = text
    # 注意：不能用 qn("xml:space") —— python-docx 的 nsmap 里没有 xml 前缀，
    # qn() 会直接 KeyError（实测会让整条插入超链接的语句抛异常，进而被
    # 上层 except 降级为纯文本，用户看到的还是不可点的链接）。
    # 这里使用 XML 命名空间的完整 URI。
    text_el.set(
        "{http://www.w3.org/XML/1998/namespace}space", "preserve"
    )
    new_run.append(text_el)
    hyperlink.append(new_run)

    paragraph._p.append(hyperlink)
    return hyperlink


def _write_element(element, doc, parent_para=None, base_dir=None):
    """递归写入单个 HTML 元素到 docx"""
    from bs4 import NavigableString, Tag

    if isinstance(element, NavigableString):
        text = str(element)
        if text.strip() and parent_para is not None:
            parent_para.add_run(text)
        return

    if not isinstance(element, Tag):
        return

    tag = element.name.lower()

    # 标题
    if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        level = int(tag[1])
        text = element.get_text().strip()
        if text:
            doc.add_heading(text, level=level)
        return

    # 段落
    if tag == "p":
        text = element.get_text().strip()
        # 优化规划 §2.6：只含图片的段落 get_text() 为空，原先会整体跳过 →
        # 图片被静默丢弃。这里把"含图片"也算作有内容。
        has_image = element.find("img") is not None
        if text or has_image:
            p = doc.add_paragraph()
            _write_inline(element, p, base_dir)
        return

    # 列表
    if tag in ("ul", "ol"):
        for li in element.find_all("li", recursive=False):
            text = li.get_text().strip()
            style = "List Number" if tag == "ol" else "List Bullet"
            try:
                p = doc.add_paragraph(style=style)
                p.add_run(text)
            except Exception:
                p = doc.add_paragraph(f"• {text}" if tag == "ul"
                                     else f"1. {text}")
        return

    # 表格
    if tag == "table":
        _write_table(element, doc)
        return

    # 代码块
    if tag == "pre":
        code_text = element.get_text()
        p = doc.add_paragraph()
        run = p.add_run(code_text)
        run.font.name = "Consolas"
        run.font.size = Pt(10)
        return

    # 引用
    if tag == "blockquote":
        text = element.get_text().strip()
        p = doc.add_paragraph()
        run = p.add_run(text)
        run.italic = True
        run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
        return

    # 分割线
    if tag == "hr":
        doc.add_paragraph("─" * 40)
        return

    # 容器类标签：递归
    if tag in ("div", "section", "article", "body", "html"):
        for child in element.children:
            _write_element(child, doc, base_dir=base_dir)
        return

    # 独立的图片（不在段落内时）
    if tag == "img":
        p = doc.add_paragraph()
        _write_inline(element, p, base_dir)
        return

    # 其他：把文本抽出来
    text = element.get_text().strip()
    if text:
        doc.add_paragraph(text)


def _write_inline(element, paragraph, base_dir=None):
    """将元素的内联内容写入段落（保留加粗、斜体、图片与超链接）"""
    from bs4 import NavigableString, Tag

    for child in element.children:
        if isinstance(child, NavigableString):
            paragraph.add_run(str(child))
        elif isinstance(child, Tag):
            tag = child.name.lower()

            # 图片：必须放在"文本为空则跳过"之前判断（<img> 的文本恒为空）
            if tag == "img":
                _write_inline_image(child, paragraph, base_dir)
                continue

            text = child.get_text()
            if not text:
                continue

            # 超链接：优先生成可点击链接（原实现只染色，href 丢失）
            if tag == "a":
                href = (child.get("href") or "").strip()
                if href:
                    try:
                        _add_hyperlink(paragraph, href, text)
                        continue
                    except Exception as e:
                        logging.warning(f"插入超链接失败，降级为纯文本: {e}")
                run = paragraph.add_run(text)
                run.font.color.rgb = RGBColor(0x15, 0x65, 0xC0)
                run.font.underline = True
                continue

            run = paragraph.add_run(text)
            if tag in ("strong", "b"):
                run.bold = True
            elif tag in ("em", "i"):
                run.italic = True
            elif tag == "code":
                run.font.name = "Consolas"
                run.font.color.rgb = RGBColor(0xD3, 0x2F, 0x2F)


def _write_inline_image(img_tag, paragraph, base_dir=None):
    """
    把 `<img>` 嵌入段落（优化规划 §2.6）。

    找不到文件或格式不受支持时插入**可见占位文字**，而不是静默丢弃——
    用户需要知道"这里本来有张图，但没被导出"。
    """
    src = (img_tag.get("src") or "").strip()
    alt = (img_tag.get("alt") or "").strip()
    path = _resolve_image_path(src, base_dir)

    if path is None:
        placeholder = f"[图片未导出: {src or '无地址'}]"
        if alt:
            placeholder = f"[图片未导出: {alt}（{src or '无地址'}）]"
        logging.warning(f"MD→DOCX: 无法定位图片，插入占位文字: {src}")
        run = paragraph.add_run(placeholder)
        run.font.color.rgb = RGBColor(0xB7, 0x1C, 0x1C)
        return

    try:
        width = None
        try:
            from PIL import Image
            with Image.open(path) as im:
                # 超过正文宽度（A4 去掉页边距约 16cm）时按比例缩到 15cm
                if im.width > 600:
                    width = Cm(15)
        except Exception:
            width = None

        run = paragraph.add_run()
        if width is not None:
            run.add_picture(str(path), width=width)
        else:
            run.add_picture(str(path))
    except Exception as e:
        logging.warning(f"嵌入图片失败 {path}: {e}")
        run = paragraph.add_run(f"[图片未导出: {alt or src}]")
        run.font.color.rgb = RGBColor(0xB7, 0x1C, 0x1C)


def _write_table(table_tag, doc):
    """将 HTML 表格写入 docx"""

    rows = table_tag.find_all("tr")
    if not rows:
        return

    # 计算列数
    n_cols = 0
    for tr in rows:
        cells = tr.find_all(["td", "th"])
        n_cols = max(n_cols, len(cells))
    if n_cols == 0:
        return

    doc_table = doc.add_table(rows=len(rows), cols=n_cols)
    doc_table.style = "Table Grid"

    for r, tr in enumerate(rows):
        cells = tr.find_all(["td", "th"])
        for c, cell in enumerate(cells):
            if c >= n_cols:
                break
            text = cell.get_text().strip()
            docx_cell = doc_table.cell(r, c)
            docx_cell.text = text
            # 表头加粗
            if cell.name == "th" or r == 0:
                for para in docx_cell.paragraphs:
                    for run in para.runs:
                        run.bold = True


# 优化规划 §3.3：原 `_write_plain_to_docx()` 与 `_write_inline_md()`（约 55 行）
# 已删除。它们是"缺少 markdown / beautifulsoup4 时的逐行降级转换"，但那两个包在
# requirements.txt 里是**必需**依赖，因此该分支不可达、也从未有测试覆盖；
# 留着只会让人以为 DOCX 导出有第二套实现。现在缺依赖时 `export_to_docx()`
# 明确失败并记录日志，不再悄悄产出一份低保真文档。



# ==================== 导出 PDF ====================
def export_to_pdf(content, output_path):
    """
    Markdown 导出为 PDF
    优先使用 WeasyPrint，失败时返回 False
    :param content: Markdown 文本
    :param output_path: 输出路径
    :return: 是否成功
    """
    try:
        from weasyprint import HTML
    except ImportError:
        logging.warning("WeasyPrint 未安装，无法导出 PDF")
        return False

    try:
        html = _md_to_html_full(content, "BeeOffice PDF")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        HTML(string=html).write_pdf(output_path)
        return True
    except Exception as e:
        logging.error(f"PDF 导出失败: {e}")
        return False


# ==================== DOCX → Markdown ====================
def import_from_docx(docx_path):
    """
    从 DOCX 文件导入为 Markdown

    v5.0.2 图片修复：
      - 从段落的 <a:blip>（DrawingML）和 <v:imagedata>（VML）提取内嵌图片
      - 图片导出到 <docx同名>_media/ 目录
      - Markdown 中使用相对路径引用：![](<docx同名>_media/image_001.png)

    v5.0.2 增强：
      - 同时提取表格单元格内的图片
      - 同时提取页眉 / 页脚内的图片

    :param docx_path: DOCX 文件路径
    :return: Markdown 文本
    """
    if not HAS_DOCX:
        raise RuntimeError("python-docx 未安装，无法导入 DOCX")

    try:
        doc = Document(docx_path)
        md_lines = []

        # ---------- v5.0.2：准备图片导出目录 ----------
        # P0-A：同级目录不可写时回退到用户缓存目录，**不再静默丢图**
        docx_p = Path(docx_path).resolve()
        media_dir, link_prefix = _resolve_media_dir(docx_p)
        img_counter = [0]   # 用 list 便于内部函数修改

        # R7：文档同级与缓存目录**都不可写**时，`_resolve_media_dir` 返回
        # `(None, "")` —— 此时**一次性放弃提取图片**，并给出一条明确提示，
        # 而不是让每张图各失败一次（23 张图 = 23 次异常、日志一片 error）。
        images_disabled = media_dir is None
        if images_disabled:
            logging.warning(
                "[import_from_docx] 无可用图片目录：本次只导入正文，不提取图片"
            )

        logging.info(
            f"[import_from_docx] 源文件: {docx_p}\n"
            f"[import_from_docx] 媒体目录: {media_dir}"
        )

        # ---------- 1. 顶层段落 ----------
        logging.debug("[import_from_docx] 开始处理顶层段落")

        # 保真度阶段 A：**段落之间必须留空行**。
        # Markdown 会把连续的非空行渲染成**同一个段落**，因此原先"一行一段"
        # 的输出会让相邻段落粘在一起 —— 实测：图片段与超链接段被并进上一段，
        # 顶层段落 6 → 4（`paragraphs` 也因此从 14 变 13）。
        # 列表项之间例外：空行会把一个列表拆成多个。
        prev_is_list = False

        def _emit(line, is_list=False):
            nonlocal prev_is_list
            if md_lines and md_lines[-1] != "" \
                    and not (is_list and prev_is_list):
                md_lines.append("")
            md_lines.append(line)
            prev_is_list = is_list

        for para in doc.paragraphs:
            text = _paragraph_text(para).strip()

            # 提取段落内嵌图片（R7：无可用目录时整体跳过，不做无用的失败写入）
            inline_imgs = [] if images_disabled else _extract_para_images(
                para, doc, media_dir, img_counter, docx_p, link_prefix
            )

            if not text:
                # 段落无文字
                if inline_imgs:
                    for img_md in inline_imgs:
                        _emit(img_md)
                else:
                    md_lines.append("")
                    prev_is_list = False
                continue

            style_name = para.style.name if para.style else ""

            # 标题
            if style_name.startswith("Heading"):
                try:
                    level = int(style_name.split()[-1])
                except (ValueError, IndexError):
                    level = 1
                _emit("#" * level + " " + _escape_markdown_text(text))
                for img_md in inline_imgs:
                    _emit(img_md)
                continue

            # 列表
            if "List" in style_name:
                if "Number" in style_name:
                    _emit("1. " + _escape_markdown_text(text), is_list=True)
                else:
                    _emit("- " + _escape_markdown_text(text), is_list=True)
                for img_md in inline_imgs:
                    _emit(img_md)
                continue

            # 普通段落（处理粗体、斜体、超链接）
            _emit(_para_to_md(para))
            for img_md in inline_imgs:
                _emit(img_md)

        # ---------- 2. v5.0.2 增强：表格单元格图片 ----------
        logging.debug("[import_from_docx] 开始处理表格")
        for t_idx, table in enumerate(doc.tables):
            md_lines.append("")
            md_lines.append(_docx_table_to_md(table))
            md_lines.append("")

            # 提取表格单元格内的图片（R7：同样整体跳过）
            for para in _iter_table_paragraphs(table):
                cell_imgs = [] if images_disabled else _extract_para_images(
                    para, doc, media_dir, img_counter, docx_p, link_prefix
                )
                for img_md in cell_imgs:
                    md_lines.append(img_md)

        # ---------- 3. v5.0.2 增强：页眉/页脚图片 ----------
        logging.debug("[import_from_docx] 开始处理页眉页脚")
        for s_idx, section in enumerate(doc.sections):
            try:
                for para in _iter_header_footer_paragraphs(section):
                    hf_imgs = [] if images_disabled else _extract_para_images(
                        para, doc, media_dir, img_counter, docx_p, link_prefix
                    )
                    for img_md in hf_imgs:
                        md_lines.append(img_md)
            except Exception as e:
                logging.debug(f"处理 section {s_idx} 页眉页脚失败: {e}")

        # ---------- 完成汇总 ----------
        logging.info(
            f"[import_from_docx] 提取完成，共提取 {img_counter[0]} 张图片"
        )

        # R7：无可用图片目录时，给用户**一条明确的说明**（而不是 23 行失败日志）
        if images_disabled:
            md_lines.append("")
            md_lines.append(
                "> ⚠️ **本文档的图片未能提取**：文档所在位置与用户缓存目录都不可写。"
                "正文已正常导入；如需图片，请把文档复制到可写目录（如桌面）后重新打开。"
            )

        return "\n".join(md_lines)
    except Exception as e:
        logging.error(f"DOCX 导入失败: {e}")
        raise


def _extract_para_images(para, doc, media_dir, img_counter, docx_p,
                         link_prefix=None):
    """
    v5.0.2 新增：从段落中提取内嵌图片。

    DOCX 中图片有两处存放位置：
      1. DrawingML（现代 Word）：<w:drawing>/<a:blip r:embed="rIdX"/>
      2. VML（旧版 Word）：<w:pict>/<v:imagedata r:id="rIdX"/>

    两种都处理，最大化兼容性。

    v5.0.2 增强：加入详细调试日志。

    :param para: python-docx 的 Paragraph 对象
    :param doc: python-docx 的 Document 对象（用于查找 relationships）
    :param media_dir: 图片保存目录（Path）
    :param img_counter: 计数器（单元素 list，用于生成递增序号）
    :param docx_p: DOCX 源文件路径（Path）
    :return: Markdown 图片语法列表，如 ["![](demo_media/image_001.png)"]
    """
    imgs_md = []

    try:
        # 收集所有图片引用的 rId
        r_ids = []

        # 1. DrawingML 图片（现代 Word）
        try:
            blips = para._element.findall(
                f'.//{{{_NS_DRAWINGML}}}blip'
            )
            for blip in blips:
                r_embed = blip.get(f'{{{_NS_RELATIONSHIPS}}}embed')
                if r_embed:
                    r_ids.append(("drawingml", r_embed))
                    logging.debug(
                        f"[_extract_para_images] 发现 DrawingML 图片: "
                        f"rId={r_embed}"
                    )
        except Exception as e:
            logging.debug(f"查找 DrawingML 图片失败: {e}")

        # 2. VML 图片（旧版 Word）
        try:
            vml_imgs = para._element.findall(
                f'.//{{{_NS_VML}}}imagedata'
            )
            for vml in vml_imgs:
                r_id = vml.get(f'{{{_NS_RELATIONSHIPS}}}id')
                if r_id:
                    r_ids.append(("vml", r_id))
                    logging.debug(
                        f"[_extract_para_images] 发现 VML 图片: "
                        f"rId={r_id}"
                    )
        except Exception as e:
            logging.debug(f"查找 VML 图片失败: {e}")

        # 3. 逐个提取图片二进制
        for source_type, r_id in r_ids:
            try:
                rel = doc.part.rels.get(r_id)
                if not rel or not rel.target_part:
                    logging.warning(
                        f"[_extract_para_images] 未找到关系: "
                        f"{source_type} rId={r_id}"
                    )
                    continue

                img_part = rel.target_part
                img_bytes = img_part.blob

                # 从 partname 推断扩展名：/word/media/image1.png → "png"
                part_name = str(img_part.partname)
                img_ext = part_name.rsplit('.', 1)[-1].lower()
                if img_ext not in _SUPPORTED_IMAGE_EXTS:
                    logging.debug(
                        f"[_extract_para_images] 未知扩展名 "
                        f"'{img_ext}'，回退为 png"
                    )
                    img_ext = 'png'

                img_counter[0] += 1
                img_name = f"image_{img_counter[0]:03d}.{img_ext}"

                # 保存到 media 目录
                media_dir.mkdir(parents=True, exist_ok=True)
                img_path = media_dir / img_name
                with open(img_path, "wb") as f:
                    f.write(img_bytes)

                logging.info(
                    f"[_extract_para_images] 已保存图片 "
                    f"{img_name} ({len(img_bytes)} bytes) → "
                    f"{img_path}"
                )

                # 相对于 docx 文件的相对路径；回退到缓存目录时是绝对路径
                rel_path = f"{link_prefix or (docx_p.stem + '_media/')}{img_name}"
                imgs_md.append(f"![]({rel_path})")
            except Exception as e:
                logging.warning(
                    f"[_extract_para_images] 提取单个图片失败 "
                    f"{source_type} rId={r_id}: {e}"
                )
    except Exception as e:
        logging.warning(f"提取段落图片失败: {e}")

    return imgs_md


def _media_cache_root() -> Path:
    """
    图片**回退目录**的根：用户缓存区（可写、不进文档目录）。

    只在"文档所在位置不可写"时才用到（见 `_resolve_media_dir`）。
    """
    import os
    import tempfile

    candidates = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "BeeOffice" / "media")
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        candidates.append(Path(xdg) / "beeoffice" / "media")
    try:
        candidates.append(Path.home() / ".cache" / "beeoffice" / "media")
    except Exception:  # noqa: BLE001
        pass
    candidates.append(Path(tempfile.gettempdir()) / "beeoffice_media")

    for path in candidates:
        try:
            path.mkdir(parents=True, exist_ok=True)
            # 真写一次才算数：mkdir 成功但不可写的情况是存在的
            probe = path / ".write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return path
        except Exception:  # noqa: BLE001
            continue
    # ⚠️ R7：这里**不能**再"兜底返回 tempfile.gettempdir()" ——
    # 它本身也可能不可写（沙箱/受限账户/磁盘满），于是调用方会拿到一个
    # **已知不可写**的目录，然后**每张图各失败一次**（23 张图 = 23 次异常），
    # 日志里一片 error 却看不出真正原因。
    # 返回 None 让调用方**一次性判定并快速失败**。
    logging.error(
        "[import_from_docx] 找不到可写的图片缓存目录（候选：%s）",
        ", ".join(str(c) for c in candidates),
    )
    return None


def _resolve_media_dir(docx_p: Path):
    """
    决定图片落地目录，返回 `(目录, Markdown 链接前缀)`。

    **为什么要回退**（真实缺陷）
    ---------------------------
    原先无条件写到文档同级的 `<名>_media/`。文档放在**只读位置**时
    （光盘、网络共享、`Program Files`、只读归档），`mkdir`/写入被拒，
    图片被**静默降级为占位文字** —— 用户看到的是一份缺图的文档，
    而唯一的线索只是日志里一行 warning。

    策略：
      1. 优先文档同级 `<名>_media/`（保持既有行为与**相对链接**不变）；
      2. 该位置不可写 → 回退到用户缓存目录，并把链接写成**绝对路径**
         （`base_dir` 解析不了别的目录，绝对路径最稳）。

    :return: (media_dir, link_prefix)；`link_prefix` 形如 `"名字_media/"` 或
        `"C:/…/media/名字-1a2b3c4d/"`
    """
    adjacent = docx_p.parent / (docx_p.stem + "_media")
    try:
        adjacent.mkdir(parents=True, exist_ok=True)
        probe = adjacent / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return adjacent, f"{docx_p.stem}_media/"
    except Exception as e:  # noqa: BLE001
        logging.warning(
            f"[import_from_docx] 文档同级目录不可写（{type(e).__name__}: {e}），"
            f"图片改存用户缓存目录，链接将写成绝对路径"
        )

    import hashlib

    digest = hashlib.sha1(
        str(docx_p).encode("utf-8", "ignore")
    ).hexdigest()[:8]
    root = _media_cache_root()
    if root is None:
        # 文档同级不可写、缓存区也不可写：**一次性放弃提取图片**
        # （而不是每张图各失败一次）。调用方会用占位提示替代图片。
        logging.error(
            "[import_from_docx] 文档同级与用户缓存目录**都不可写**，"
            "本次不提取图片（正文仍会正常导入）"
        )
        return None, ""
    fallback = root / f"{docx_p.stem}-{digest}"
    try:
        fallback.mkdir(parents=True, exist_ok=True)
        probe = fallback / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except Exception as e:  # noqa: BLE001
        logging.error(f"[import_from_docx] 回退目录也不可写: {e}")
        return None, ""
    # 绝对路径：Windows 反斜杠换成正斜杠，避免 Markdown/URL 解析出岔子
    return fallback, fallback.as_posix().rstrip("/") + "/"


def _iter_table_paragraphs(table):
    """
    v5.0.2 新增：遍历表格中所有单元格的所有段落。

    表格可能是嵌套的（单元格里还有表格），
    所以递归处理单元格内嵌的表格。

    :param table: python-docx 的 Table 对象
    :yield: 每个 Paragraph 对象
    """
    try:
        for row in table.rows:
            for cell in row.cells:
                # 单元格内的段落
                for para in cell.paragraphs:
                    yield para
                # 单元格内嵌的表格（递归）
                for nested_table in cell.tables:
                    yield from _iter_table_paragraphs(nested_table)
    except Exception as e:
        logging.debug(f"遍历表格段落失败: {e}")


def _iter_header_footer_paragraphs(section):
    """
    v5.0.2 新增：遍历 section 的页眉和页脚中的所有段落。

    :param section: python-docx 的 Section 对象
    :yield: 每个 Paragraph 对象
    """
    # 页眉
    try:
        header = section.header
        if header is not None:
            for para in header.paragraphs:
                yield para
            for table in header.tables:
                yield from _iter_table_paragraphs(table)
    except Exception as e:
        logging.debug(f"处理页眉失败: {e}")

    # 页脚
    try:
        footer = section.footer
        if footer is not None:
            for para in footer.paragraphs:
                yield para
            for table in footer.tables:
                yield from _iter_table_paragraphs(table)
    except Exception as e:
        logging.debug(f"处理页脚失败: {e}")

    # 首页页眉 / 页脚（若与默认不同）
    try:
        first_header = section.first_page_header
        if first_header is not None:
            for para in first_header.paragraphs:
                yield para
    except Exception:
        pass

    try:
        first_footer = section.first_page_footer
        if first_footer is not None:
            for para in first_footer.paragraphs:
                yield para
    except Exception:
        pass


def _url_from_field_instruction(instr):
    """
    从**域指令**里取出 HYPERLINK 的目标 URL（不是超链接域则返回 ""）。

    实测真实文档里超链接有两种存法：`w:hyperlink` 元素，以及**域**
    （`' HYPERLINK "https://blog.csdn.net/…"'`）。`yum源更新.docx` 的 6 个
    "域" 全是后者 —— 文字还在、链接目标丢失。
    """
    if not instr or "HYPERLINK" not in instr.upper():
        return ""
    match = re.search(r'HYPERLINK\s+"([^"]+)"', instr, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"HYPERLINK\s+(\S+)", instr, re.IGNORECASE)
    return match.group(1) if match else ""


def _iter_para_children(para):
    """
    按**文档顺序**遍历段落里的文字片段，返回 `(run 元素, 链接 URL 或 "")`。

    为什么不能直接用 `para.runs` / `para.text`：python-docx 只看 `w:p` 的
    **直接子** `w:r`，凡是嵌在容器里的文字都会被漏掉。真实文档实测到三类：

    1. `w:hyperlink/w:r` —— 超链接文字（已修）
    2. **复杂域**（`w:fldChar` + `w:instrText` + 缓存结果）—— 页脚的页码
       `12 / 12` 就在这里：`w:t` 明明有 `'12'`、`' / '`、`'12'`，
       但 `paragraph.text` 返回 `''`，于是页脚被当成空的、整个部件都不写。
    3. `HYPERLINK` **域** —— 实测 `yum源更新.docx` 有 6 个，丢失后链接变纯文字。

    因此这里用一个状态机遍历全部子元素：
      - `w:r`：若是域控制符（begin/separate/end）或指令文本则不产出；
        否则产出该 run（若身处域的**结果区**，带上域里解析出的 URL）
      - `w:hyperlink` / `w:fldSimple`：取其 URL，产出内部所有嵌套 run
      - 其它容器（`w:smartTag`/`w:ins`/`w:sdt`…）：递归产出内部 run
    """
    from docx.oxml.ns import qn

    in_field = False
    result_started = False
    field_url = ""

    for child in para._p:
        tag = child.tag

        if tag == qn("w:r"):
            fld_char = child.find(qn("w:fldChar"))
            if fld_char is not None:
                ftype = fld_char.get(qn("w:fldCharType"))
                if ftype == "begin":
                    in_field, result_started, field_url = True, False, ""
                elif ftype == "separate":
                    result_started = True
                elif ftype == "end":
                    in_field, result_started, field_url = False, False, ""
                continue

            instr = child.find(qn("w:instrText"))
            if instr is not None:
                url = _url_from_field_instruction(instr.text or "")
                if url:
                    field_url = url
                continue

            yield child, (field_url if (in_field and result_started) else "")

        elif tag == qn("w:hyperlink"):
            url = _hyperlink_target(child, para)
            for run in child.iter(qn("w:r")):
                yield run, url

        elif tag == qn("w:fldSimple"):
            url = _url_from_field_instruction(
                child.get(qn("w:instr")) or ""
            )
            for run in child.iter(qn("w:r")):
                yield run, url

        else:
            # 其它容器：递归取出里面的 run（不带链接语义）
            for run in child.iter(qn("w:r")):
                yield run, ""


def _paragraph_text(para):
    """
    段落的**可见文字**（含嵌套 run 与域的缓存结果）。

    用它替代 `para.text` —— 后者会漏掉嵌在 `w:hyperlink`、复杂域、
    `w:smartTag` 等容器里的文字（实测页脚页码就是这样被漏掉的）。
    """
    from docx.text.run import Run

    return "".join(
        Run(element, para).text for element, _ in _iter_para_children(para)
    )


def _hyperlink_target(hyperlink, para):
    """
    取出 `w:hyperlink` 的目标。

    - 外部链接：`r:id` → 解析关系 → URL
    - 内部书签：`w:anchor` → `#书签名`
    """
    from docx.oxml.ns import qn

    r_id = hyperlink.get(qn("r:id"))
    if r_id:
        try:
            return para.part.rels[r_id].target_ref or ""
        except Exception:
            return ""
    anchor = hyperlink.get(qn("w:anchor"))
    if anchor:
        return f"#{anchor}"
    return ""


def _escape_inline_text(text):
    """
    **行内**转义：让一段纯文本在 Markdown 里语义不变。

    ⚠️ 只做行内的事，**绝不能**做行首缩进/块级标记的剥离 —— 本函数是**按 run**
    调用的，而一个 run 完全可能只包含空格（实测真实文档里 `'原', '  ', '因：'`
    就是三个 run）。早期版本在这里做了 `lstrip(" \\t")`，把那个纯空格 run 变成
    空串，导致"原  因"变成"原因"。行级处理请用 `_escape_block_markers()`。

    为什么 `<` `>` `&` 用 HTML 实体而不是反斜杠：Python-Markdown 的可转义集合
    只含标点（`* _ { } [ ] ( ) # + - . !` 等），**不含 `<` 与 `&`** ——
    实测 `\\<UP,...>` 里的 `\\` 原样留下、尖括号内容照样被当标签吃掉。
    """
    if not text:
        return text

    # 已有的反斜杠先转义，之后加的反斜杠才不会被二次转义
    text = text.replace("\\", "\\\\")
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    # 行内强调/链接标记：`a*b*c` 会被渲染成强调（实测变成 `abc`）
    for ch in ("*", "_", "`", "[", "]"):
        text = text.replace(ch, "\\" + ch)
    return text


def _escape_block_markers(markdown_text):
    """
    **行级**处理：行首缩进与块级标记。

    必须在**整段（或整行）拼好之后**调用，不能按 run 调用：
    否则会把"只含空格的 run"整段抹掉（真实文档实测踩过）。

    处理内容：
      - 行首缩进（tab 或 ≥4 空格）→ 会触发代码块，去掉
      - 行首 `#` / `-` / `+` / `数字.` → 会被当成标题/列表
      - 整行由 `=` 或 `-` 组成 → 会成为 setext 标题的下划线
    """
    if not markdown_text:
        return markdown_text

    out_lines = []
    for line in markdown_text.split("\n"):
        # 行首缩进（tab 或 ≥4 空格）会触发代码块。
        # **不要直接 strip 掉** —— 对技术文档，代码行的缩进是有意义的。
        # 用实体表示：`&#32;`/`&#9;` 在块级解析时不是空白（不会成为代码块），
        # 渲染时又变回空格/制表符。实测真实教程文档里 shell/YAML 缩进全靠它保住。
        stripped = line.lstrip(" \t")
        indent = line[: len(line) - len(stripped)]
        if indent:
            indent = "".join(
                "&#9;" if ch == "\t" else "&#32;" for ch in indent
            )
        line = indent + stripped

        line = re.sub(r"^(#{1,6})", r"\\\1", line)
        line = re.sub(r"^([-+])(?=\s|$)", r"\\\1", line)
        line = re.sub(r"^(\d+)([.)])(?=\s)", r"\1\\\2", line)
        if re.fullmatch(r"[=\-]+", line):
            line = "\\" + line
        out_lines.append(line)
    return "\n".join(out_lines)


def _escape_markdown_text(text):
    """行内 + 行级一起做（用于"整段文字已经拼好"的场合）。"""
    return _escape_block_markers(_escape_inline_text(text))


def _wrap_emphasis(text, marker):
    """
    给文字套上强调标记，并**把首尾空白留在标记外面**。

    为什么必须这样（渲染时才发现的缺陷）
    ------------------------------------
    Markdown 要求强调的收尾定界符**不能紧跟在空白之后**（`**x **` 不解析）。
    实测真实文档里有 `bold=True` 且**结尾带空格**的 run：

        run.text = 'Linux-mount: 在 /dev/sr0 上找不到媒体 '   (bold=True)

    直接套成 `**…媒体 **` 后，星号**原样显示**在文档里。

    这个问题**结构性指标完全看不到** —— `**` 本身也是字符，字符数一点没变，
    只有把导出的 DOCX 真的渲染出来才看得见。
    """
    if not text:
        return text
    blank = " \t\u3000"
    stripped = text.strip(blank)
    if not stripped:
        return text
    lead = text[: len(text) - len(text.lstrip(blank))]
    trail = text[len(text.rstrip(blank)):]
    return f"{lead}{marker}{stripped}{marker}{trail}"


def _para_to_md(para):
    """
    将段落转为 Markdown（保留粗体、斜体，**并把超链接写成 `[文字](url)`**）。

    写回 `[文字](url)` 之后，导出路径的 `_add_hyperlink()` 会把它还原成
    真正的 `w:hyperlink`，于是超链接可以完整往返。
    """
    from docx.text.run import Run

    parts = []
    for element, url in _iter_para_children(para):
        run = Run(element, para)
        text = run.text
        if not text:
            continue
        # 只做**行内**转义（按 run 调用是安全的）；行级处理放到整段拼好之后
        text = _escape_inline_text(text)
        if run.bold:
            text = _wrap_emphasis(text, "**")
        if run.italic:
            text = _wrap_emphasis(text, "*")
        if url:
            text = f"[{text}]({url})"
        parts.append(text)
    return _escape_block_markers("".join(parts))


def _docx_table_to_md(table):
    """将 docx 表格转为 Markdown 表格"""
    lines = []
    for ri, row in enumerate(table.rows):
        # 先按纯文本转义（含 < > & 与行首标记），再处理表格自己的 `|`
        cells = [
            _escape_markdown_text(cell.text.strip()).replace("|", "\\|")
            for cell in row.cells
        ]
        lines.append("| " + " | ".join(cells) + " |")
        if ri == 0:
            lines.append("|" + "|".join(["---"] * len(cells)) + "|")
    return "\n".join(lines)


# ==================== 批量转换 ====================
def batch_convert_docx_to_md(input_dir, output_dir):
    """
    批量将 DOCX 转为 Markdown
    :param input_dir: 输入目录
    :param output_dir: 输出目录
    :return: [{status, file}, ...]
    """
    results = []
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    if not input_path.exists():
        return results

    output_path.mkdir(parents=True, exist_ok=True)

    for docx_file in input_path.glob("*.docx"):
        try:
            md_text = import_from_docx(str(docx_file))
            out_file = output_path / (docx_file.stem + ".md")
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(md_text)
            results.append({
                "status": "✅",
                "file": docx_file.name,
                "output": str(out_file),
            })
        except Exception as e:
            results.append({
                "status": "❌",
                "file": docx_file.name,
                "error": str(e),
            })

    return results


def batch_convert_md_to_docx(input_dir, output_dir):
    """
    批量将 Markdown 转为 DOCX
    :param input_dir: 输入目录
    :param output_dir: 输出目录
    :return: [{status, file}, ...]
    """
    results = []
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    if not input_path.exists():
        return results

    output_path.mkdir(parents=True, exist_ok=True)

    for md_file in input_path.glob("*.md"):
        try:
            with open(md_file, "r", encoding="utf-8") as f:
                content = f.read()
            out_file = output_path / (md_file.stem + ".docx")
            if export_to_docx(content, str(out_file)):
                results.append({
                    "status": "✅",
                    "file": md_file.name,
                    "output": str(out_file),
                })
            else:
                results.append({
                    "status": "❌",
                    "file": md_file.name,
                    "error": "导出失败",
                })
        except Exception as e:
            results.append({
                "status": "❌",
                "file": md_file.name,
                "error": str(e),
            })

    return results


# ==================== 目录生成 ====================
def generate_toc(md_text):
    """
    根据 Markdown 标题生成目录
    :param md_text: Markdown 文本
    :return: 目录 Markdown 文本
    """
    lines = md_text.split("\n")
    toc_items = []

    for line in lines:
        m = re.match(r"^(#{1,6})\s+(.+)", line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            # 生成锚点：中英文都保留，空格转 -
            anchor = re.sub(r'[^\w\u4e00-\u9fff\- ]', '', title)
            anchor = anchor.strip().replace(' ', '-').lower()
            toc_items.append((level, title, anchor))

    if not toc_items:
        return "（文档中没有标题，无法生成目录）"

    # 生成列表
    out = ["## 目录", ""]
    for level, title, anchor in toc_items:
        indent = "  " * (level - 1)
        out.append(f"{indent}- [{title}](#{anchor})")

    return "\n".join(out)


# ==================== 文档对比 ====================
def compare_documents(original, modified):
    """
    对比两份文档的差异
    :param original: 原始文本
    :param modified: 修改后文本
    :return: {additions, deletions, total_changes, diff}
    """
    orig_lines = original.split("\n")
    mod_lines = modified.split("\n")

    # 使用 difflib 生成 unified diff
    diff_lines = list(difflib.unified_diff(
        orig_lines, mod_lines,
        lineterm="",
        fromfile="原始",
        tofile="修改后"
    ))
    diff_text = "\n".join(diff_lines)

    additions = 0
    deletions = 0

    for line in diff_lines:
        if line.startswith("+") and not line.startswith("+++"):
            additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1

    total_changes = additions + deletions

    return {
        "additions": additions,
        "deletions": deletions,
        "total_changes": total_changes,
        "diff": diff_text or "（无差异）",
    }


# ==================== 幻灯片导出 GIF ====================
def export_slides_to_gif(slides_html, output_path, css, duration_ms=2000):
    """
    将幻灯片导出为 GIF 动图
    :param slides_html: HTML 片段列表（每张幻灯片一个）
    :param output_path: 输出路径
    :param css: 主题 CSS（当前版本未使用，仅供未来扩展）
    :param duration_ms: 每帧显示时长（毫秒）
    :return: 是否成功
    """
    if not HAS_PIL:
        logging.error("Pillow 未安装，无法导出 GIF")
        return False

    try:
        frames = []
        for slide_html in slides_html:
            img = _render_slide_to_image(slide_html)
            if img is not None:
                frames.append(img)

        if not frames:
            logging.warning("没有可渲染的幻灯片")
            return False

        # 保存为 GIF
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        frames[0].save(
            output_path,
            save_all=True,
            append_images=frames[1:],
            duration=duration_ms,
            loop=0
        )
        return True
    except Exception as e:
        logging.error(f"GIF 导出失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def _render_slide_to_image(html_content, width=1024, height=768):
    """
    将 HTML 片段渲染为 PIL Image
    当前实现：提取文本，绘制到白色背景
    """
    # 提取纯文本
    text = html_content
    if HAS_BS4:
        soup = BeautifulSoup(html_content, "html.parser")
        text = soup.get_text("\n").strip()
    else:
        # 简单去除 HTML 标签
        text = re.sub(r'<[^>]+>', '', html_content)
        text = re.sub(r'\n+', '\n', text).strip()

    if not text:
        text = "（空白幻灯片）"

    # 创建图片
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    # 尝试加载中文字体
    font = None
    font_paths = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, 28)
                break
            except Exception:
                continue

    if font is None:
        font = ImageFont.load_default()

    # 文本换行
    wrapped_lines = _wrap_text(text, font, draw, width - 120)

    # 垂直居中
    line_height = 40
    total_height = len(wrapped_lines) * line_height
    y = max(60, (height - total_height) // 2)

    for line in wrapped_lines:
        # 标题行加大字号
        if line.startswith("# "):
            line = line[2:]
            title_font = font
            try:
                for fp in font_paths:
                    if os.path.exists(fp):
                        title_font = ImageFont.truetype(fp, 42)
                        break
            except Exception:
                pass
            draw.text((60, y), line, fill="black", font=title_font)
            y += 56
        else:
            draw.text((60, y), line, fill="#333333", font=font)
            y += line_height

        if y > height - 60:
            break

    return img


def _wrap_text(text, font, draw, max_width):
    """将文本按最大宽度换行"""
    lines = []
    for raw_line in text.split("\n"):
        raw_line = raw_line.strip()
        if not raw_line:
            lines.append("")
            continue

        # 逐字符累加，测量宽度
        current = ""
        for char in raw_line:
            test = current + char
            try:
                bbox = draw.textbbox((0, 0), test, font=font)
                w = bbox[2] - bbox[0]
            except Exception:
                w = len(test) * 20

            if w <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = char
        if current:
            lines.append(current)

    return lines


# ==================== 兼容导出（供 app.py 直接调用） ====================
def export_html_to_docx(html_content, output_path, base_dir=None):
    """HTML 内容 → DOCX（供特殊场景调用）

    :param base_dir: 解析相对图片路径的基准目录（优化规划 §2.6）
    """
    if not HAS_DOCX or not HAS_BS4:
        return False
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        doc = Document()
        _write_html_to_docx(soup, doc, base_dir=base_dir)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with atomic_replace(output_path) as tmp_path:
            doc.save(str(tmp_path))
        return True
    except Exception as e:
        logging.error(f"HTML→DOCX 失败: {e}")
        return False