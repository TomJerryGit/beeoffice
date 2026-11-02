# beeoffice/plugins/beeshow_print_mixin.py
"""
蜜演的**打印 / 打印预览**（P1-B ★★）：幻灯片、讲义、备注页、大纲。

为什么要有它
------------
实机清点发现：打印只实现在**蜜写**，蜜算此前也没有（已补），**蜜演同样没有**。
演示场景里"打讲义发给听众""打备注页自己讲"是常规需求。

怎么拿到幻灯片的画面
--------------------
蜜演的幻灯片是 **QtWebEngine 渲染的 HTML**，所以画面只能由 WebEngine 产出。
本模块**复用仓库里已有的路子**（见 `beeshow_export_mixin._export_pdf`）：

    render_slide_html(...) → QWebEngineView.loadHtml → page().printToPdf()
    → 得到"每页一张幻灯片"的 PDF
    → 再用 `QPdfDocument` 把每页**栅格化成 QImage**
    → 最后用 QPainter 按讲义/备注页版式拼到打印页上

**分层设计（重要）**：把"**排版计划**"和"**绘制**"和"**需要 WebEngine 的取图**"
三层分开：
  · `_build_print_plan()`  —— 纯数据（哪一页放哪几张、网格位置、备注文字），
    测试直接断言，**不需要 WebEngine、也不需要字体**；
  · `_paint_plan()`        —— 只吃 `QImage`，所以测试可以喂**合成图**，
    并用 PyMuPDF 把输出 PDF **逐像素**回读，验证"第 N 张图确实落在第 N 格"；
  · `_slides_pdf()`        —— 唯一依赖 WebEngine 的一层，**单独隔离**，
    失败时给出明确中文提示（本沙箱 QtWebEngine 不可用，见测试说明）。
"""
import logging
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor, QFont, QImage, QPageLayout, QPageSize, QPainter, QPen,
)
from PySide6.QtWidgets import QMessageBox

#: 讲义每页张数 → (行, 列)
HANDOUT_LAYOUTS = {
    1: (1, 1),
    2: (1, 2),
    3: (1, 3),
    4: (2, 2),
    6: (2, 3),
    9: (3, 3),
}

#: 打印模式
MODE_SLIDES = "slides"       # 每页一张幻灯片
MODE_HANDOUT = "handout"     # 讲义：每页 N 张
MODE_NOTES = "notes"         # 备注页：缩略图 + 备注
MODE_OUTLINE = "outline"     # 大纲：纯文字

MODE_LABELS = {
    MODE_SLIDES: "幻灯片（每页 1 张）",
    MODE_HANDOUT: "讲义（每页多张）",
    MODE_NOTES: "备注页（幻灯片 + 备注）",
    MODE_OUTLINE: "大纲（仅文字）",
}

MARGIN_MM = 12.0
GAP_MM = 4.0


