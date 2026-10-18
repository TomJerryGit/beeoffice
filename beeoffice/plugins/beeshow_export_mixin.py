# beeoffice/plugins/beeshow_export_mixin.py
"""
蜜演导出 Mixin

职责：
  - _export_pptx         : 导出 PPTX（任务 3.1：原生元素映射 + 任务 5.1 动态数字预处理）
  - _export_pptx_legacy  : PPTX 保底方案（BeautifulSoup 解析）
  - _export_pdf          : 导出 PDF（P0-4：保持 QWebEngineView 引用 +
                           任务 5.3 视频封面替换 + 任务 5.1 动态数字预处理）
  - _export_html         : 导出 HTML（任务 5.3 复制视频 + 任务 5.1 注入动态数字 JS）
  - _export_images       : 导出 PNG 图片序列（P0-4）
  - _export_gif          : 导出 GIF 动图（依赖 bee_export）
  - _record_presentation : 录制占位

v5.1 增量汇总：
  - 任务 3.1：_export_pptx 改用 PPTXEngine 做原生元素映射；
             保留 _export_pptx_legacy 作为保底
  - 任务 5.1：_export_pdf / _export_pptx 前处理动态数字；
             _export_html 注入动态数字 JS
  - 任务 5.3：_export_html 复制视频文件；
             _export_pdf 把视频替换为封面图

v5.1.1 修复：
  - QTimer 从 PySide6.QtWidgets 改为 PySide6.QtCore
    （QTimer 属于 QtCore，不在 QtWidgets；原 import 会抛 ImportError）

修复记录：
  - 补 `import logging`：
      原 beeshow.py 的 _export_images 里用了 logging.error 但未导入 logging，
      实际运行时若截图失败会抛 NameError。

依赖：
  - logging / pathlib.Path
  - PySide6.QtWidgets（QFileDialog / QMessageBox / QInputDialog）
  - PySide6.QtCore（QTimer）
  - PySide6.QtWebEngineWidgets（QWebEngineView）
  - beeshow_constants.SLIDE_THEMES
  - bee_export.export_slides_to_gif（延迟 import）
  - beeshow_pptx_engine.PPTXEngine（延迟 import，任务 3.1）

注意：
  - 不导入其他 beeshow_* Mixin，避免循环依赖
  - P0-4 关键修复：_export_views 保持 QWebEngineView 引用，避免被 GC
"""

import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog, QMessageBox, QInputDialog,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWebEngineWidgets import QWebEngineView

from beeoffice.plugins.beeshow_constants import SLIDE_THEMES
from beeoffice.i18n import tr


