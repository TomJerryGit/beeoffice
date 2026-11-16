# beeoffice/plugins/pdf_annotator.py
"""
PDF 批注工具

v5.0.1 修复（P1-14）：
  - _undo_annotation 从"只删最后一个"改为"删当前页最后一个"
    原实现 `self._annotations.pop()` 不看页码，用户在第 3 页点撤销
    会误删第 5 页最后一条批注。现在倒序找当前页的批注删除，
    当前页无批注时提示而非误删他页。

v5.0.5 数据保全修复（优化规划 §1.8）：
  1. 本类原本**没有 closeEvent** —— 关窗即静默丢弃未「保存批注/烧录」的批注。
     现在关闭前询问，支持「保存 / 放弃 / 取消」。
  2. open_pdf 把「打开 PDF」与「读取旁挂文件」放在同一个 try 里，且
     Annotation.from_dict 用 data["page"]/data["color"] 直接下标：旁挂文件里
     只要有一条缺字段，用户就会看到「打开失败: 'color'」，并且**已经读到的
     批注全部丢失**。现在两步分离，坏条目逐条跳过并明确告知。
  3. _save_annotations 直接 open(...,'w') 且无异常保护：目标目录不可写时异常
     冲出槽函数、用户毫无提示，还可能留下被截断的文件。现在走原子写 + 明确
     的错误提示。
  4. _burn_annotations 完全不传颜色，烧出来永远是库默认色（高亮黄/下划线红），
     用户在 UI 里选的颜色只存在于屏幕叠加层。现在调用 set_colors()。
"""
import logging
import tempfile
import json
from pathlib import Path
from datetime import datetime

from beeoffice.pdf_backend import get_backend

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
                                QListWidget, QListWidgetItem, QTextEdit, QFileDialog,
                                QMessageBox, QSplitter, QDialog, QDialogButtonBox,
                                QGraphicsView, QGraphicsScene, QColorDialog, QInputDialog, QLineEdit)
from PySide6.QtCore import Qt, QRectF, Signal, QPointF, QSize
from PySide6.QtGui import (QPixmap, QPainter, QColor, QPen, QFont, QPolygonF, QIcon)

from beeoffice.utils import atomic_write_json


from beeoffice.plugins.ribbon_widget import RibbonBar


class AnnoRect:
    """轻量矩形（替代 fitz.Rect），坐标为 PDF 点、左上原点。"""

    def __init__(self, *args):
        if len(args) == 1 and not isinstance(args[0], (int, float)):
            args = tuple(args[0])
        self.x0, self.y0, self.x1, self.y1 = [float(v) for v in args]
        if self.x1 < self.x0:
            self.x0, self.x1 = self.x1, self.x0
        if self.y1 < self.y0:
            self.y0, self.y1 = self.y1, self.y0

    @property
    def width(self):
        return self.x1 - self.x0

    @property
    def height(self):
        return self.y1 - self.y0

    @property
    def is_empty(self):
        return self.width <= 0 or self.height <= 0

    def __mul__(self, scale):
        return AnnoRect(self.x0 * scale, self.y0 * scale,
                        self.x1 * scale, self.y1 * scale)


