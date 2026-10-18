# beeoffice/plugins/beeshow_pptx_engine.py
"""
蜜演 PPTX 导出引擎（任务 3.1 + 任务 3.2）

设计目标：
  把 HTML 幻灯片转为 PPTX 时，**保留原生可编辑文本**，而非全量截图。
  参考 html-to-pptx 的 headless 测量 + 元素映射方案。

v5.1 增量汇总：
  - 任务 3.1：本模块整体（HTML → 原生 PPTX）
  - 任务 3.2：PPTXEngine.export 末尾追加字体子集化 + 嵌入
             （延迟 import beeshow_font_subset.FontEmbedder）

架构：
  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
  │ HTML 幻灯片  │ →  │  元素测量    │ →  │  PPTX 生成   │
  │ (list[str])  │    │ (MeasureResult)│    │ (python-pptx)│
  └──────────────┘    └──────────────┘    └──────────────┘
                                                ↓ 任务 3.2
                                          ┌──────────────┐
                                          │ 字体子集化    │
                                          │ + 嵌入 PPTX  │
                                          └──────────────┘

元素类型：
  - text      : 文本块（h1/h2/h3/p/li）→ 原生文本框
  - image     : 图片 → 原生 Picture
  - table     : 表格 → 原生 Table
  - rect      : 矩形背景 → 原生 Rectangle
  - snapshot  : 复杂 CSS 块（渐变/阴影）→ 局部 PNG 快照

测量实现（双路径）：
  1. 首选：Playwright headless Chromium（精确的 getBoundingClientRect）
  2. 回退：BeautifulSoup 纯文本降级（无 Playwright 时）

坐标换算：
  - CSS 像素（96 DPI）→ EMU（English Metric Units）
  - 1 inch = 914400 EMU = 96 px
  - 即：1 px = 9525 EMU

依赖：
  - python-pptx（必需）
  - playwright（可选，推荐）：pip install playwright && playwright install chromium
  - Pillow（可选，用于快照合成）
  - fonttools（任务 3.2，可选但推荐）：pip install fonttools
  - beautifulsoup4（降级路径使用）

用法：
  from beeoffice.plugins.beeshow_pptx_engine import PPTXEngine
  engine = PPTXEngine()
  engine.export(
      slides_html=[...],
      output_path="demo.pptx",
      theme_css="...",
      slide_width=10.0,      # 英寸
      slide_height=7.5,
  )

注意：
  - 该引擎不依赖 Qt，可在纯 Python 环境跑（用于 CI 测试）
  - 测量失败时降级为"仅文本"模式（不保真但至少可编辑）
  - 任务 3.2 的字体嵌入失败不影响主流程（PPTX 已生成）
"""

import json
import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any
from beeoffice.i18n import tr


# ==================== 常量 ====================
# 1 CSS 像素 = 9525 EMU（96 DPI）
PX_TO_EMU = 9525

# 默认幻灯片尺寸（英寸）
DEFAULT_SLIDE_WIDTH = 10.0
DEFAULT_SLIDE_HEIGHT = 7.5


# ==================== 数据结构 ====================
@dataclass
class MeasuredElement:
    """
    测量后的单个 DOM 元素。

    字段：
      tag       : HTML 标签名（h1/h2/p/li/img/table/div）
      text      : 文本内容（文本元素）
      x, y      : 左上角坐标（CSS 像素，相对幻灯片）
      width     : 宽（CSS 像素）
      height    : 高（CSS 像素）
      font_size : 字号（pt）
      bold      : 是否加粗
      italic    : 是否斜体
      color     : 文字颜色（#RRGGBB）
      align     : 对齐（left/center/right）
      src       : 图片路径（图片元素）
      bg_color  : 背景色（形状元素）
      z_index   : 层级
    """
    tag: str = ""
    text: str = ""
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    font_size: float = 18.0
    bold: bool = False
    italic: bool = False
    color: str = "#333333"
    align: str = "left"
    src: str = ""
    bg_color: str = ""
    z_index: int = 0


