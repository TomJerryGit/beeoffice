# beeoffice/plugins/beeshow_plugin.py
"""
蜜演插件：将 BeeShowView 包装为符合 Plugin 基类的插件

v5.0.1 修复（P0-8）：
  - play_show() 删除检查 `hasattr(view, "current_index")` 与
    `hasattr(view, "show_slide")` 的死代码。
    实际 BeeShowView 里没有这两个属性（正确名字是 _current_slide
    和 _show_slide），且 _start_play() 内部已执行 self._current_slide = 0，
    无需额外处理。原实现的两个 hasattr 恒为 False，是纯误导性代码。
"""
import logging
from datetime import datetime

from PySide6.QtWidgets import QWidget, QMessageBox, QFileDialog

from beeoffice.plugin_base import Plugin


class BeeShowPlugin(Plugin):
    """蜜演插件"""

    name = "蜜演 BeeShow"
    version = "1.0"
    description = "演示文稿制作、动画效果、演讲备注、排练计时"
    author = "TomJerryGit"

    def __init__(self, parent=None):
        super().__init__(parent)

    # ---------- 创建控件 ----------
    def create_widget(self, parent=None) -> QWidget:
        """创建蜜演演示视图实例"""
        from beeoffice.plugins.beeshow import BeeShowView
        return BeeShowView(parent or self.parent)

    # ---------- 命令注册 ----------
    def register_commands(self, palette):
        """注册蜜演相关命令到命令面板"""
        palette.register_command(
            "蜜演：新建幻灯片",
            "创建一个新的蜜演演示文稿",
            self.new_show
        )
        palette.register_command(
            "蜜演：播放幻灯片",
            "全屏播放当前演示文稿 (F5)",
            self.play_show
        )
        palette.register_command(
            "蜜演：从当前页播放",
            "从当前幻灯片开始播放",
            self.play_from_current
        )
        palette.register_command(
            "蜜演：导出 PPTX",
            "将当前演示文稿导出为 PowerPoint",
            self.export_pptx
        )
        palette.register_command(
            "蜜演：演讲备注",
            "编辑当前幻灯片的演讲备注",
            self.edit_notes
        )
        palette.register_command(
            "蜜演：排练计时",
            "开始/停止排练计时",
            self.toggle_rehearsal
        )
        palette.register_command(
            "蜜演：添加幻灯片",
            "在当前演示文稿中新增一张幻灯片",
            self.add_slide
        )
        palette.register_command(
            "蜜演：删除幻灯片",
            "删除当前幻灯片",
            self.delete_slide
        )

    # ---------- 新建演示文稿 ----------
    def new_show(self) -> QWidget:
        """新建一个蜜演演示文稿并添加为标签页"""
        view = self.create_widget()
        timestamp = datetime.now().strftime("%H%M")
        self.parent.tab_manager.addTab(view, f"🎥 蜜演-{timestamp}")
        self.parent.tab_manager.setCurrentWidget(view)
        return view

    # ---------- 获取当前演示视图 ----------
    def _current_view(self):
        """返回当前标签页的蜜演视图（若非蜜演则返回 None）"""
        widget = self.parent.tab_manager.currentWidget()
        if widget is None:
            return None
        from beeoffice.plugins.beeshow import BeeShowView
        if isinstance(widget, BeeShowView):
            return widget
        return None

    # ---------- 播放 ----------
    def play_show(self):
        """
        从头开始播放当前演示文稿

        P0-8 修复：
          原实现在调用 _start_play() 之前，尝试通过
          `hasattr(view, "current_index")` 和
          `hasattr(view, "show_slide")` 定位到第一页。
          但 BeeShowView 的属性/方法名是 `_current_slide` /
          `_show_slide`（带下划线前缀），这两个 hasattr 恒为 False。
          且 _start_play() 内部已执行 `self._current_slide = 0`，
          因此无需在插件层做任何重置。此处删除死代码，避免误导。
        """
        view = self._current_view()
        if not view:
            self._warn("请先打开一个蜜演演示文稿")
            return
        if hasattr(view, "_start_play"):
            try:
                # _start_play 内部会重置 _current_slide = 0，无需额外处理
                view._start_play()
            except Exception as e:
                logging.error(f"播放失败: {e}")
                QMessageBox.warning(self.parent, "播放失败", str(e))
        else:
            self._warn("当前视图不支持播放功能")

    def play_from_current(self):
        """从当前页开始播放"""
        view = self._current_view()
        if not view:
            self._warn("请先打开一个蜜演演示文稿")
            return
        if hasattr(view, "_start_play"):
            try:
                view._start_play()
            except Exception as e:
                logging.error(f"播放失败: {e}")
                QMessageBox.warning(self.parent, "播放失败", str(e))
        else:
            self._warn("当前视图不支持播放功能")

    # ---------- 导出 ----------
    def export_pptx(self):
        """导出为 PPTX"""
        view = self._current_view()
        if not view:
            self._warn("请先打开一个蜜演演示文稿")
            return

        # 优先调用视图自身的导出方法
        if hasattr(view, "_export_pptx"):
            try:
                view._export_pptx()
                return
            except Exception as e:
                logging.error(f"导出 PPTX 失败: {e}")
                QMessageBox.warning(self.parent, "导出失败", str(e))
                return

        # 回退实现：通过文件对话框询问保存路径
        self._export_pptx_fallback(view)

    def _export_pptx_fallback(self, view):
        """回退的 PPTX 导出实现"""
        try:
            path, _ = QFileDialog.getSaveFileName(
                self.parent, "导出 PPTX", "presentation.pptx",
                "PowerPoint (*.pptx)"
            )
            if not path:
                return

            # 尝试从视图获取幻灯片内容
            slides = getattr(view, "slides", None)
            if slides is None:
                self._warn("当前视图不支持导出 PPTX")
                return

            # 使用 python-pptx 导出
            # （Inches / Pt 在本文件都未使用；真要用到时 F821 门禁会拦下）
            from pptx import Presentation

            prs = Presentation()
            for slide_data in slides:
                # 使用空白布局
                slide = prs.slides.add_slide(prs.slide_layouts[5])
                # 提取文本内容
                content = ""
                if isinstance(slide_data, str):
                    content = slide_data
                elif isinstance(slide_data, dict):
                    content = slide_data.get("content", "")
                elif hasattr(slide_data, "get_content"):
                    content = slide_data.get_content()

                # 添加标题
                title = slide.shapes.title
                if title is not None:
                    title.text = content.split("\n", 1)[0][:100]

                # 添加正文
                if len(content) > 50:
                    body = slide.placeholders[1] if len(slide.placeholders) > 1 else None
                    if body is not None:
                        body.text = content[:1000]

            prs.save(path)
            QMessageBox.information(self.parent, "完成", f"已导出:\n{path}")
            self.parent.set_global_status("PPTX 导出完成", 3000)
        except ImportError:
            QMessageBox.warning(self.parent, "缺少依赖",
                                "导出 PPTX 需要 python-pptx 库")
        except Exception as e:
            logging.error(f"导出 PPTX 失败: {e}")
            QMessageBox.warning(self.parent, "导出失败", str(e))

    # ---------- 演讲备注 ----------
    def edit_notes(self):
        """编辑当前幻灯片的演讲备注"""
        view = self._current_view()
        if not view:
            self._warn("请先打开一个蜜演演示文稿")
            return
        if hasattr(view, "edit_current_notes"):
            try:
                view.edit_current_notes()
            except Exception as e:
                logging.error(f"编辑备注失败: {e}")
                QMessageBox.warning(self.parent, "编辑失败", str(e))
        elif hasattr(view, "add_speaker_notes"):
            # 回退实现
            from PySide6.QtWidgets import QInputDialog
            try:
                current_idx = getattr(view, "_current_slide", 0)
                current_notes = ""
                notes = getattr(view, "_speaker_notes", None)
                if isinstance(notes, list) and 0 <= current_idx < len(notes):
                    current_notes = notes[current_idx]
                text, ok = QInputDialog.getMultiLineText(
                    self.parent, "演讲备注", "输入备注内容：", current_notes
                )
                if ok:
                    view.add_speaker_notes(text)
                    self.parent.set_global_status("备注已保存", 2000)
            except Exception as e:
                logging.error(f"编辑备注失败: {e}")
                QMessageBox.warning(self.parent, "编辑失败", str(e))
        else:
            self._warn("当前视图不支持演讲备注")

    # ---------- 排练计时 ----------
    def toggle_rehearsal(self):
        """开始/停止排练计时"""
        view = self._current_view()
        if not view:
            self._warn("请先打开一个蜜演演示文稿")
            return

        try:
            # 判断当前是否在计时
            is_running = False
            if hasattr(view, "rehearsal_timer"):
                is_running = view.rehearsal_timer.isActive()
            elif hasattr(view, "rehearsal_start_time"):
                is_running = view.rehearsal_start_time is not None

            if is_running:
                if hasattr(view, "stop_rehearsal"):
                    view.stop_rehearsal()
                else:
                    self._warn("当前视图不支持停止排练计时")
            else:
                if hasattr(view, "start_rehearsal"):
                    view.start_rehearsal()
                else:
                    self._warn("当前视图不支持排练计时")
        except Exception as e:
            logging.error(f"排练计时切换失败: {e}")
            QMessageBox.warning(self.parent, "操作失败", str(e))

    # ---------- 幻灯片管理 ----------
    def add_slide(self):
        """新增一张幻灯片"""
        view = self._current_view()
        if not view:
            self._warn("请先打开一个蜜演演示文稿")
            return
        if hasattr(view, "add_slide"):
            try:
                view.add_slide()
                self.parent.set_global_status("已添加幻灯片", 2000)
            except Exception as e:
                logging.error(f"添加幻灯片失败: {e}")
                QMessageBox.warning(self.parent, "添加失败", str(e))
        else:
            self._warn("当前视图不支持添加幻灯片")

    def delete_slide(self):
        """删除当前幻灯片"""
        view = self._current_view()
        if not view:
            self._warn("请先打开一个蜜演演示文稿")
            return

        # 确认删除
        reply = QMessageBox.question(
            self.parent, "删除幻灯片",
            "确定要删除当前幻灯片吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        if hasattr(view, "delete_slide"):
            try:
                view.delete_slide()
                self.parent.set_global_status("已删除幻灯片", 2000)
            except Exception as e:
                logging.error(f"删除幻灯片失败: {e}")
                QMessageBox.warning(self.parent, "删除失败", str(e))
        else:
            self._warn("当前视图不支持删除幻灯片")

    # ---------- 辅助 ----------
    def _warn(self, message: str):
        """统一提示"""
        QMessageBox.information(self.parent, "提示", message)

    # ---------- 生命周期 ----------
    def on_close(self):
        """插件关闭时清理"""
        super().on_close()
        logging.info("蜜演插件已卸载")