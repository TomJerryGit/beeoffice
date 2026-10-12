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
import io
import logging
import difflib
from pathlib import Path

from beeoffice.plugins.image_utils import (
    normalize_image_ref,
    resolve_image_path,
)

# ==================== 可选依赖导入 ====================
try:
    import markdown
    HAS_MARKDOWN = True
except ImportError:
    HAS_MARKDOWN = False

try:
    from docx import Document
    from docx.shared import Pt, RGBColor, Inches, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
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


# ==================== 导出 DOCX ====================
def export_to_docx(content, output_path, page_settings=None, base_dir=None):
    """
    Markdown 导出为 DOCX 文件

    :param content: Markdown 文本
    :param output_path: 输出路径
    :param page_settings: 页面设置（单位 mm，见 apply_page_settings）。
        为 None 时沿用 python-docx 默认模板（保持向后兼容）。
    :param base_dir: Markdown 所在目录，用于解析**相对图片路径**
        （优化规划 §2.6）。为 None 时相对路径按当前工作目录解析。
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
        apply_page_settings(doc, page_settings)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        doc.save(output_path)
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
    from bs4 import Tag

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
        docx_p = Path(docx_path).resolve()
        media_dir = docx_p.parent / (docx_p.stem + "_media")
        img_counter = [0]   # 用 list 便于内部函数修改

        logging.info(
            f"[import_from_docx] 源文件: {docx_p}\n"
            f"[import_from_docx] 媒体目录: {media_dir}"
        )

        # ---------- 1. 顶层段落 ----------
        logging.debug("[import_from_docx] 开始处理顶层段落")
        for para in doc.paragraphs:
            text = para.text.strip()

            # 提取段落内嵌图片
            inline_imgs = _extract_para_images(
                para, doc, media_dir, img_counter, docx_p
            )

            if not text:
                # 段落无文字
                if inline_imgs:
                    for img_md in inline_imgs:
                        md_lines.append(img_md)
                else:
                    md_lines.append("")
                continue

            style_name = para.style.name if para.style else ""

            # 标题
            if style_name.startswith("Heading"):
                try:
                    level = int(style_name.split()[-1])
                except (ValueError, IndexError):
                    level = 1
                md_lines.append("#" * level + " " + text)
                for img_md in inline_imgs:
                    md_lines.append(img_md)
                continue

            # 列表
            if "List" in style_name:
                if "Number" in style_name:
                    md_lines.append("1. " + text)
                else:
                    md_lines.append("- " + text)
                for img_md in inline_imgs:
                    md_lines.append(img_md)
                continue

            # 普通段落（处理粗体、斜体）
            md_lines.append(_para_to_md(para))
            for img_md in inline_imgs:
                md_lines.append(img_md)

        # ---------- 2. v5.0.2 增强：表格单元格图片 ----------
        logging.debug("[import_from_docx] 开始处理表格")
        for t_idx, table in enumerate(doc.tables):
            md_lines.append("")
            md_lines.append(_docx_table_to_md(table))
            md_lines.append("")

            # 提取表格单元格内的图片
            for para in _iter_table_paragraphs(table):
                cell_imgs = _extract_para_images(
                    para, doc, media_dir, img_counter, docx_p
                )
                for img_md in cell_imgs:
                    md_lines.append(img_md)

        # ---------- 3. v5.0.2 增强：页眉/页脚图片 ----------
        logging.debug("[import_from_docx] 开始处理页眉页脚")
        for s_idx, section in enumerate(doc.sections):
            try:
                for para in _iter_header_footer_paragraphs(section):
                    hf_imgs = _extract_para_images(
                        para, doc, media_dir, img_counter, docx_p
                    )
                    for img_md in hf_imgs:
                        md_lines.append(img_md)
            except Exception as e:
                logging.debug(f"处理 section {s_idx} 页眉页脚失败: {e}")

        # ---------- 完成汇总 ----------
        logging.info(
            f"[import_from_docx] 提取完成，共提取 {img_counter[0]} 张图片"
        )

        return "\n".join(md_lines)
    except Exception as e:
        logging.error(f"DOCX 导入失败: {e}")
        raise


def _extract_para_images(para, doc, media_dir, img_counter, docx_p):
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

                # 相对于 docx 文件的相对路径
                rel_path = f"{docx_p.stem}_media/{img_name}"
                imgs_md.append(f"![]({rel_path})")
            except Exception as e:
                logging.warning(
                    f"[_extract_para_images] 提取单个图片失败 "
                    f"{source_type} rId={r_id}: {e}"
                )
    except Exception as e:
        logging.warning(f"提取段落图片失败: {e}")

    return imgs_md


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


def _para_to_md(para):
    """将段落转为 Markdown（保留粗体、斜体）"""
    parts = []
    for run in para.runs:
        text = run.text
        if not text:
            continue
        if run.bold:
            text = f"**{text}**"
        if run.italic:
            text = f"*{text}*"
        parts.append(text)
    return "".join(parts)


def _docx_table_to_md(table):
    """将 docx 表格转为 Markdown 表格"""
    lines = []
    for ri, row in enumerate(table.rows):
        cells = [cell.text.strip().replace("|", "\\|")
                 for cell in row.cells]
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
        doc.save(output_path)
        return True
    except Exception as e:
        logging.error(f"HTML→DOCX 失败: {e}")
        return False