class ExportMixin:
    """蜜演导出 Mixin"""

    # ==================== 导出 PPTX（任务 3.1） ====================
    def _export_pptx(self):
        """
        导出为 PowerPoint（.pptx）。

        任务 3.1：改用 PPTXEngine 做原生元素映射。
        相比旧实现：
          - 文本保持原生可编辑、可搜索
          - 图片保持原生 Picture（可替换）
          - 表格保持原生 Table
          - 保留字号、颜色、加粗、对齐
          - 保留背景色 / 容器背景

        任务 5.1：导出前把 {{number:...}} 替换为最终值。

        降级：
          - 无 playwright 时，引擎自动降级为"仅文本"模式
            （不保真，但至少可编辑）
          - 引擎失败时，回退到旧的 BeautifulSoup 方案
        """
        if not self._slides_html:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, tr("auto.beeshow_export_mixin.851f94c5", "导出 PPTX"), tr("auto.beeshow_export_mixin.09a5be6b", "演示.pptx"), "PowerPoint (*.pptx)"
        )
        if not path:
            return

        theme = SLIDE_THEMES[self._current_theme]
        bg = self._custom_bg or theme.get("bg", "#FFF")

        # 背景色可能是渐变（linear-gradient(...)），提取纯色作为兜底
        if "gradient" in bg or "linear" in bg:
            bg_solid = "#FFFFFF"
        else:
            bg_solid = bg

        try:
            from beeoffice.plugins.beeshow_pptx_engine import PPTXEngine

            self._set_status(tr("auto.beeshow_export_mixin.d62eaf8a", "📄 正在导出 PPTX..."), 0)

            # 任务 5.1：导出 PPTX 时把动态数字替换为最终值
            export_slides = []
            for s in self._slides_html:
                try:
                    s = self._render_dynamic_numbers_for_export(s)
                except AttributeError:
                    pass
                export_slides.append(s)

            engine = PPTXEngine(slide_width=10.0, slide_height=7.5)
            success = engine.export(
                slides_html=export_slides,
                output_path=path,
                theme_css=theme["css"],
                bg_color=bg_solid,
            )

            if success:
                QMessageBox.information(
                    self, tr("auto.beeshow_export_mixin.c893536c", "导出成功"),
                    tr("auto.beeshow_export_mixin.88cd08b2", "已保存: {path}\n\n✅ 文本可编辑、可搜索\n✅ 保留字号/颜色/对齐").format(path=path)
                )
                self._set_status(tr("auto.beeshow_export_mixin.029fa78e", "✅ PPTX 导出完成"), 3000)
            else:
                QMessageBox.warning(
                    self, tr("auto.beeshow_export_mixin.67533812", "导出失败"),
                    tr("auto.beeshow_export_mixin.bc67aae1", "PPTX 引擎返回失败，尝试旧方案...")
                )
                self._export_pptx_legacy(path)

        except ImportError as e:
            logging.error(f"PPTX 引擎导入失败：{e}")
            QMessageBox.warning(
                self, tr("auto.beeshow_export_mixin.1f393593", "缺少依赖"),
                tr("auto.beeshow_export_mixin.eeb35820", "PPTX 引擎不可用：\n{e}\n\n请确认 python-pptx 已安装。\n如需精确版式，请安装 playwright：\npip install playwright && playwright install chromium").format(e=e)
            )
            self._export_pptx_legacy(path)

        except Exception as e:
            logging.error(f"PPTX 导出失败：{e}")
            QMessageBox.warning(
                self, tr("auto.beeshow_export_mixin.67533812", "导出失败"), tr("auto.beeshow_export_mixin.08588f22", "出错：{e}\n\n尝试旧方案...").format(e=e)
            )
            self._export_pptx_legacy(path)

    def _export_pptx_legacy(self, path: str):
        """
        旧的 PPTX 导出方案（保底）。

        - 基于 BeautifulSoup 解析 HTML
        - 提取标题和正文到占位符
        - 不保真，但依赖最少
        """
        try:
            from pptx import Presentation
            from pptx.util import Inches
            from bs4 import BeautifulSoup

            prs = Presentation()
            prs.slide_width = Inches(10)
            prs.slide_height = Inches(7.5)

            for slide_html in self._slides_html:
                soup = BeautifulSoup(slide_html, 'html.parser')
                title_tag = soup.find(['h1', 'h2', 'h3'])
                title_text = (
                    title_tag.get_text().strip() if title_tag else ""
                )
                slide = prs.slides.add_slide(
                    prs.slide_layouts[1] if title_text
                    else prs.slide_layouts[0]
                )
                if title_text and slide.shapes.title:
                    slide.shapes.title.text = title_text

                content = []
                for elem in soup.find_all(['p', 'li']):
                    t = elem.get_text().strip()
                    if t and t != title_text:
                        prefix = '• ' if elem.name == 'li' else ''
                        content.append(f"{prefix}{t}")

                if content and len(slide.placeholders) > 1:
                    slide.placeholders[1].text = "\n".join(content)

            prs.save(path)
            return True
        except Exception as e:
            logging.error(f"PPTX 遗留导出失败: {e}")
            return False
            QMessageBox.information(
                self, tr("auto.beeshow_export_mixin.8af82fcd", "导出成功（保底方案）"),
                tr("auto.beeshow_export_mixin.4221e686", "已保存: {path}\n\n⚠️ 使用了保底方案，版式可能不精确。").format(path=path)
            )
        except Exception as e:
            logging.error(f"保底方案也失败：{e}")
            QMessageBox.warning(self, tr("auto.beeshow_export_mixin.67533812", "导出失败"), str(e))

    # ==================== 导出 PDF（P0-4 + 任务 5.3 + 任务 5.1） ====================
    def _export_pdf(self):
        """
        导出 PDF（P0-4：保持 QWebEngineView 引用，避免被 GC）。

        任务 5.3：视频替换为封面图。
        任务 5.1：动态数字替换为最终值。

        流程：
          1. 拼接所有幻灯片为一份 HTML
          2. 创建临时 QWebEngineView（加入 self._export_views）
          3. loadFinished 后调 printToPdf
          4. 完成后清理引用

        关键：
          - 先 connect 再 setHtml，避免时序问题
          - 在 loadFinished 回调里做清理，避免提前 GC
        """
        if not self._slides_html:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, tr("auto.beeshow_export_mixin.d58b0502", "导出 PDF"), tr("auto.beeshow_export_mixin.174251a5", "演示.pdf"), "PDF (*.pdf)"
        )
        if not path:
            return

        theme = SLIDE_THEMES[self._current_theme]
        bg = self._custom_bg or theme.get("bg", "#FFF")

        # 任务 5.3：视频替换为封面图
        slides_for_export = list(self._slides_html)
        try:
            slides_for_export = self._replace_videos_with_posters(
                slides_for_export
            )
        except AttributeError:
            pass

        parts = []
        for i, s in enumerate(slides_for_export):
            # 任务 5.1：动态数字替换为最终值
            try:
                s = self._render_dynamic_numbers_for_export(s)
            except AttributeError:
                pass

            pb = (
                '<div style="page-break-after:always"></div>'
                if i < len(slides_for_export) - 1 else ''
            )
            parts.append(
                f"<div class='slide' style='width:100%;min-height:100vh;"
                f"display:flex;flex-direction:column;"
                f"justify-content:center;align-items:center;"
                f"padding:60px;box-sizing:border-box'>{s}</div>{pb}"
            )
        slides_html = "".join(parts)

        # 任务 2.1：拼入版式 CSS
        full_html = (
            f"""<!DOCTYPE html><html><head><meta charset="utf-8">"""
            f"""<style>{theme['css']}{self._get_layout_css()}"""
            f"""body{{background:{bg};}}"""
            f"""@page{{size:A4 landscape;margin:0}}body{{margin:0}}"""
            f"""</style></head><body>{slides_html}</body></html>"""
        )

        # P0-4：保持 QWebEngineView 引用，避免被 GC
        temp = QWebEngineView()
        self._export_views.append(temp)

        def _cleanup_view():
            if temp in self._export_views:
                self._export_views.remove(temp)
            temp.deleteLater()

        def on_pdf_finished(file_path, success):
            """
            printToPdf 是异步的：必须等这个信号才算真的写完。

            原实现在 printToPdf 之后立刻弹"导出成功"并 deleteLater，
            等于在文件还没落盘时就宣布成功、并把正在打印的页面销毁。
            """
            try:
                if success:
                    QMessageBox.information(
                        self, tr("auto.beeshow_export_mixin.c893536c", "导出成功"), tr("auto.beeshow_export_mixin.99bc3d5d", "已保存: {file_path}").format(file_path=file_path)
                    )
                else:
                    QMessageBox.warning(
                        self, tr("auto.beeshow_export_mixin.67533812", "导出失败"),
                        tr("auto.beeshow_export_mixin.0d838d37", "PDF 写入失败（磁盘空间不足或无写权限？）")
                    )
            finally:
                _cleanup_view()

        def on_load(ok):
            if not ok:
                QMessageBox.warning(self, tr("auto.beeshow_export_mixin.67533812", "导出失败"), tr("auto.beeshow_export_mixin.363f3966", "页面渲染失败"))
                _cleanup_view()
                return
            # 先接完成信号再发起导出，避免竞态
            temp.page().pdfPrintingFinished.connect(on_pdf_finished)
            temp.page().printToPdf(path)

        # P0-4：先 connect 再 setHtml，避免时序问题
        temp.page().loadFinished.connect(on_load)
        temp.setHtml(full_html)

    # ==================== 导出 HTML（任务 5.3 + 任务 5.1） ====================
    def _export_html(self):
        """
        导出为单文件 HTML。

        任务 5.3：若含视频，自动复制到输出目录的 media/ 子目录。
        任务 5.1：注入动态数字 JS（HTML 里 JS 会执行，保留动画）。

        每张幻灯片作为 <div class='slide'>，通过 CSS 全屏显示。
        直接写文件，无需 QWebEngineView。
        """
        if not self._slides_html:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, tr("auto.beeshow_export_mixin.f9dc03e0", "导出 HTML"), tr("auto.beeshow_export_mixin.0a902a6c", "演示.html"), "HTML (*.html)"
        )
        if not path:
            return

        theme = SLIDE_THEMES[self._current_theme]
        bg = self._custom_bg or theme.get("bg", "#FFF")

        # 任务 5.3：复制视频文件
        slides_html = list(self._slides_html)
        try:
            output_dir = Path(path).parent
            slides_html = self._copy_videos_for_html_export(
                output_dir, slides_html
            )
        except AttributeError:
            pass

        # 构造 HTML 片段
        parts = []
        for s in slides_html:
            parts.append(
                f"<div class='slide' style='width:100%;min-height:100vh;"
                f"display:flex;flex-direction:column;"
                f"justify-content:center;align-items:center;"
                f"padding:60px;box-sizing:border-box'>{s}</div>"
            )
        slides_html_joined = "\n".join(parts)

        # 任务 5.1：动态数字 JS
        dynamic_js = ""
        try:
            dynamic_js = self._get_dynamic_number_js()
        except AttributeError:
            pass

        # 任务 2.1：拼入版式 CSS
        full_html = (
            f"""<!DOCTYPE html><html><head><meta charset="utf-8">"""
            f"""<style>{theme['css']}{self._get_layout_css()}"""
            f"""body{{background:{bg};}}body{{margin:0}}</style>"""
            f"""</head><body>{slides_html_joined}{dynamic_js}</body></html>"""
        )

        with open(path, 'w', encoding='utf-8') as f:
            f.write(full_html)

        QMessageBox.information(self, tr("auto.beeshow_export_mixin.c893536c", "导出成功"), tr("auto.beeshow_export_mixin.16411a46", "已保存: {path}").format(path=path))

    # ==================== 导出图片序列（P0-4） ====================
    def _export_images(self):
        """
        导出 PNG 图片序列（P0-4：保持 QWebEngineView 引用，避免被 GC）。

        为每张幻灯片创建一个独立的 QWebEngineView：
          - 加入 self._export_views 列表保持引用
          - loadFinished 后调 page.grab().save(...)
          - 完成后从列表移除并 deleteLater

        修复：
          - 原文件用了 logging.error 但未 import logging；
            现在顶部补上 import logging。
        """
        if not self._slides_html:
            return

        output_dir = QFileDialog.getExistingDirectory(
            self, tr("auto.beeshow_export_mixin.98488765", "选择输出文件夹")
        )
        if not output_dir:
            return

        theme = SLIDE_THEMES[self._current_theme]
        bg = self._custom_bg or theme.get("bg", "#FFF")
        total = len(self._slides_html)

        # 统计成功/失败：原来无论截到几张都报"导出成功"
        results = {"ok": 0, "fail": 0}

        def report():
            if results["ok"] + results["fail"] < total:
                return
            if results["fail"] == 0:
                QMessageBox.information(
                    self, tr("auto.beeshow_export_mixin.c893536c", "导出成功"),
                    tr("auto.beeshow_export_mixin.54c90c57", "已保存 {0} 张图片到:\n{1}").format(results['ok'], output_dir)
                )
            else:
                QMessageBox.warning(
                    self, tr("auto.beeshow_export_mixin.7912043e", "部分失败"),
                    tr("auto.beeshow_export_mixin.b8294b84", "成功 {0} 张，失败 {1} 张。\n目录: {2}").format(results['ok'], results['fail'], output_dir)
                )

        for i, s in enumerate(self._slides_html):
            # 任务 2.1：拼入版式 CSS
            full_html = (
                f"""<!DOCTYPE html><html><head><meta charset="utf-8">"""
                f"""<style>{theme['css']}{self._get_layout_css()}"""
                f"""body{{background:{bg};}}"""
                f"""</style></head>"""
                f"""<body><div class="slide">{s}</div></body></html>"""
            )

            # P0-4：保持引用，避免每次循环覆盖导致 GC
            temp = QWebEngineView()
            # 离屏渲染：不弹窗，但保证首帧确实被绘制，grab() 才有内容
            temp.setAttribute(Qt.WA_DontShowOnScreen, True)
            self._export_views.append(temp)
            temp.resize(1024, 768)
            temp.show()

            def capture(view, idx=i, out=output_dir):
                """
                截图并保存。

                修复：原实现调用 page.grab() —— QWebEnginePage 没有这个方法
                （grab 属于 QWebEngineView），异常被 except 吞掉后仍报"成功"。
                """
                try:
                    pixmap = view.grab()
                    target = Path(out) / f"slide_{idx+1:03d}.png"
                    if pixmap.isNull() or not pixmap.save(str(target)):
                        results["fail"] += 1
                        logging.error(f"截图失败 slide {idx+1}")
                    else:
                        results["ok"] += 1
                except Exception as e:
                    results["fail"] += 1
                    logging.error(f"截图异常 slide {idx+1}: {e}")
                finally:
                    if view in self._export_views:
                        self._export_views.remove(view)
                    view.deleteLater()
                    report()

            def on_loaded(ok, view, idx):
                if not ok:
                    capture(view, idx)
                    return
                # loadFinished 只表示文档加载完，首帧可能还没绘制。
                # 300ms 在满负载（或慢机器）上会截到空白帧，
                # 实测全量测试压力下就会偶发，因此放宽到 800ms。
                QTimer.singleShot(800, lambda: capture(view, idx))

            temp.page().loadFinished.connect(
                lambda ok, t=temp, idx=i: on_loaded(ok, t, idx)
            )
            temp.setHtml(full_html)

        # 说明：原实现在此处用 QTimer.singleShot(3000) 弹一个模态"导出中"，
        # 会在导出已经开始后才抢焦点、并阻塞事件循环，反而影响截图。
        # 已移除——进度应走状态栏，而不是延迟弹出的模态框。

    # ==================== 导出 GIF ====================
    def _export_gif(self):
        """
        导出为 GIF 动图。

        依赖 bee_export.export_slides_to_gif（延迟 import）。
        用户可选每帧停留时长（默认 2000ms，范围 500~10000ms）。
        """
        if not self._slides_html:
            QMessageBox.information(self, tr("auto.beeshow_export_mixin.ab3656a9", "提示"), tr("auto.beeshow_export_mixin.63565334", "请先编写幻灯片内容"))
            return

        path, _ = QFileDialog.getSaveFileName(
            self, tr("auto.beeshow_export_mixin.b545b506", "导出 GIF"), tr("auto.beeshow_export_mixin.b25d8f56", "演示.gif"), tr("auto.beeshow_export_mixin.6d000c73", "GIF 动图 (*.gif)")
        )
        if not path:
            return

        theme = SLIDE_THEMES[self._current_theme]

        from beeoffice.plugins.bee_export import export_slides_to_gif

        duration, ok = QInputDialog.getInt(
            self, "GIF 设置", "每页停留时间（毫秒）:",
            2000, 500, 10000, 500
        )

        if ok and export_slides_to_gif(
            self._slides_html, path, theme['css'], duration
        ):
            QMessageBox.information(
                self, tr("auto.beeshow_export_mixin.c893536c", "导出成功"), tr("auto.beeshow_export_mixin.6e013b3e", "GIF 已保存至：\n{path}").format(path=path)
            )
        else:
            QMessageBox.warning(self, tr("auto.beeshow_export_mixin.67533812", "导出失败"), tr("auto.beeshow_export_mixin.35f4a209", "GIF 导出失败"))

    # ==================== 录制（占位） ====================
    def _record_presentation(self):
        """
        录制功能占位。

        真正的录制需要：
          - 屏幕捕获库（如 mss / pyautogui）
          - 音视频编码库（如 ffmpeg / moviepy）
          - 与全屏播放窗口的切换时机同步
        当前先以提示代替。
        """
        QMessageBox.information(
            self,
            tr("auto.beeshow_export_mixin.fe3e8e19", "录制"),
            tr("auto.beeshow_export_mixin.7ae18b2e", "录制功能需要在全屏播放时自动记录幻灯片切换时间戳。\n"
            "按 F5 开始播放即可自动记录。")
        )