class ShowPrintMixin:
    """蜜演打印 / 打印预览。"""

    # ==================================================================
    # 一、取数据（不需要 WebEngine）
    # ==================================================================
    def _print_slide_count(self) -> int:
        return len(getattr(self, "_slides_html", []) or [])

    def _print_notes(self, index: int) -> str:
        """取第 index 张幻灯片的备注（没有就返回空串）。"""
        notes = getattr(self, "_speaker_notes", None) or []
        if 0 <= index < len(notes):
            return str(notes[index] or "")
        return ""

    def _print_slide_title(self, index: int) -> str:
        """
        取第 index 张幻灯片的标题（用于大纲/备注页抬头）。

        优先用 Markdown 源的第一行标题；取不到再退回"第 N 张"。
        """
        slides_md = getattr(self, "_slides_md", None) or []
        if 0 <= index < len(slides_md):
            for line in str(slides_md[index] or "").splitlines():
                text = line.strip()
                if not text:
                    continue
                # 去掉常见的 Markdown 前缀（标题/列表/引用）
                while text and text[0] in "#->*+ ":
                    text = text[1:].lstrip()
                if text:
                    return text[:60]
        return f"第 {index + 1} 张"

    # ==================================================================
    # 二、排版计划（纯数据，可测）
    # ==================================================================
    @staticmethod
    def _build_print_plan(slide_count, mode=MODE_SLIDES, per_page=1,
                          titles=None, notes=None):
        """
        生成排版计划 —— **纯数据**，不做任何绘制、不碰 WebEngine。

        :param slide_count: 幻灯片张数
        :param mode: MODE_SLIDES / MODE_HANDOUT / MODE_NOTES / MODE_OUTLINE
        :param per_page: 讲义模式每页张数（必须是 `HANDOUT_LAYOUTS` 的键）
        :param titles: 每张的标题（大纲/备注页用）
        :param notes: 每张的备注文本（备注页用）
        :return: {"mode", "rows", "cols", "pages": [...], "slide_count",
                  "empty"}
          每个 page = {"page_no", "total_pages", "footer_right",
                       "items": [{"slide": i, "row": r, "col": c,
                                  "title": …, "notes": …}],
                       "outline_lines": [...]}
        """
        titles = list(titles or [])
        notes = list(notes or [])
        slide_count = max(0, int(slide_count))

        plan = {
            "mode": mode,
            "rows": 1,
            "cols": 1,
            "pages": [],
            "slide_count": slide_count,
            "empty": slide_count == 0,
        }
        if slide_count == 0:
            return plan

        if mode == MODE_OUTLINE:
            # 大纲：每页固定行数，纯文字
            lines_per_page = 34
            entries = [
                (i, titles[i] if i < len(titles) else f"第 {i + 1} 张")
                for i in range(slide_count)
            ]
            pages = []
            for start in range(0, len(entries), lines_per_page):
                chunk = entries[start:start + lines_per_page]
                pages.append({
                    "page_no": len(pages) + 1,
                    "items": [],
                    "outline_lines": [
                        {"slide": i, "title": t, "level": 0}
                        for i, t in chunk
                    ],
                })
            plan.update({"rows": 0, "cols": 0, "pages": pages})
            _fill_footers(plan)
            return plan

        if mode == MODE_NOTES:
            # 备注页：**一张幻灯片一页**（缩略图 + 备注）
            pages = []
            for i in range(slide_count):
                pages.append({
                    "page_no": i + 1,
                    "items": [{
                        "slide": i,
                        "row": 0,
                        "col": 0,
                        "title": titles[i] if i < len(titles)
                        else f"第 {i + 1} 张",
                        "notes": notes[i] if i < len(notes) else "",
                    }],
                    "outline_lines": [],
                })
            plan.update({"rows": 1, "cols": 1, "pages": pages})
            _fill_footers(plan)
            return plan

        # 幻灯片 / 讲义
        if mode == MODE_HANDOUT:
            per_page = per_page if per_page in HANDOUT_LAYOUTS else 4
        else:
            per_page = 1
        rows, cols = HANDOUT_LAYOUTS.get(per_page, (2, 2))

        pages = []
        for start in range(0, slide_count, per_page):
            items = []
            for offset in range(per_page):
                index = start + offset
                if index >= slide_count:
                    break
                items.append({
                    "slide": index,
                    "row": offset // cols,
                    "col": offset % cols,
                    "title": titles[index] if index < len(titles)
                    else f"第 {index + 1} 张",
                    "notes": "",
                })
            pages.append({
                "page_no": len(pages) + 1,
                "items": items,
                "outline_lines": [],
            })
        plan.update({"rows": rows, "cols": cols, "pages": pages})
        _fill_footers(plan)
        return plan

    # ==================================================================
    # 三、绘制（只吃 QImage，可喂合成图做像素级验证）
    # ==================================================================
    @staticmethod
    def _paint_plan(printer, plan, images):
        """
        按排版计划把图片画到打印设备上。

        :param images: {slide_index: QImage}；缺图的格子会画一个占位框
                      （而不是静默留白 —— 用户要能看出"这里本该有东西"）
        """
        painter = QPainter(printer)
        try:
            rect = printer.pageLayout().paintRectPixels(printer.resolution())
            dpi = max(1.0, float(printer.resolution()))
            px = dpi / 25.4
            margin = MARGIN_MM * px
            gap = GAP_MM * px
            painter.translate(rect.left(), rect.top())

            if plan["empty"]:
                _draw_center_text(
                    painter, QRectF(0, 0, rect.width(), rect.height()),
                    14.0, "（这份演示没有幻灯片）",
                )
                return

            usable_w = max(1.0, rect.width() - 2 * margin)
            usable_h = max(1.0, rect.height() - 2 * margin)
            footer_h = 8.0 * px
            body_h = max(1.0, usable_h - footer_h)

            for page_index, page in enumerate(plan["pages"]):
                if page_index > 0:
                    if not printer.newPage():
                        break
                    painter.translate(rect.left(), rect.top())

                if plan["mode"] == MODE_OUTLINE:
                    _paint_outline_page(
                        painter, page, margin, margin, usable_w, body_h, px
                    )
                elif plan["mode"] == MODE_NOTES:
                    _paint_notes_page(
                        painter, page, images, margin, margin,
                        usable_w, body_h, px,
                    )
                else:
                    _paint_grid_page(
                        painter, page, plan["rows"], plan["cols"], images,
                        margin, margin, usable_w, body_h, gap, px,
                    )

                _draw_footer(
                    painter, page,
                    margin, rect.height() - margin + 1.0 * px, usable_w, px,
                )
        finally:
            painter.end()

    # ==================================================================
    # 四、取图（唯一依赖 WebEngine 的一层，单独隔离）
    # ==================================================================
    def _slides_pdf(self, target_path) -> bool:
        """
        把所有幻灯片渲染成一份"每页一张"的 PDF。

        ⚠️ 这一步**必须** QtWebEngine（与仓库里 `_export_pdf` 同一条路）。
        本沙箱 QWebEngine 不可用，因此这一步无法在此环境验证 —— 失败时
        返回 False 并由调用方给出明确提示，**不会静默变成空白打印**。
        """
        slides = getattr(self, "_slides_html", None) or []
        if not slides:
            return False
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView

            from beeoffice.plugins.beeshow_constants import SLIDE_THEMES
            from beeoffice.plugins.beeshow_html import render_slide_html
        except Exception as e:  # noqa: BLE001
            logging.warning(f"[蜜演打印] 无法加载渲染组件: {e}")
            return False

        theme = SLIDE_THEMES[self._current_theme]
        bg = self._custom_bg or theme.get("bg", "#FFF")

        parts = []
        for i, slide_html in enumerate(slides):
            page_break = (
                '<div style="page-break-after:always"></div>'
                if i < len(slides) - 1 else ''
            )
            parts.append(
                f"<div class='slide' style='width:100%;min-height:100vh;"
                f"display:flex;flex-direction:column;"
                f"justify-content:center;align-items:center;"
                f"padding:60px;box-sizing:border-box'>{slide_html}</div>"
                f"{page_break}"
            )
        full_html = render_slide_html(
            "".join(parts),
            theme_css=theme['css'],
            layout_css=self._get_layout_css(),
            bg=bg,
            extra_css="@page{size:A4 landscape;margin:0}body{margin:0}",
            wrap_slide=False,
        )

        view = QWebEngineView()
        try:
            self._export_views.append(view)
        except AttributeError:
            pass

        pdf_path = str(target_path)
        done = {"ok": False}

        def on_load(ok):
            try:
                if ok:
                    view.page().printToPdf(pdf_path)
                    done["ok"] = True
            except Exception as e:  # noqa: BLE001
                logging.warning(f"[蜜演打印] printToPdf 失败: {e}")

        view.loadFinished.connect(on_load)
        view.setHtml(full_html)

        # 等渲染完成（最多 30 秒）——与导出 PDF 不同，打印是同步流程，
        # 预览对话框需要拿到 PDF 才能画。
        import time

        from PySide6.QtWidgets import QApplication

        waited = 0.0
        while waited < 30.0 and not (
            done["ok"] and Path(pdf_path).exists()
            and Path(pdf_path).stat().st_size > 0
        ):
            QApplication.processEvents()
            time.sleep(0.05)
            waited += 0.05
        return Path(pdf_path).exists() and Path(pdf_path).stat().st_size > 0

    @staticmethod
    def _rasterize_slides(pdf_path, width=900):
        """
        把"每页一张幻灯片"的 PDF 栅格化成 QImage 列表。

        用 `QPdfDocument`（QtPdf）——**不需要 WebEngine，也不需要字体**，
        因此这一步在本环境可测（测试用 PyMuPDF 造的彩色 PDF 验证）。
        """
        from PySide6.QtPdf import QPdfDocument

        document = QPdfDocument()
        try:
            document.load(str(pdf_path))
            images = []
            for index in range(document.pageCount()):
                size = document.pagePointSize(index)
                if size.width() <= 0 or size.height() <= 0:
                    images.append(QImage())
                    continue
                height = max(1, int(width * size.height() / size.width()))
                images.append(document.render(index, QSize(width, height)))
            return images
        finally:
            document.close()

    # ==================================================================
    # 五、入口
    # ==================================================================
    def _print_preview(self):
        """蜜演的打印预览：先选模式，再预览。"""
        if self._print_slide_count() == 0:
            QMessageBox.information(self, "提示", "这份演示还没有幻灯片")
            return
        mode, per_page = _ask_print_options(self)
        if mode is None:
            return
        self._print_preview_with(mode, per_page)

    def _print_preview_with(self, mode, per_page=4):
        """按指定模式打开打印预览（供菜单/测试直接调用）。"""
        try:
            from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog
        except ImportError:
            QMessageBox.warning(self, "提示", "当前环境不支持打印功能")
            return

        from PySide6.QtCore import QDir, QTemporaryDir

        # 幻灯片是横向的：幻灯片/讲义/备注页都用横向，大纲用纵向
        landscape = mode != MODE_OUTLINE

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        printer.setPageOrientation(
            QPageLayout.Orientation.Landscape if landscape
            else QPageLayout.Orientation.Portrait
        )

        images = {}
        temp_dir = None
        if mode in (MODE_SLIDES, MODE_HANDOUT, MODE_NOTES):
            temp_dir = QTemporaryDir(QDir.tempPath() + "/beeoffice_print_XXXXXX")
            pdf_path = Path(temp_dir.path()) / "slides.pdf"
            if not self._slides_pdf(pdf_path):
                QMessageBox.warning(
                    self,
                    "无法渲染幻灯片",
                    "蜜演打印需要 QtWebEngine 把幻灯片渲染成画面，"
                    "当前环境不可用。\n\n"
                    "替代办法：用「导出 → PDF / 图片」再打印。",
                )
                return
            for index, image in enumerate(
                self._rasterize_slides(pdf_path, width=1200)
            ):
                images[index] = image

        plan = self._build_print_plan(
            self._print_slide_count(), mode=mode, per_page=per_page,
            titles=[self._print_slide_title(i)
                    for i in range(self._print_slide_count())],
            notes=[self._print_notes(i)
                   for i in range(self._print_slide_count())],
        )

        preview = QPrintPreviewDialog(printer, self)
        preview.setWindowTitle(f"🖨️ 打印预览（蜜演 · {MODE_LABELS.get(mode, mode)}）")
        preview.resize(1100, 800)
        preview.paintRequested.connect(
            lambda p: self._paint_plan(p, plan, images)
        )
        preview.exec()
        _ = temp_dir