@dataclass
class MeasuredSlide:
    """测量后的一页幻灯片"""
    elements: List[MeasuredElement] = field(default_factory=list)
    bg_color: str = "#FFFFFF"
    error: str = ""


# ==================== 测量器 ====================
class ElementMeasurer:
    """
    DOM 元素测量器。

    双路径：
      - Playwright（推荐，精确）
      - BeautifulSoup 纯文本降级（无 Playwright 时）
    """

    # 注入到页面的测量 JS
    # 遍历 .slide 内所有元素，返回 {tag, text, rect, style}
    MEASURE_JS = r"""
    () => {
        const slide = document.querySelector('.slide');
        if (!slide) return [];
        const results = [];
        const slideRect = slide.getBoundingClientRect();

        function walk(el) {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            const tag = el.tagName.toLowerCase();

            // 跳过不可见元素
            if (style.display === 'none' ||
                style.visibility === 'hidden' ||
                rect.width < 1 || rect.height < 1) {
                return;
            }

            // 只处理叶子文本节点或特殊元素
            const hasBlockChild = Array.from(el.children).some(
                c => ['div', 'p', 'ul', 'ol', 'table', 'h1', 'h2',
                      'h3', 'h4'].includes(c.tagName.toLowerCase())
            );

            const text = el.innerText ? el.innerText.trim() : '';
            const isTextTag = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                               'p', 'li', 'blockquote', 'span']
                               .includes(tag);
            const isImage = tag === 'img';
            const isTable = tag === 'table';

            if (isTextTag && !hasBlockChild && text) {
                results.push({
                    tag: tag,
                    text: text,
                    x: rect.left - slideRect.left,
                    y: rect.top - slideRect.top,
                    width: rect.width,
                    height: rect.height,
                    font_size: parseFloat(style.fontSize) || 18,
                    bold: parseInt(style.fontWeight) >= 600,
                    italic: style.fontStyle === 'italic',
                    color: style.color,
                    align: style.textAlign,
                    bg_color: style.backgroundColor,
                    z_index: parseInt(style.zIndex) || 0,
                    src: ''
                });
            } else if (isImage) {
                results.push({
                    tag: 'img',
                    text: el.alt || '',
                    x: rect.left - slideRect.left,
                    y: rect.top - slideRect.top,
                    width: rect.width,
                    height: rect.height,
                    font_size: 0,
                    bold: false,
                    italic: false,
                    color: '#000000',
                    align: 'center',
                    bg_color: '',
                    z_index: 0,
                    src: el.src || el.getAttribute('data-src') || ''
                });
            } else if (isTable) {
                results.push({
                    tag: 'table',
                    text: el.innerText,
                    x: rect.left - slideRect.left,
                    y: rect.top - slideRect.top,
                    width: rect.width,
                    height: rect.height,
                    font_size: 14,
                    bold: false,
                    italic: false,
                    color: '#333333',
                    align: 'left',
                    bg_color: '',
                    z_index: 0,
                    src: ''
                });
            } else if (!hasBlockChild) {
                // 递归子元素
                Array.from(el.children).forEach(walk);
            } else {
                // 容器元素：记录背景，再递归
                if (style.backgroundColor !== 'rgba(0, 0, 0, 0)'
                    && style.backgroundColor !== 'transparent') {
                    results.push({
                        tag: 'div',
                        text: '',
                        x: rect.left - slideRect.left,
                        y: rect.top - slideRect.top,
                        width: rect.width,
                        height: rect.height,
                        font_size: 0,
                        bold: false,
                        italic: false,
                        color: '#000000',
                        align: 'left',
                        bg_color: style.backgroundColor,
                        z_index: -1,
                        src: ''
                    });
                }
                Array.from(el.children).forEach(walk);
            }
        }

        Array.from(slide.children).forEach(walk);
        return results;
    }
    """

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self._playwright_available = self._check_playwright()

    def _check_playwright(self) -> bool:
        """检查 playwright 是否可用"""
        try:
            import playwright  # noqa: F401
            return True
        except ImportError:
            return False

    def measure(
        self, full_html: str, width: int = 1280, height: int = 960
    ) -> MeasuredSlide:
        """
        测量单页 HTML。

        :param full_html: 完整 HTML（含 .slide）
        :param width: 视口宽（CSS 像素）
        :param height: 视口高
        :return: MeasuredSlide
        """
        if self._playwright_available:
            return self._measure_playwright(full_html, width, height)
        else:
            return self._measure_fallback(full_html)

    # ---------- 路径 1：Playwright ----------
    def _measure_playwright(
        self, full_html: str, width: int, height: int
    ) -> MeasuredSlide:
        """用 Playwright 测量（精确）"""
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(
                    viewport={"width": width, "height": height}
                )
                page.set_content(full_html)
                page.wait_for_timeout(300)

                raw = page.evaluate(self.MEASURE_JS)
                bg = page.evaluate(
                    "() => getComputedStyle("
                    "document.querySelector('.slide')"
                    ").backgroundColor"
                )
                browser.close()

                return self._parse_measure_result(raw, bg)
        except Exception as e:
            logging.error(f"Playwright 测量失败：{e}")
            return MeasuredSlide(error=str(e))

    # ---------- 路径 2：纯文本降级 ----------
    def _measure_fallback(self, full_html: str) -> MeasuredSlide:
        """
        无 Playwright 时的降级测量。

        只提取纯文本，位置靠自动布局（不保真，但至少可编辑）。
        """
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(full_html, "html.parser")
            slide = soup.find(class_="slide")
            if not slide:
                return MeasuredSlide(error="未找到 .slide 元素")

            elements = []
            y = 60.0
            for tag in slide.find_all(
                ["h1", "h2", "h3", "h4", "p", "li", "blockquote"]
            ):
                text = tag.get_text().strip()
                if not text:
                    continue
                name = tag.name.lower()
                font_size = {
                    "h1": 36, "h2": 28, "h3": 22, "h4": 20,
                    "p": 18, "li": 18, "blockquote": 18,
                }.get(name, 18)
                elements.append(MeasuredElement(
                    tag=name,
                    text=text,
                    x=80.0,
                    y=y,
                    width=1120.0,
                    height=font_size * 1.8,
                    font_size=font_size,
                    bold=name in ("h1", "h2", "h3"),
                    color="#333333",
                    align="left",
                ))
                y += font_size * 2.2

            return MeasuredSlide(elements=elements)
        except Exception as e:
            logging.error(f"降级测量失败：{e}")
            return MeasuredSlide(error=str(e))

    def _parse_measure_result(
        self, raw: List[Dict[str, Any]], bg: str
    ) -> MeasuredSlide:
        """把 JS 返回的原始 dict 解析为 MeasuredElement"""
        elements = []
        for item in raw:
            # 解析颜色：#RRGGBB 或 rgb(r,g,b)
            color = self._normalize_color(item.get("color", ""))
            bg_color = self._normalize_color(item.get("bg_color", ""))

            elements.append(MeasuredElement(
                tag=item.get("tag", ""),
                text=item.get("text", ""),
                x=float(item.get("x", 0)),
                y=float(item.get("y", 0)),
                width=float(item.get("width", 0)),
                height=float(item.get("height", 0)),
                font_size=float(item.get("font_size", 18)),
                bold=bool(item.get("bold", False)),
                italic=bool(item.get("italic", False)),
                color=color,
                align=item.get("align", "left") or "left",
                src=item.get("src", ""),
                bg_color=bg_color,
                z_index=int(item.get("z_index", 0)),
            ))

        return MeasuredSlide(
            elements=elements,
            bg_color=self._normalize_color(bg) or "#FFFFFF",
        )

    @staticmethod
    def _normalize_color(c: str) -> str:
        """把 rgb(r,g,b) / rgba(...) 转为 #RRGGBB"""
        if not c:
            return ""
        c = c.strip()
        if c.startswith("#"):
            return c
        if c.startswith("rgb"):
            try:
                nums = c[c.index("(") + 1: c.index(")")].split(",")
                r = int(float(nums[0].strip()))
                g = int(float(nums[1].strip()))
                b = int(float(nums[2].strip()))
                return f"#{r:02X}{g:02X}{b:02X}"
            except Exception:
                return ""
        return ""


