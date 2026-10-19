# beeoffice/plugins/beeshow_pptx_import.py
"""
把 **`.pptx` 读成蜜演文稿**（P0-1：「打开别人的 PPT」）。

## 为什么单独一个纯模块
蜜演是 WebEngine 视图，"打开 pptx"这件事**不该依赖界面**：
* 转换逻辑放在这里 → 可以被 CLI（`beecmd`）、界面、测试**共用**；
* 纯 python-pptx + 标准库 → **不 import Qt**（可以在服务器上跑）。

## 能力边界（v1，**只说真做到的**）
**会保留**：每页的**标题**、正文**段落与层级**（缩进 → 列表层级）、
**演讲者备注**、页序。
**不保留（会写进损失报告）**：版式/主题/配色、字体与字号、图片、
表格、图表、SmartArt、动画与切换、超链接的目标、母版与占位符位置。
也就是说：**文字内容进得来，版式要重排** —— 这是诚实的预期，
而不是"能打开 pptx 了"这种含糊说法。

## 与 `.beshow` 的关系
输出就是蜜演自己的文稿格式（Markdown + `---` 分页 + 一行标记，
标记由 `beeshow_doc.save_deck` 加），所以"导入"= 生成一份正常的 `.beshow`，
后续的编辑/保存/导出走的都是既有链路，不新增格式。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

#: 蜜演文稿的页分隔符（与 `beeshow.py` 的模板一致）
PAGE_SEPARATOR = "---"


@dataclass
class SlideContent:
    """一页幻灯片抽出来的内容。"""

    index: int
    title: str = ""
    bullets: List[Tuple[int, str]] = field(default_factory=list)  # (层级, 文本)
    notes: str = ""
    images: int = 0
    tables: int = 0
    charts: int = 0


@dataclass
class PptxImport:
    """一次导入的结果（含**损失清单**，用于如实告知用户）。"""

    slides: List[SlideContent] = field(default_factory=list)
    losses: Dict[str, int] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    @property
    def slide_count(self) -> int:
        return len(self.slides)

    def has_losses(self) -> bool:
        return bool(self.losses) or bool(self.warnings)


def read_pptx(path) -> PptxImport:
    """
    读 `.pptx`，抽文字内容并统计**无法保留**的元素。

    :raises BeecmdError 风格的 `ValueError`：文件不存在/不是 pptx/python-pptx 缺失
        时给出**可操作**的说明（不静默返回空文稿 —— 那会让用户以为文件是空的）。
    """
    file = Path(path)
    if not file.is_file():
        raise ValueError(f"文件不存在: {file}")
    if file.suffix.lower() != ".pptx":
        raise ValueError(f"不是 .pptx 文件: {file.suffix}")

    try:
        from pptx import Presentation
    except ImportError as e:  # pragma: no cover - 依赖缺失时的可操作提示
        raise ValueError(
            "导入 .pptx 需要 python-pptx：pip install python-pptx"
        ) from e

    presentation = Presentation(str(file))
    result = PptxImport()

    for index, slide in enumerate(presentation.slides, 1):
        content = SlideContent(index=index)
        _read_slide_texts(slide, content)
        _count_unsupported(slide, content, result)
        result.slides.append(content)

    if not result.slides:
        result.warnings.append("这份演示里一页幻灯片都没有")
    return result


def _read_slide_texts(slide, content: SlideContent) -> None:
    """取标题 / 正文层级 / 备注（只用公开 API，不碰底层 XML）。"""
    title_id = None
    try:
        title_shape = slide.shapes.title
        if title_shape is not None and title_shape.has_text_frame:
            content.title = title_shape.text_frame.text.strip()
            # ⚠️ 不能用 `is` 比较：`slide.shapes.title` 每次返回**新的代理对象**，
            # `shape is title_shape` 永远为 False → 标题会被当成正文再抽一遍（踩过）。
            title_id = getattr(title_shape, "shape_id", None)
    except Exception as e:  # noqa: BLE001 - 标题取不到不算致命
        logging.debug(f"[pptx] 第 {content.index} 页取标题失败: {e}")

    for shape in slide.shapes:
        if not getattr(shape, "has_text_frame", False):
            continue
        # 按 shape_id 跳过标题占位符（见上面的注释）
        if title_id is not None and getattr(shape, "shape_id", None) == title_id:
            continue
        for paragraph in shape.text_frame.paragraphs:
            text = "".join(run.text for run in paragraph.runs).strip()
            if not text:
                continue
            # 层级：python-pptx 的 paragraph.level 从 0 开始，层级越深越大
            level = int(getattr(paragraph, "level", 0) or 0)
            content.bullets.append((level, text))

    try:
        if slide.has_notes_slide:
            notes_frame = slide.notes_slide.notes_text_frame
            if notes_frame is not None:
                content.notes = notes_frame.text.strip()
    except Exception as e:  # noqa: BLE001 - 备注缺失不算致命
        logging.debug(f"[pptx] 第 {content.index} 页取备注失败: {e}")


def _count_unsupported(slide, content: SlideContent, result: PptxImport) -> None:
    """统计**无法保留**的元素，写进损失报告（不假装搬得过去）。"""
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    for shape in slide.shapes:
        try:
            shape_type = shape.shape_type
        except Exception:  # noqa: BLE001
            shape_type = None
        if shape_type == MSO_SHAPE_TYPE.PICTURE:
            content.images += 1
            result.losses["图片"] = result.losses.get("图片", 0) + 1
        elif getattr(shape, "has_table", False):
            content.tables += 1
            result.losses["表格"] = result.losses.get("表格", 0) + 1
        elif getattr(shape, "has_chart", False):
            content.charts += 1
            result.losses["图表"] = result.losses.get("图表", 0) + 1


def render_deck(imported: PptxImport) -> str:
    """
    把导入结果渲染成蜜演的 Markdown 文稿（`---` 分页；标记由 `save_deck` 加）。

    每页：`# 标题` → 正文按层级缩进成列表 → 备注写成 `> 备注：…`。
    """
    pages: List[str] = []
    for slide in imported.slides:
        lines: List[str] = []
        title = slide.title.strip()
        lines.append(f"# {title}" if title else f"# 第 {slide.index} 页")
        lines.append("")
        for level, text in slide.bullets:
            indent = "  " * max(0, level)
            lines.append(f"{indent}- {text}")
        if slide.bullets:
            lines.append("")
        if slide.notes:
            lines.append("> 备注：" + slide.notes.replace("\n", "\n> "))
            lines.append("")
        pages.append("\n".join(lines).rstrip() + "\n")
    return f"\n{PAGE_SEPARATOR}\n\n".join(pages)


def loss_summary(imported: PptxImport) -> str:
    """把损失清单渲染成**人能读懂**的一段话（用于对话框/报告）。"""
    if not imported.has_losses():
        return "未发现无法保留的元素（只有文字内容，全部保留）。"
    parts: List[str] = []
    if imported.losses:
        detail = "、".join(f"{name} × {count}"
                          for name, count in sorted(imported.losses.items()))
        parts.append(f"以下元素**不会**进入文稿：{detail}")
    if imported.warnings:
        parts.extend(imported.warnings)
    parts.append(
        "文字内容（标题/正文层级/备注）已全部保留；"
        "版式、主题、字体与图片位置需要重新排版。"
    )
    return "\n".join(parts)


def import_pptx(path) -> Tuple[PptxImport, str]:
    """`(导入结果, Markdown 文稿文本)` —— 纯函数，无副作用、不写文件。"""
    imported = read_pptx(path)
    return imported, render_deck(imported)


def import_pptx_to_file(path, out_path) -> PptxImport:
    """转换并写成 `.beshow` 文件（走产品自己的 `save_deck`，保证标记/编码一致）。"""
    from beeoffice.plugins.beeshow_doc import save_deck

    imported, markdown = import_pptx(path)
    if not save_deck(str(out_path), markdown):
        raise ValueError(f"写 {out_path} 失败")
    return imported