# ======================================================================
# 模块级绘制辅助（纯函数，便于单独测试）
# ======================================================================
def _fill_footers(plan):
    """补上页脚页码（页码依赖总页数，所以统一在这里收尾）。"""
    total = len(plan["pages"])
    for page in plan["pages"]:
        page["total_pages"] = total
        page["footer_right"] = f"第 {page['page_no']} / {total} 页"


def _draw_center_text(painter, rect, point_size, text):
    painter.save()
    font = QFont()
    font.setPointSizeF(point_size)
    painter.setFont(font)
    painter.setPen(QPen(QColor(120, 120, 120)))
    painter.drawText(
        rect,
        Qt.AlignmentFlag.AlignCenter,
        text,
    )
    painter.restore()


def _draw_slide_frame(painter, rect, image):
    """画一个幻灯片框：有图就贴图，没图就画占位提示。"""
    painter.save()
    painter.setPen(QPen(QColor(160, 160, 160)))
    painter.drawRect(rect)
    if image is not None and not image.isNull():
        painter.drawImage(rect, image)
    else:
        _draw_center_text(painter, rect, 10.0, "（幻灯片画面不可用）")
    painter.restore()


def _paint_grid_page(painter, page, rows, cols, images,
                     left, top, width, height, gap, px):
    """讲义/幻灯片页：把本页的图按 rows×cols 网格摆好。"""
    if not page["items"]:
        return
    rows = max(1, rows)
    cols = max(1, cols)
    cell_w = (width - gap * (cols - 1)) / cols
    cell_h = (height - gap * (rows - 1)) / rows
    for item in page["items"]:
        row, col = item["row"], item["col"]
        x = left + col * (cell_w + gap)
        y = top + row * (cell_h + gap)
        _draw_slide_frame(
            painter, QRectF(x, y, cell_w, cell_h),
            images.get(item["slide"]),
        )