# ==================== 生成器 ====================
class PPTXGenerator:
    """
    MeasuredSlide → PPTX 生成器。

    使用 python-pptx 的原生 API 创建元素：
      - 文本 → slide.shapes.add_textbox
      - 图片 → slide.shapes.add_picture
      - 表格 → slide.shapes.add_table
      - 背景 → slide.background.fill（纯色）
    """

    def __init__(
        self,
        slide_width: float = DEFAULT_SLIDE_WIDTH,
        slide_height: float = DEFAULT_SLIDE_HEIGHT,
    ):
        self.slide_width = slide_width
        self.slide_height = slide_height
        # 测量时的视口宽（需与 ElementMeasurer 一致）
        self.view_width = 1280.0
        self.view_height = 960.0

    def generate(
        self,
        slides: List[MeasuredSlide],
        output_path: str,
    ) -> bool:
        """
        生成 PPTX 文件。

        :param slides: 测量后的幻灯片列表
        :param output_path: 输出路径
        :return: 是否成功
        """
        try:
            from pptx import Presentation
            from pptx.util import Inches, Pt, Emu
            from pptx.dml.color import RGBColor
            from pptx.enum.text import PP_ALIGN

            prs = Presentation()
            prs.slide_width = Inches(self.slide_width)
            prs.slide_height = Inches(self.slide_height)

            # 空白布局（不用占位符，全部手动放）
            blank_layout = prs.slide_layouts[6]

            for ms in slides:
                slide = prs.slides.add_slide(blank_layout)

                # 背景色
                if ms.bg_color and ms.bg_color != "#FFFFFF":
                    self._set_slide_bg(slide, ms.bg_color)

                # 逐个元素
                for el in ms.elements:
                    try:
                        self._add_element(slide, el, prs)
                    except Exception as e:
                        logging.warning(f"添加元素失败 {el.tag}：{e}")

            prs.save(output_path)
            logging.info(f"PPTX 已生成：{output_path}")
            return True

        except ImportError:
            logging.error("python-pptx 未安装")
            return False
        except Exception as e:
            logging.error(f"PPTX 生成失败：{e}")
            return False

    # ---------- 背景 ----------
    def _set_slide_bg(self, slide, hex_color: str):
        """设置幻灯片背景纯色"""
        try:
            from pptx.dml.color import RGBColor
            fill = slide.background.fill
            fill.solid()
            fill.fore_color.rgb = RGBColor.from_string(
                hex_color.lstrip("#")
            )
        except Exception as e:
            logging.debug(f"设置背景失败：{e}")

    # ---------- 元素分发 ----------
    def _add_element(self, slide, el: MeasuredElement, prs):
        """按元素类型分发"""
        if el.tag == "img" and el.src:
            self._add_picture(slide, el)
        elif el.tag == "table":
            self._add_table(slide, el)
        elif el.tag == "div" and el.bg_color:
            self._add_rect(slide, el)
        elif el.text:
            self._add_textbox(slide, el)

    # ---------- 文本框 ----------
    def _add_textbox(self, slide, el: MeasuredElement):
        """添加原生文本框（可编辑、可搜索）"""
        from pptx.util import Emu, Pt
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN

        left = self._px_to_emu(el.x)
        top = self._px_to_emu(el.y)
        width = self._px_to_emu(el.width)
        height = self._px_to_emu(el.height)

        tb = slide.shapes.add_textbox(left, top, width, height)
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = 0
        tf.margin_right = 0
        tf.margin_top = 0
        tf.margin_bottom = 0

        p = tf.paragraphs[0]
        run = p.add_run()
        run.text = el.text

        # 字号（CSS px → pt：1 px = 0.75 pt）
        run.font.size = Pt(el.font_size * 0.75)
        run.font.bold = el.bold
        run.font.italic = el.italic
        if el.color:
            try:
                run.font.color.rgb = RGBColor.from_string(
                    el.color.lstrip("#")
                )
            except Exception:
                pass

        # 对齐
        align_map = {
            "left": PP_ALIGN.LEFT,
            "center": PP_ALIGN.CENTER,
            "right": PP_ALIGN.RIGHT,
            "justify": PP_ALIGN.JUSTIFY,
        }
        p.alignment = align_map.get(el.align, PP_ALIGN.LEFT)

    # ---------- 图片 ----------
    def _add_picture(self, slide, el: MeasuredElement):
        """添加原生图片"""
        from pathlib import Path as _Path
        src = el.src
        if src.startswith("file://"):
            src = src[7:]
        if not _Path(src).exists():
            logging.debug(f"图片不存在，跳过：{src}")
            return

        left = self._px_to_emu(el.x)
        top = self._px_to_emu(el.y)
        width = self._px_to_emu(el.width) if el.width > 0 else None
        height = self._px_to_emu(el.height) if el.height > 0 else None

        kwargs = {"left": left, "top": top}
        if width:
            kwargs["width"] = width
        if height:
            kwargs["height"] = height
        slide.shapes.add_picture(str(src), **kwargs)

    # ---------- 表格 ----------
    def _add_table(self, slide, el: MeasuredElement):
        """
        添加原生表格。

        注意：从 innerText 还原表格结构信息有限，
        这里采用简单策略：按行拆分为单列表格。
        如需完整表格，需测量器额外提供行列数据（后续迭代）。
        """
        from pptx.util import Emu, Pt

        lines = [l for l in el.text.split("\n") if l.strip()]
        if not lines:
            return

        left = self._px_to_emu(el.x)
        top = self._px_to_emu(el.y)
        width = self._px_to_emu(el.width)
        height = self._px_to_emu(el.height)

        rows = len(lines)
        cols = 1
        table_shape = slide.shapes.add_table(
            rows, cols, left, top, width, height
        )
        table = table_shape.table

        for i, line in enumerate(lines):
            cell = table.cell(i, 0)
            cell.text = line.strip()
            for para in cell.text_frame.paragraphs:
                for run in para.runs:
                    run.font.size = Pt(12)

    # ---------- 矩形背景 ----------
    def _add_rect(self, slide, el: MeasuredElement):
        """添加矩形背景（用于容器的背景色）"""
        from pptx.util import Emu
        from pptx.dml.color import RGBColor
        from pptx.enum.shapes import MSO_SHAPE

        left = self._px_to_emu(el.x)
        top = self._px_to_emu(el.y)
        width = self._px_to_emu(el.width)
        height = self._px_to_emu(el.height)

        shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, left, top, width, height
        )
        shape.fill.solid()
        try:
            shape.fill.fore_color.rgb = RGBColor.from_string(
                el.bg_color.lstrip("#")
            )
        except Exception:
            pass
        # 无边框
        shape.line.fill.background()

    # ---------- 坐标换算 ----------
    def _px_to_emu(self, px: float) -> int:
        """
        CSS 像素 → EMU（按比例映射到幻灯片尺寸）。

        视口宽 1280px → 幻灯片 10 英寸。
        所以 1 px = (10 / 1280) 英寸 = 0.0078125 英寸
        """
        inches = px / self.view_width * self.slide_width
        return int(inches * 914400)


