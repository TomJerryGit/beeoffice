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

import fitz
import json
from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
                                QListWidget, QListWidgetItem, QTextEdit, QFileDialog,
                                QMessageBox, QSplitter, QDialog, QDialogButtonBox,
                                QGraphicsView, QGraphicsScene, QColorDialog)
from PySide6.QtCore import Qt, QRectF, Signal, QPointF
from PySide6.QtGui import (QPixmap, QImage, QPainter, QColor, QPen, QFont)

from beeoffice.utils import atomic_write_json


class Annotation:
    #: .beeanno 旁挂文件格式版本（新写入的文件带此字段；旧文件是裸列表，仍可读）
    FORMAT_VERSION = 1

    def __init__(self, page, rect, anno_type="highlight", text="", color=(1,1,0)):
        self.page=page; self.rect=rect; self.type=anno_type; self.text=text; self.color=color
        self.created=datetime.now().isoformat()
    def to_dict(self): return {"page":self.page,"rect":[self.rect.x0,self.rect.y0,self.rect.x1,self.rect.y1],"type":self.type,"text":self.text,"color":list(self.color),"created":self.created}

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
            rect_obj = fitz.Rect(rect)
        except Exception:
            rect_obj = fitz.Rect(0, 0, 0, 0)

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
        self.setRenderHint(QPainter.SmoothPixmapTransform)
    def set_page(self, page, annotations):
        self._page=page; self._annotations=[a for a in annotations if a.page==page.number]; self._render_page()
    def _render_page(self):
        if not self._page: return
        mat=fitz.Matrix(self._scale, self._scale); pix=self._page.get_pixmap(matrix=mat)
        img=QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
        pixmap=QPixmap.fromImage(img); self._scene.clear(); self._scene.addPixmap(pixmap)
        for a in self._annotations:
            r=a.rect*self._scale; c=QColor(int(a.color[0]*255),int(a.color[1]*255),int(a.color[2]*255),80)
            if a.type=="highlight": self._scene.addRect(r.x0,r.y0,r.width,r.height,QPen(Qt.NoPen),c)
            elif a.type=="underline": self._scene.addLine(r.x0,r.y1,r.x1,r.y1,QPen(c,2))
            elif a.type=="strikethrough": self._scene.addLine(r.x0,(r.y0+r.y1)/2,r.x1,(r.y0+r.y1)/2,QPen(c,2))
            elif a.type=="text": self._scene.addText("💬",QFont("Segoe UI Emoji",12)).setPos(r.x0-8,r.y0-12)
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
            rect=fitz.Rect(sp.x(),sp.y(),ep2.x(),ep2.y())
            if not rect.is_empty and self._page:
                self.annotation_added.emit(Annotation(self._page.number,rect,self._current_tool,color=self._current_color))
            self._rubberband_start=None; self._render_page()
        else: super().mouseReleaseEvent(event)
    def set_tool(self,t): self._current_tool=t
    def set_current_color(self,c): self._current_color=c


class PDFAnnotator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🐝 PDF 批注"); self.resize(1100,750)
        self._doc=None; self._filepath=None; self._annotations=[]; self._current_page=0
        self._current_color=(1,0.8,0)
        # 优化规划 §1.8：用于 closeEvent 判断是否存在未落盘的批注
        self._dirty_annotations=False
        layout=QVBoxLayout(self)
        toolbar=QHBoxLayout()
        self._page_label=QLabel("第 1/1 页"); toolbar.addWidget(self._page_label); toolbar.addStretch()
        for n,t in [("🖍️ 高亮","highlight"),("📝 下划线","underline"),("🚫 删除线","strikethrough"),("💬 批注","text")]:
            btn=QPushButton(n); btn.setCheckable(True); btn.clicked.connect(lambda checked, tt=t: self._set_tool(tt)); toolbar.addWidget(btn)
        toolbar.addWidget(QPushButton("🎨 颜色", clicked=self._choose_color)); toolbar.addStretch()
        for text,slot in [("◀",self._prev_page),("▶",self._next_page),("💾 保存批注",self._save_annotations),("🔥 烧录",self._burn_annotations),("↩ 撤销",self._undo_annotation)]:
            toolbar.addWidget(QPushButton(text, clicked=slot))
        layout.addLayout(toolbar)
        splitter=QSplitter(Qt.Horizontal)
        self._page_view=PDFPageView(); self._page_view.annotation_added.connect(self._on_annotation_added); splitter.addWidget(self._page_view)
        right=QWidget(); rl=QVBoxLayout(right); rl.addWidget(QLabel("批注列表"))
        self._anno_list=QListWidget(); rl.addWidget(self._anno_list)
        self._note_editor=QTextEdit(); self._note_editor.hide(); rl.addWidget(self._note_editor)
        splitter.addWidget(right); splitter.setSizes([750,300]); layout.addWidget(splitter)

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
            self._doc = fitz.open(filepath)
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
        self._page_view.set_page(self._doc[self._current_page], self._annotations)
        self._page_label.setText(f"第 {self._current_page+1}/{len(self._doc)} 页")
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
        if self._doc and self._current_page<len(self._doc)-1: self._current_page+=1; self._update_view()
    def _on_annotation_added(self, anno):
        if anno.type=="text":
            dlg=QDialog(self); dlg.setWindowTitle("添加文字批注"); ed=QTextEdit()
            btns=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
            btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
            l=QVBoxLayout(dlg); l.addWidget(ed); l.addWidget(btns)
            if dlg.exec()==QDialog.Accepted: anno.text=ed.toPlainText()
            else: return
        self._annotations.append(anno); self._dirty_annotations=True; self._update_view()

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
                self._annotations.pop(i)
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
            nd=fitz.open(self._filepath)
            for a in self._annotations:
                pg=nd[a.page]
                anno=None
                if a.type=="highlight": anno=pg.add_highlight_annot(a.rect)
                elif a.type=="underline": anno=pg.add_underline_annot(a.rect)
                elif a.type=="strikethrough": anno=pg.add_strikeout_annot(a.rect)
                elif a.type=="text": anno=pg.add_text_annot(a.rect.tl, a.text)
                # 优化规划 §1.8：原实现不传颜色，烧出来永远是库默认色
                # （高亮黄／下划线红）——用户在 UI 里选的颜色只存在于屏幕叠加层。
                if anno is not None and a.type != "text":
                    try:
                        anno.set_colors(stroke=tuple(a.color))
                    except Exception as e:
                        logging.warning(f"设置批注颜色失败: {e}")
            nd.save(p); nd.close(); QMessageBox.information(self,"烧录成功",f"已保存至：\n{p}")
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