def _paint_notes_page(painter, page, images, left, top, width, height, px):
    """备注页：上半放幻灯片缩略图，下半放备注文字。"""
    if not page["items"]:
        return
    item = page["items"][0]
    thumb_h = height * 0.52
    _draw_slide_frame(
        painter, QRectF(left, top, width, thumb_h),
        images.get(item["slide"]),
    )

    # 备注文字
    text_top = top + thumb_h + 6.0 * px
    text_h = height - thumb_h - 6.0 * px
    painter.save()
    font = QFont()
    font.setPointSizeF(12.0)
    painter.setFont(font)
    painter.setPen(QPen(QColor(60, 60, 60)))
    header = f"备注 · {item.get('title') or ''}"
    painter.drawText(
        QRectF(left, text_top, width, 8.0 * px),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        header,
    )
    painter.setPen(QPen(QColor(33, 33, 33)))
    notes = (item.get("notes") or "").strip()
    if not notes:
        painter.setPen(QPen(QColor(150, 150, 150)))
        notes = "（这张幻灯片没有备注）"
    painter.drawText(
        QRectF(left, text_top + 9.0 * px, width, max(1.0, text_h - 9.0 * px)),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        | Qt.TextFlag.TextWordWrap,
        notes,
    )
    painter.restore()


def _paint_outline_page(painter, page, left, top, width, height, px):
    """大纲页：纯文字列表（序号 + 标题）。"""
    painter.save()
    font = QFont()
    font.setPointSizeF(13.0)
    painter.setFont(font)
    painter.setPen(QPen(QColor(33, 33, 33)))
    line_h = 10.0 * px
    y = top
    for line in page.get("outline_lines", []):
        painter.drawText(
            QRectF(left, y, 26.0 * px, line_h),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"{line['slide'] + 1}.",
        )
        painter.drawText(
            QRectF(left + 30.0 * px, y, max(1.0, width - 30.0 * px), line_h),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            str(line["title"]),
        )
        y += line_h
        if y > top + height:
            break
    painter.restore()