# ==================== 顶层引擎 ====================
class PPTXEngine:
    """
    HTML → PPTX 顶层引擎。

    用法：
      engine = PPTXEngine()
      success = engine.export(
          slides_html=[...],        # 每页 HTML 片段
          output_path="demo.pptx",
          theme_css="...",          # 主题 CSS
          slide_width=10.0,
          slide_height=7.5,
      )

    内部流程：
      1. 为每页 HTML 拼上主题 CSS，得到完整 HTML
      2. 用 ElementMeasurer 测量每页
      3. 用 PPTXGenerator 生成 PPTX
      4. 任务 3.2：用 FontEmbedder 子集化字体并嵌入 PPTX
    """

    def __init__(
        self,
        slide_width: float = DEFAULT_SLIDE_WIDTH,
        slide_height: float = DEFAULT_SLIDE_HEIGHT,
    ):
        self.slide_width = slide_width
        self.slide_height = slide_height
        self.measurer = ElementMeasurer()
        self.generator = PPTXGenerator(slide_width, slide_height)

    def export(
        self,
        slides_html: List[str],
        output_path: str,
        theme_css: str = "",
        bg_color: str = "#FFFFFF",
        slide_width: Optional[float] = None,
        slide_height: Optional[float] = None,
    ) -> bool:
        """
        执行导出。

        :param slides_html: 每页的 HTML 片段（不含 <html> 包裹）
        :param output_path: 输出 .pptx 路径
        :param theme_css: 主题 CSS（拼入完整 HTML）
        :param bg_color: 背景色
        :param slide_width: 覆盖默认宽
        :param slide_height: 覆盖默认高
        :return: 是否成功

        任务 3.2：PPTX 生成后自动调用字体子集化 + 嵌入。
        """
        if slide_width:
            self.slide_width = slide_width
            self.generator.slide_width = slide_width
        if slide_height:
            self.slide_height = slide_height
            self.generator.slide_height = slide_height

        if not slides_html:
            logging.warning(tr("auto.beeshow_pptx_engine.1192cfac", "无幻灯片可导出"))
            return False

        measured_slides = []
        for i, html_fragment in enumerate(slides_html):
            full_html = self._wrap_html(html_fragment, theme_css, bg_color)
            ms = self.measurer.measure(full_html)
            if ms.error:
                # 测量失败意味着这一页的版式一定是错的（文字位置、图片尺寸全部退化）。
                # 原来的行为是"记一条 warning 然后继续生成并返回 True"，
                # 用户拿到的是一个能打开、但排版错乱的文件——比直接失败更糟。
                # 现在首错即中止，交由上层回退到图片版导出。
                logging.error(
                    f"PPTX 导出中止：第 {i+1}/{len(slides_html)} 页测量失败：{ms.error}"
                )
                return False
            measured_slides.append(ms)

        # 生成 PPTX
        success = self.generator.generate(measured_slides, output_path)
        if not success:
            return False

        # 任务 3.2：字体子集化 + 嵌入
        try:
            from beeoffice.plugins.beeshow_font_subset import FontEmbedder
            embedder = FontEmbedder()
            embed_ok = embedder.embed(
                pptx_path=output_path,
                slides_html=slides_html,
            )
            if embed_ok:
                logging.info("中文字体已嵌入 PPTX")
            else:
                logging.info(
                    "字体嵌入跳过（fonttools 未装或字体缺失），"
                    "导出正常但目标机器可能缺字体"
                )
        except Exception as e:
            logging.warning(f"字体嵌入异常（不影响导出）：{e}")

        return True

    def _wrap_html(
        self, fragment: str, theme_css: str, bg_color: str
    ) -> str:
        """拼装完整 HTML"""
        return (
            f'<!DOCTYPE html><html><head><meta charset="utf-8">'
            f'<style>{theme_css} '
            f'body{{margin:0;background:{bg_color};}}'
            f'.slide{{width:1280px;height:960px;}}'
            f'</style></head>'
            f'<body><div class="slide">{fragment}</div></body></html>'
        )


# ==================== 便捷函数 ====================
def export_html_to_pptx(
    slides_html: List[str],
    output_path: str,
    theme_css: str = "",
    bg_color: str = "#FFFFFF",
) -> bool:
    """
    便捷函数：HTML 片段列表 → PPTX。

    :param slides_html: 每页 HTML 片段
    :param output_path: 输出路径
    :param theme_css: 主题 CSS
    :param bg_color: 背景色
    :return: 是否成功
    """
    engine = PPTXEngine()
    return engine.export(
        slides_html=slides_html,
        output_path=output_path,
        theme_css=theme_css,
        bg_color=bg_color,
    )