class Annotation:
    #: .beeanno 旁挂文件格式版本（新写入的文件带此字段；旧文件是裸列表，仍可读）
    FORMAT_VERSION = 1

    def __init__(self, page, rect, anno_type="highlight", text="", color=(1,1,0), width=2):
        if not isinstance(rect, AnnoRect):
            rect = AnnoRect(rect.x0, rect.y0, rect.x1, rect.y1) \
                if hasattr(rect, "x0") else AnnoRect(rect)
        self.page=page; self.rect=rect; self.type=anno_type; self.text=text; self.color=color
        self.width=int(width)
        self.created=datetime.now().isoformat()
    def to_dict(self): return {"page":self.page,"rect":[self.rect.x0,self.rect.y0,self.rect.x1,self.rect.y1],"type":self.type,"text":self.text,"color":list(self.color),"width":self.width,"created":self.created}

    @classmethod
    def from_dict(cls, data):
        """
        从字典恢复一条批注。

        优化规划 §1.8：原实现是
            cls(data["page"], fitz.Rect(data["rect"]), data["type"],
                data["text"], data["color"])
        缺任一键即抛 KeyError，进而让整份旁挂文件都读不出来。
        现在所有字段都有默认值：坏条目自身可能退化成默认值，但不会拖垮其它批注。
        """
        if not isinstance(data, dict):
            raise ValueError(f"批注条目不是字典: {type(data).__name__}")

        rect = data.get("rect") or [0, 0, 0, 0]
        try:
            rect_obj = AnnoRect(rect)
        except Exception:
            rect_obj = AnnoRect(0, 0, 0, 0)

        color = data.get("color") or (1, 1, 0)
        try:
            color = tuple(float(c) for c in color)
            if len(color) != 3:
                color = (1, 1, 0)
        except Exception:
            color = (1, 1, 0)

        anno = cls(
            int(data.get("page", 0)),
            rect_obj,
            data.get("type", "highlight"),
            data.get("text", "") or "",
            color,
            data.get("width", 2) or 2,
        )
        if data.get("created"):
            anno.created = data["created"]
        return anno