def _draw_footer(painter, page, left, y, width, px):
    painter.save()
    font = QFont()
    font.setPointSizeF(8.0)
    painter.setFont(font)
    painter.setPen(QPen(QColor(120, 120, 120)))
    painter.drawText(
        QRectF(left, y, width * 0.6, 6.0 * px),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        "蜜蜂办公 · 蜜演",
    )
    painter.drawText(
        QRectF(left + width * 0.6, y, width * 0.4, 6.0 * px),
        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        str(page.get("footer_right", "")),
    )
    painter.restore()


def _ask_print_options(parent):
    """
    询问打印模式与讲义张数。

    :return: (mode, per_page)；用户取消返回 (None, None)
    """
    from PySide6.QtWidgets import QInputDialog

    options = [
        f"{MODE_LABELS[MODE_SLIDES]}",
        f"{MODE_LABELS[MODE_HANDOUT]}：2 张",
        f"{MODE_LABELS[MODE_HANDOUT]}：3 张",
        f"{MODE_LABELS[MODE_HANDOUT]}：4 张",
        f"{MODE_LABELS[MODE_HANDOUT]}：6 张",
        f"{MODE_LABELS[MODE_HANDOUT]}：9 张",
        MODE_LABELS[MODE_NOTES],
        MODE_LABELS[MODE_OUTLINE],
    ]
    choice, ok = QInputDialog.getItem(
        parent, "打印内容", "选择打印方式：", options, 0, False
    )
    if not ok or not choice:
        return None, None
    if choice.startswith(MODE_LABELS[MODE_HANDOUT]):
        try:
            per_page = int(choice.rsplit("：", 1)[1].replace("张", "").strip())
        except (IndexError, ValueError):
            per_page = 4
        return MODE_HANDOUT, per_page
    if choice == MODE_LABELS[MODE_NOTES]:
        return MODE_NOTES, 1
    if choice == MODE_LABELS[MODE_OUTLINE]:
        return MODE_OUTLINE, 1
    return MODE_SLIDES, 1
