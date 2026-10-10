# beeoffice/plugins/pdf_annotator.py
"""
PDF 批注工具

v5.0.1 修复（P1-14）：
  - _undo_annotation 从"只删最后一个"改为"删当前页最后一个"
    原实现 `self._annotations.pop()` 不看页码，用户在第 3 页点撤销
    会误删第 5 页最后一条批注。现在倒序找当前页的批注删除，
    当前页无批注时提示而非误删他页。
"""
import fitz, json
from pathlib import Path
from datetime import datetime
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
                                QListWidget, QListWidgetItem, QTextEdit, QFileDialog,
                                QMessageBox, QSplitter, QDialog, QDialogButtonBox,
                                QGraphicsView, QGraphicsScene, QColorDialog)
from PySide6.QtCore import Qt, QRectF, Signal, QPointF
from PySide6.QtGui import (QPixmap, QImage, QPainter, QColor, QPen, QFont)


class Annotation:
    def __init__(self, page, rect, anno_type="highlight", text="", color=(1,1,0)):
        self.page=page; self.rect=rect; self.type=anno_type; self.text=text; self.color=color
        self.created=datetime.now().isoformat()
    def to_dict(self): return {"page":self.page,"rect":[self.rect.x0,self.rect.y0,self.rect.x1,self.rect.y1],"type":self.type,"text":self.text,"color":self.color}
    @classmethod
    def from_dict(cls, data): return cls(data["page"], fitz.Rect(data["rect"]), data["type"], data["text"], data["color"])


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
        f=1.15 if event.angleDelta().y()>0 else 1/1.15; self._scale*=f; self._render_page()
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

    def open_pdf(self, filepath):
        try:
            self._doc=fitz.open(filepath); self._filepath=filepath; self._annotations=[]; self._current_page=0
            ap=Path(filepath).with_suffix(".beeanno")
            if ap.exists():
                with open(ap,'r',encoding='utf-8') as f: self._annotations=[Annotation.from_dict(d) for d in json.load(f)]
            self._update_view()
        except Exception as e: QMessageBox.warning(self,"打开失败",str(e))
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
        self._annotations.append(anno); self._update_view()

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
                self._update_view()
                return
        # 当前页没有批注
        QMessageBox.information(
            self, "提示", "当前页没有可撤销的批注"
        )

    def _save_annotations(self):
        if not self._filepath: return
        p=Path(self._filepath).with_suffix(".beeanno")
        with open(p,'w',encoding='utf-8') as f: json.dump([a.to_dict() for a in self._annotations],f,indent=2,ensure_ascii=False)
        QMessageBox.information(self,"保存成功",f"批注已保存至：\n{p}")
    def _burn_annotations(self):
        if not self._doc or not self._annotations: QMessageBox.information(self,"提示","没有批注可烧录"); return
        p,_=QFileDialog.getSaveFileName(self,"保存已批注 PDF","","PDF (*.pdf)")
        if not p: return
        try:
            nd=fitz.open(self._filepath)
            for a in self._annotations:
                pg=nd[a.page]
                if a.type=="highlight": pg.add_highlight_annot(a.rect)
                elif a.type=="underline": pg.add_underline_annot(a.rect)
                elif a.type=="strikethrough": pg.add_strikeout_annot(a.rect)
                elif a.type=="text": pg.add_text_annot(a.rect.tl, a.text)
            nd.save(p); nd.close(); QMessageBox.information(self,"烧录成功",f"已保存至：\n{p}")
        except Exception as e: QMessageBox.warning(self,"烧录失败",str(e))