class PDFPageView(QGraphicsView):
    annotation_added = Signal(Annotation)
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene=QGraphicsScene(self); self.setScene(self._scene)
        self._page=None; self._annotations=[]; self._current_tool="highlight"; self._current_color=(1,0.8,0)
        self._rubberband_start=None; self._scale=1.0
        self._annotations_visible=True; self._all_annotations=[]
        self.setRenderHint(QPainter.SmoothPixmapTransform)
    def set_page(self, page, annotations, src=None, backend=None):
        self._page=page; self._src=src; self._backend=backend
        self._all_annotations=list(annotations)
        self._annotations=[a for a in annotations if a.page==page]; self._render_page()
    def _render_page(self):
        if self._page is None or not self._src or self._backend is None:
            return
        tmp = None
        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.close()
            self._backend.render_page_png(
                self._src, self._page + 1, tmp.name, scale=self._scale
            )
            pixmap = QPixmap(tmp.name)
            self._scene.clear(); self._scene.addPixmap(pixmap)
        finally:
            if tmp:
                Path(tmp.name).unlink(missing_ok=True)
        if not self._annotations_visible:
            return
        for a in self._annotations:
            r=a.rect*self._scale; c=QColor(int(a.color[0]*255),int(a.color[1]*255),int(a.color[2]*255),80)
            lw = max(1, int(getattr(a, 'width', 2)))
            if a.type=="highlight": self._scene.addRect(r.x0,r.y0,r.width,r.height,QPen(Qt.NoPen),c)
            elif a.type=="underline": self._scene.addLine(r.x0,r.y1,r.x1,r.y1,QPen(c,lw))
            elif a.type=="strikethrough": self._scene.addLine(r.x0,(r.y0+r.y1)/2,r.x1,(r.y0+r.y1)/2,QPen(c,lw))
            elif a.type=="text": self._scene.addText("💬",QFont("Segoe UI Emoji",12)).setPos(r.x0-8,r.y0-12)
            elif a.type=="textbox":
                self._scene.addRect(r.x0,r.y0,r.width,r.height,QPen(c,1),QColor(255,255,255,30))
                item=self._scene.addText(a.text or "文本",QFont("Microsoft YaHei",10))
                item.setDefaultTextColor(c); item.setPos(r.x0+3,r.y0+2)
            elif a.type=="signature":
                item=self._scene.addText(a.text or "签名",QFont("KaiTi",16,QFont.StyleItalic))
                item.setDefaultTextColor(c); item.setPos(r.x0,r.y0)
            elif a.type=="rectangle":
                self._scene.addRect(r.x0,r.y0,r.width,r.height,QPen(c,2),QColor(0,0,0,0))
            elif a.type=="circle":
                self._scene.addEllipse(r.x0,r.y0,r.width,r.height,QPen(c,2),QColor(0,0,0,0))
            elif a.type=="line":
                self._scene.addLine(r.x0,r.y0,r.x1,r.y1,QPen(c,lw))
            elif a.type=="arrow":
                self._scene.addLine(r.x0,r.y0,r.x1,r.y1,QPen(c,lw))
                dx,dy=r.x1-r.x0,r.y1-r.y0
                ln=(dx*dx+dy*dy)**0.5 or 1
                ux,uy=dx/ln,dy/ln
                size=8
                p1=QPointF(r.x1-size*ux+size*0.5*uy, r.y1-size*uy-size*0.5*ux)
                p2=QPointF(r.x1-size*ux-size*0.5*uy, r.y1-size*uy+size*0.5*ux)
                self._scene.addPolygon(QPolygonF([QPointF(r.x1,r.y1),p1,p2]),QPen(c),c)
    def wheelEvent(self, event):
        f=1.15 if event.angleDelta().y()>0 else 1/1.15
        # 优化规划 §1.8：原实现没有上下限，长按滚轮可放大到 1.15^n
        # （n≈20 即 16 倍，约 128 Mpx × 3B ≈ 385 MB 位图）而崩溃。
        self._scale=max(0.2, min(self._scale*f, 8.0))
        self._render_page()
    def mousePressEvent(self, event):
        if event.button()==Qt.LeftButton: self._rubberband_start=self.mapToScene(event.position().toPoint())
        else: super().mousePressEvent(event)
    def mouseMoveEvent(self, event):
        if self._rubberband_start:
            r=QRectF(self._rubberband_start, self.mapToScene(event.position().toPoint()))
            self._render_page(); self._scene.addRect(r, QPen(QColor("#FFB300")), QColor(255,200,0,40))
        else: super().mouseMoveEvent(event)
    def mouseReleaseEvent(self, event):
        if self._rubberband_start:
            ep=self.mapToScene(event.position().toPoint())
            sp=QPointF(self._rubberband_start.x()/self._scale, self._rubberband_start.y()/self._scale)
            ep2=QPointF(ep.x()/self._scale, ep.y()/self._scale)
            rect=AnnoRect(sp.x(),sp.y(),ep2.x(),ep2.y())
            if not rect.is_empty and self._page is not None:
                self.annotation_added.emit(Annotation(self._page.number,rect,self._current_tool,color=self._current_color,width=getattr(self,'_current_width',2)))
            self._rubberband_start=None; self._render_page()
        else: super().mouseReleaseEvent(event)
    def set_tool(self,t): self._current_tool=t
    def set_current_color(self,c): self._current_color=c
    def set_current_width(self,w): self._current_width=max(1,int(w))
    def set_annotations_visible(self,v): self._annotations_visible=bool(v); self._render_page()


class PDFAnnotator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🐝 PDF 批注"); self.resize(1100,750)
        self._doc=None; self._filepath=None; self._annotations=[]; self._current_page=0
        self._page_count=0; self._backend=get_backend()
        self._current_color=(1,0.8,0)
        self._current_width=2
        self._redo_stack=[]
        # 优化规划 §1.8：用于 closeEvent 判断是否存在未落盘的批注
        self._dirty_annotations=False
        layout=QVBoxLayout(self)
        # WPS 式 Ribbon：开始（页面/文件）/ 标注 / 操作
        self._ribbon = RibbonBar()
        page_home = self._ribbon.add_tab("开始")
        page_group = self._ribbon.add_group(page_home, "页面")
        self._page_label = QLabel("第 1/1 页")
        page_group.add_widget(self._page_label)
        page_group.add_small_button("上一页", "上一页", self._prev_page, icon_name="prev")
        page_group.add_small_button("下一页", "下一页", self._next_page, icon_name="next")
        file_group = self._ribbon.add_group(page_home, "文件")
        file_group.add_small_button("保存批注", "保存批注", self._save_annotations, icon_name="save")
        file_group.add_small_button("烧录", "烧录", self._burn_annotations, icon_name="burn")
        file_group.add_small_button("撤销", "撤销", self._undo_annotation, icon_name="undo")

        page_anno = self._ribbon.add_tab("标注")
        anno_group = self._ribbon.add_group(page_anno, "标注工具")
        for label, tool, icon_name in (
            ("高亮", "highlight", "highlight"),
            ("下划线", "underline", "underline"),
            ("删除线", "strikethrough", "strike"),
            ("批注", "text", "comment"),
            ("文本框", "textbox", "textbox"),
            ("箭头", "arrow", "arrow"),
            ("签名", "signature", "signature"),
            ("矩形", "rectangle", "rectangle"),
            ("圆形", "circle", "circle"),
            ("直线", "line", "line"),
        ):
            def _select(checked=False, tt=tool):
                self._set_tool(tt)
            btn = anno_group.add_large_button(label, label, _select, icon_name=icon_name)
            btn.setCheckable(True)
        color_group = self._ribbon.add_group(page_anno, "颜色")
        color_group.add_small_button("选择颜色", "选择颜色", self._choose_color, icon_name="color")
        from PySide6.QtWidgets import QSpinBox
        width_spin = QSpinBox()
        width_spin.setRange(1, 12)
        width_spin.setValue(2)
        width_spin.setPrefix("线宽 ")
        width_spin.valueChanged.connect(self._set_current_width)
        color_group.add_widget(width_spin)
        manage_group = self._ribbon.add_group(page_anno, "管理")
        manage_group.add_small_button("撤销", "撤销", self._undo_annotation, icon_name="undo")
        manage_group.add_small_button("重做", "重做", self._redo_annotation, icon_name="redo")
        manage_group.add_small_button("显示/隐藏", "显示/隐藏", self._toggle_annotations_visible, icon_name="view")
        manage_group.add_small_button("导出批注", "导出批注", self._export_annotations, icon_name="export")
        manage_group.add_small_button("导入批注", "导入批注", self._import_annotations, icon_name="import")

        page_page = self._ribbon.add_tab("页面")
        nav_group = self._ribbon.add_group(page_page, "导航")
        nav_group.add_small_button("上一页", "上一页", self._prev_page, icon_name="prev")
        nav_group.add_small_button("下一页", "下一页", self._next_page, icon_name="next")
        nav_group.add_small_button("连续阅读", "连续阅读", self._toggle_continuous, icon_name="view")
        op_group = self._ribbon.add_group(page_page, "页面管理")
        op_group.add_small_button("页面管理", "页面管理", self._open_page_manager, icon_name="page")
        op_group.add_small_button("页面工具", "页面工具", self._open_toolbox, icon_name="command")
        op_group.add_small_button("旋转", "旋转", self._rotate_current, icon_name="view")

        protect_page = self._ribbon.add_tab("保护")
        protect_group = self._ribbon.add_group(protect_page, "保护")
        protect_group.add_small_button("加密/权限", "加密/权限", self._encrypt_pdf_dialog, icon_name="save")
        protect_group.add_small_button("水印", "水印", self._watermark_dialog, icon_name="page")

        convert_page = self._ribbon.add_tab("转换")
        convert_group = self._ribbon.add_group(convert_page, "转换")
        convert_group.add_small_button("PDF→图片", "PDF→图片", self._pdf_to_images_dialog, icon_name="image")
        convert_group.add_small_button("PDF→TXT", "PDF→TXT", self._pdf_to_text_dialog, icon_name="export")
        convert_group.add_small_button("图片→PDF", "图片→PDF", self._images_to_pdf_dialog, icon_name="page")
        convert_group.add_small_button("PDF工具箱", "PDF工具箱", self._open_toolbox, icon_name="command")

        layout.addWidget(self._ribbon)
        splitter=QSplitter(Qt.Horizontal)
        left=QWidget(); ll=QVBoxLayout(left); ll.addWidget(QLabel("页面"))
        self._thumb_list=QListWidget(); self._thumb_list.setIconSize(QSize(96,128))
        self._thumb_list.currentRowChanged.connect(self._goto_thumb_page)
        ll.addWidget(self._thumb_list)
        splitter.addWidget(left)
        self._page_view=PDFPageView(); self._page_view.annotation_added.connect(self._on_annotation_added); splitter.addWidget(self._page_view)
        right=QWidget(); rl=QVBoxLayout(right); rl.addWidget(QLabel("批注列表"))
        self._anno_list=QListWidget(); rl.addWidget(self._anno_list)
        splitter.addWidget(right); splitter.setSizes([150,750,300]); layout.addWidget(splitter)

    # ==================== 打开 ====================
    def open_pdf(self, filepath):
        """
        打开 PDF 及其旁挂批注。

        优化规划 §1.8：原实现把「fitz.open」与「读取 .beeanno」放在同一个
        try 里，任何一个旁挂文件解析问题都会让用户看到「打开失败」，
        并且已经读到的批注被整体丢弃。现在两步分离，互不牵连。
        """
        # 第一步：打开 PDF —— 这一步失败才是真正的"打不开"
        try:
            self._page_count = self._backend.page_count(filepath)
            self._doc = filepath
        except Exception as e:
            logging.error(f"打开 PDF 失败: {e}")
            QMessageBox.warning(self, "打开失败", f"无法打开 PDF：{e}")
            return

        self._filepath = filepath
        self._annotations = []
        self._current_page = 0
        self._dirty_annotations = False

        # 第二步：读取旁挂批注 —— 失败只影响批注，不影响文档本身
        anno_path = Path(filepath).with_suffix(".beeanno")
        if anno_path.exists():
            self._load_annotations(anno_path)

        self._update_view()
        self._load_thumbnails()

    def _set_status(self, text, timeout=0):
        """轻量状态提示（PDF 面板无状态栏）。"""
        try:
            self.setWindowTitle(f"🐝 PDF 批注 — {text}")
        except Exception:
            pass

    def _load_thumbnails(self):
        self._thumb_list.clear()
        if not self._doc:
            return
        import tempfile, os
        for i in range(self._page_count):
            try:
                fd, tmp = tempfile.mkstemp(suffix=".png")
                os.close(fd)
                self._backend.render_page_png(self._doc, i, tmp, scale=0.25)
                pm = QPixmap(tmp)
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                item = QListWidgetItem(QIcon(pm), f"第 {i + 1} 页")
                item.setData(Qt.UserRole, i)
                self._thumb_list.addItem(item)
            except Exception:
                self._thumb_list.addItem(QListWidgetItem(f"第 {i + 1} 页"))
        if self._page_count:
            self._thumb_list.setCurrentRow(0)

    def _goto_thumb_page(self, row):
        if row < 0 or row >= self._page_count:
            return
        if row != self._current_page:
            self._current_page = row
            self._update_view()

    def _encrypt_pdf_dialog(self):
        if not self._doc:
            QMessageBox.information(self, "加密", "请先打开 PDF。")
            return
        pwd, ok = QInputDialog.getText(self, "加密 PDF", "打开密码：", QLineEdit.Password)
        if not ok or not pwd:
            return
        out, _ = QFileDialog.getSaveFileName(self, "保存加密 PDF", "", "PDF (*.pdf)")
        if not out:
            return
        try:
            from beeoffice.pdf_tools import encrypt_pdf
            encrypt_pdf(self._filepath, out, pwd)
            QMessageBox.information(self, "加密完成", f"已保存：\n{out}")
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "加密失败", str(e))

    def _watermark_dialog(self):
        if not self._doc:
            QMessageBox.information(self, "水印", "请先打开 PDF。")
            return
        text, ok = QInputDialog.getText(self, "添加水印", "水印文字：")
        if not ok or not text:
            return
        out, _ = QFileDialog.getSaveFileName(self, "保存水印 PDF", "", "PDF (*.pdf)")
        if not out:
            return
        try:
            from beeoffice.pdf_tools import add_watermark
            add_watermark(self._filepath, out, text)
            QMessageBox.information(self, "水印完成", f"已保存：\n{out}")
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "水印失败", str(e))

    def _pdf_to_images_dialog(self):
        if not self._doc:
            QMessageBox.information(self, "PDF→图片", "请先打开 PDF。")
            return
        outdir = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if not outdir:
            return
        try:
            from beeoffice.pdf_tools import pdf_to_images
            info = pdf_to_images(self._doc, outdir)
            QMessageBox.information(self, "转换完成",
                                    f"已输出 {info['count']} 张图片：\n{outdir}")
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "转换失败", str(e))

    def _pdf_to_text_dialog(self):
        if not self._doc:
            QMessageBox.information(self, "PDF→TXT", "请先打开 PDF。")
            return
        out, _ = QFileDialog.getSaveFileName(self, "导出文本", "", "文本 (*.txt)")
        if not out:
            return
        try:
            from beeoffice.pdf_tools import pdf_to_text
            pdf_to_text(self._doc, out)
            QMessageBox.information(self, "转换完成", f"已保存：\n{out}")
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "转换失败", str(e))

    def _images_to_pdf_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择图片", "", "图片 (*.png *.jpg *.jpeg *.bmp)"
        )
        if not files:
            return
        out, _ = QFileDialog.getSaveFileName(self, "保存 PDF", "", "PDF (*.pdf)")
        if not out:
            return
        try:
            from beeoffice.pdf_tools import images_to_pdf
            info = images_to_pdf(files, out)
            QMessageBox.information(self, "转换完成",
                                    f"已合成 {info['count']} 页：\n{out}")
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "转换失败", str(e))

    def _toggle_continuous(self):
        self._continuous = not getattr(self, "_continuous", False)
        try:
            self._page_view.setDragMode(
                QGraphicsView.ScrollHandDrag if self._continuous
                else QGraphicsView.RubberBandDrag
            )
        except Exception:
            pass
        self._set_status("连续阅读模式" if self._continuous else "单页模式", 2000)

    def _open_page_manager(self):
        if not self._doc:
            QMessageBox.information(self, "页面管理", "请先打开 PDF。")
            return
        from beeoffice.plugins.pdf_page_manager import PDFPageManagerDialog
        dlg = PDFPageManagerDialog(self._doc, self)
        if dlg.exec() == QDialog.Accepted and dlg.output_path:
            self.open_pdf(dlg.output_path)
            self._set_status("页面管理已应用（输出新文件）", 3000)

    def _rotate_current(self):
        self._set_status("旋转页面请使用“页面工具”（输出新文件，不修改原文件）", 3000)
        self._open_toolbox()

    def _open_toolbox(self):
        try:
            from beeoffice.plugins.pdf_toolbox_dialog import PDFToolboxDialog
            dlg = PDFToolboxDialog(self)
            dlg.exec()
        except Exception as e:
            QMessageBox.warning(self, "PDF 工具", f"无法打开工具：{e}")

    def _load_annotations(self, anno_path):
        """读取 .beeanno；坏条目逐条跳过，不让一条坏数据毁掉全部批注。"""
        try:
            with open(anno_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            logging.error(f"读取批注旁挂文件失败: {e}")
            QMessageBox.warning(
                self, "批注未载入",
                f"PDF 已打开，但旁挂批注文件无法解析：\n{e}",
            )
            return

        # 新格式是 {"version": ..., "annotations": [...]}；旧格式是裸列表
        if isinstance(raw, dict):
            raw = raw.get("annotations", [])
        if not isinstance(raw, list):
            logging.error("批注旁挂文件格式不可识别，已忽略")
            return

        loaded, skipped = [], 0
        for item in raw:
            try:
                loaded.append(Annotation.from_dict(item))
            except Exception as e:
                skipped += 1
                logging.warning(f"跳过无法解析的批注条目: {e}")

        self._annotations = loaded
        if skipped:
            QMessageBox.warning(
                self, "批注部分损坏",
                f"旁挂文件中有 {skipped} 条批注无法读取，已跳过；"
                f"其余 {len(loaded)} 条已正常载入。",
            )

    # ==================== 视图 ====================
    def _update_view(self):
        if not self._doc: return
        self._page_view.set_page(
            self._current_page, self._annotations,
            src=self._filepath, backend=self._backend,
        )
        self._page_label.setText(
            f"第 {self._current_page+1}/{self._page_count} 页"
        )
        if hasattr(self, "_thumb_list") and self._thumb_list.currentRow() != self._current_page:
            self._thumb_list.blockSignals(True)
            self._thumb_list.setCurrentRow(self._current_page)
            self._thumb_list.blockSignals(False)
        self._anno_list.clear()
        for i,a in enumerate([a for a in self._annotations if a.page==self._current_page]):
            self._anno_list.addItem(QListWidgetItem(f"{i+1}. [{a.type}] {a.text[:20]}"))
    def _set_tool(self,t): self._page_view.set_tool(t)
    def _choose_color(self):
        c=QColorDialog.getColor()
        if c.isValid(): self._current_color=(c.redF(),c.greenF(),c.blueF()); self._page_view.set_current_color(self._current_color)
    def _prev_page(self):
        if self._current_page>0: self._current_page-=1; self._update_view()
    def _next_page(self):
        if self._doc and self._current_page < self._page_count - 1:
            self._current_page += 1; self._update_view()
    def _on_annotation_added(self, anno):
        if anno.type in ("text", "textbox"):
            dlg=QDialog(self); dlg.setWindowTitle("添加文字批注"); ed=QTextEdit()
            btns=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
            btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
            l=QVBoxLayout(dlg); l.addWidget(ed); l.addWidget(btns)
            if dlg.exec()==QDialog.Accepted:
                anno.text=ed.toPlainText()
            else:
                return
        elif anno.type=="signature":
            text, ok = QInputDialog.getText(self, "签名", "输入签名文字")
            if not ok or not text:
                return
            anno.text=text
        self._annotations.append(anno); self._dirty_annotations=True; self._update_view()

    def _set_current_width(self, value):
        self._current_width = int(value)
        self._page_view.set_current_width(value)

    def _redo_annotation(self):
        if not getattr(self, "_redo_stack", None):
            self._set_status("没有可重做的批注", 2000)
            return
        anno = self._redo_stack.pop()
        self._annotations.append(anno)
        self._dirty_annotations = True
        self._update_view()

    def _toggle_annotations_visible(self):
        self._annotations_visible = not getattr(self, "_annotations_visible", True)
        self._page_view.set_annotations_visible(self._annotations_visible)
        self._set_status("显示批注" if self._annotations_visible else "隐藏批注", 2000)

    def _export_annotations(self):
        if not self._annotations:
            QMessageBox.information(self, "导出批注", "当前没有批注。")
            return
        p, _ = QFileDialog.getSaveFileName(
            self, "导出批注", "annotations.beeanno", "BeeAnno (*.beeanno)"
        )
        if not p:
            return
        payload = {"version": Annotation.FORMAT_VERSION,
                   "annotations": [a.to_dict() for a in self._annotations]}
        if not atomic_write_json(p, payload):
            QMessageBox.warning(self, "导出批注", "写入失败。")
            return
        self._set_status("批注已导出", 2000)

    def _import_annotations(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "导入批注", "", "BeeAnno (*.beeanno);;JSON (*.json)"
        )
        if not p:
            return
        try:
            import json
            data = json.loads(Path(p).read_text(encoding="utf-8"))
            items = data.get("annotations", data) if isinstance(data, dict) else data
            for item in items:
                self._annotations.append(Annotation.from_dict(item))
            self._update_view()
            self._set_status(f"已导入 {len(items)} 条批注", 3000)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "导入批注", f"导入失败：{e}")

    def _undo_annotation(self):
        """
        撤销当前页最后一处批注（P1-14 修复）

        原实现：
            if self._annotations:
                self._annotations.pop()    # ← 不看页码，误删他页
                self._update_view()

        修复后：
            倒序找当前页的最后一个批注删除；
            当前页无批注时提示，不误删其他页。
        """
        # 倒序找到当前页的最后一个批注
        for i in range(len(self._annotations) - 1, -1, -1):
            if self._annotations[i].page == self._current_page:
                removed = self._annotations.pop(i)
                self._redo_stack.append(removed)
                self._dirty_annotations = True
                self._update_view()
                return
        # 当前页没有批注
        QMessageBox.information(
            self, "提示", "当前页没有可撤销的批注"
        )

    # ==================== 保存 / 烧录 ====================
    def save_annotations_path(self):
        """返回当前 PDF 对应的旁挂批注文件路径（没有打开文件时为 None）。"""
        if not self._filepath:
            return None
        return Path(self._filepath).with_suffix(".beeanno")

    def _save_annotations(self):
        p = self.save_annotations_path()
        if p is None:
            QMessageBox.information(self, "提示", "请先打开一个 PDF")
            return

        payload = {
            "version": Annotation.FORMAT_VERSION,
            "annotations": [a.to_dict() for a in self._annotations],
        }
        # 优化规划 §1.8：原子写 + 失败必须让用户看见
        if not atomic_write_json(p, payload):
            QMessageBox.warning(
                self, "保存失败",
                f"批注保存失败（原有文件未被改动）：\n{p}\n\n"
                "请检查该目录是否可写。",
            )
            return

        self._dirty_annotations = False
        QMessageBox.information(self, "保存成功", f"批注已保存至：\n{p}")

    def _burn_annotations(self):
        if not self._doc or not self._annotations: QMessageBox.information(self,"提示","没有批注可烧录"); return
        p,_=QFileDialog.getSaveFileName(self,"保存已批注 PDF","","PDF (*.pdf)")
        if not p: return
        try:
            from beeoffice.pdf_tools import burn_annotations
            burn_annotations(
                self._filepath, p, [a.to_dict() for a in self._annotations]
            )
            QMessageBox.information(self,"烧录成功",f"已保存至：\n{p}")
        except Exception as e:
            logging.error(f"烧录批注失败: {e}")
            QMessageBox.warning(self,"烧录失败",str(e))

    # ==================== 关闭 ====================
    def closeEvent(self, event):
        """
        关闭前提醒未保存的批注。

        优化规划 §1.8：本类原本**没有** closeEvent，用户关掉窗口时，
        没有点过「保存批注」或「烧录」的批注会静默丢失。
        """
        # isVisible() 守卫：只有真正显示过的窗口才询问。headless 测试里
        # 构造出来的窗口没有 show()，若也弹模态框会把测试挂死。
        if self._annotations and self._dirty_annotations and self.isVisible():
            reply = QMessageBox.question(
                self,
                "批注未保存",
                f"有 {len(self._annotations)} 条批注尚未保存到旁挂文件。\n\n"
                "是否先保存再关闭？",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save,
            )
            if reply == QMessageBox.Cancel:
                event.ignore()
                return
            if reply == QMessageBox.Save:
                self._save_annotations()
        event.accept()
