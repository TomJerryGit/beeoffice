# beeoffice/plugins/beeshow.py
"""
蜜演 BeeShow —— 主组装层

拆分历史（v5.0.6）：
  - 原 1600 行单文件按职责拆分为 7 个模块：
      * beeshow_constants.py      : 常量 + _PlayWindow
      * beeshow_toolbar_mixin.py  : UI 构建
      * beeshow_slide_mixin.py    : 幻灯片解析 / 渲染 / 增删 / 排序
      * beeshow_play_mixin.py     : 全屏播放 / 演讲者模式 / 排练计时
      * beeshow_export_mixin.py   : 导出 PPTX/PDF/HTML/图片/GIF
      * beeshow_notes_mixin.py    : 演讲备注 + 状态栏
      * beeshow_ai_mixin.py       : AI 大纲 / 模板 / 图标 / 导入 / 二维码
  - 本文件只保留：
      * __init__（拆成 _init_state + _build_ui + _apply_initial_content）
      * closeEvent

v5.1 优化（14 任务）新增 Mixin：
  - 任务 2.1 LayoutMixin       : 12 种预定义版式
  - 任务 4.1 HistoryMixin      : 版本历史（最多 50 快照）
  - 任务 5.1 DynamicMixin      : 动态数字（{{number:...}}）
  - 任务 5.3 VideoMixin        : 视频嵌入（{{video:...}}）
  - 任务 4.2 CommentMixin      : 评论与批注
  - 任务 4.3 SyncMixin         : 远程同步演示（WebSocket）
  - 任务 5.2 MorphMixin        : 平滑动画（{#id} 跨页移动）

v5.2 B1 新增 Mixin：
  - TableMixin                 : 表格编辑器（可视化编辑行列）

兼容性：
  - 顶部 re-export SLIDE_THEMES / ICON_LIBRARY / TEMPLATE_LIBRARY，
    外部 `from beeoffice.plugins.beeshow import SLIDE_THEMES` 仍有效

保留的关键修复：
  - P0-2  _PlayWindow 转发键盘（constants 里）
  - P0-4  _export_views 保持 QWebEngineView 引用（export mixin 里）
  - P1-12 演讲者模式无备注引导（play mixin 里）
  - P1-13 拖拽排序保留 Markdown 源（slide mixin 里）
  - v5.0.5 __init__ 初始化 _play_window = None；_show_play_slide None 保护；
          _stop_play getattr 判空 + 显式置 None（play mixin 里）
"""

import logging
from pathlib import Path

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import QTimer, Signal

# ==================== Mixin 层 ====================
from beeoffice.plugins.beeshow_toolbar_mixin import ToolbarMixin
from beeoffice.plugins.beeshow_slide_mixin import SlideMixin
from beeoffice.plugins.beeshow_layout_mixin import LayoutMixin
from beeoffice.plugins.beeshow_table_mixin import TableMixin          # ← v5.2 B1
from beeoffice.plugins.beeshow_play_mixin import PlayMixin
from beeoffice.plugins.beeshow_export_mixin import ExportMixin
from beeoffice.plugins.beeshow_notes_mixin import NotesMixin
from beeoffice.plugins.beeshow_history_mixin import HistoryMixin
from beeoffice.plugins.beeshow_dynamic_mixin import DynamicMixin
from beeoffice.plugins.beeshow_video_mixin import VideoMixin
from beeoffice.plugins.beeshow_comment_mixin import CommentMixin
from beeoffice.plugins.beeshow_sync_mixin import SyncMixin
from beeoffice.plugins.beeshow_morph_mixin import MorphMixin
from beeoffice.plugins.beeshow_ai_mixin import AIMixin
from beeoffice.plugins.beeshow_print_mixin import ShowPrintMixin

# ==================== 常量 re-export（兼容外部 import） ====================
from beeoffice.plugins.beeshow_constants import (   # noqa: F401
    SLIDE_THEMES,
    ICON_LIBRARY,
    TEMPLATE_LIBRARY,
    LAYOUTS,
    LAYOUT_CSS,
    _PlayWindow,
)


# ==================== 主视图 ====================
class BeeShowView(
    ToolbarMixin,
    SlideMixin,
    LayoutMixin,
    TableMixin,          # ← v5.2 B1
    PlayMixin,
    ExportMixin,
    NotesMixin,
    HistoryMixin,
    DynamicMixin,
    VideoMixin,
    CommentMixin,
    SyncMixin,
    MorphMixin,
    AIMixin,
    ShowPrintMixin,      # ← P1-B：打印（幻灯片/讲义/备注页/大纲）
    QWidget,
):
    """蜜演主视图（组装层）"""

    #: 内容变化信号（供标签页的"● 未保存"标记 —— `tab_manager.addTab` 会接它）
    contentChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BeeShow")
        self._init_state()
        self._build_ui()
        self._apply_initial_content()
        # P0 修复：把编辑器的内容变化接到 contentChanged，
        # 让标签页能点亮"未保存"标记（原先蜜演没有这个信号）。
        editor = getattr(self, "_editor", None)
        if editor is not None and hasattr(editor, "textChanged"):
            try:
                editor.textChanged.connect(self._on_content_changed)
            except Exception:            # 控件不支持时忽略
                pass

    # ==================================================================
    # 内容接口（标签页未保存检查用）
    # ==================================================================
    def content(self) -> str:
        """
        返回当前演示文稿的 Markdown 源（供 `tab_manager` 做未保存检查）。

        P0 修复背景：蜜演原先**既没有 `save` 也没有 `content`** →
        ① Ctrl+S 毫无反应；② 关标签时 `tab_manager` 拿不到内容、
        记为 None → **静默关闭、稿子直接丢**（蜜演的"历史版本"只在内存里，
        导出件又是 PPTX/PDF/HTML，回不到编辑器）。
        这里先补上"能判断有没有改动"这一半（止损），完整的保存链路见审计报告 §2.7。
        """
        editor = getattr(self, "_editor", None)
        if editor is None:
            return ""
        try:
            text = editor.toPlainText()
            configs = getattr(self, "_slide_animations", None)
            if configs:
                from beeoffice.plugins.beeshow_animation import inject_markers
                text = inject_markers(text, configs)
            return text
        except RuntimeError:             # 控件已销毁
            return ""

    def _on_content_changed(self, *_args):
        """编辑器有改动 → 通知标签页（点亮"●"未保存标记）。"""
        try:
            self.contentChanged.emit()
        except Exception:
            pass

    # ==================================================================
    # 保存 / 打开（P0 剩余项：蜜演原先**整条保存链路不存在**）
    # ==================================================================
    def _suggested_deck_name(self) -> str:
        from beeoffice.plugins import beeshow_doc

        text = self.content()
        first = ""
        for line in text.splitlines():
            if line.strip():
                first = line
                break
        return beeshow_doc.suggested_filename(first)

    def _write_deck(self, path: str) -> bool:
        """把当前文稿写盘并记住路径（失败**如实提示**，不假装成功）。"""
        from beeoffice.plugins import beeshow_doc

        if not beeshow_doc.save_deck(
            path, self.content(),
            rehearsal=getattr(self, "_rehearsal_page_seconds", None),
        ):
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(
                self, "保存失败",
                f"没能写入：\n{path}\n\n请检查目录是否可写、文件是否被占用。",
            )
            return False
        self._current_file_path = str(path)
        self._sync_tab_title(str(path))
        return True

    def _sync_tab_title(self, path: str):
        """同步标签标题（主窗口通常有 `sync_tab_title`）。"""
        try:
            parent = self.window()
            if path and hasattr(parent, "sync_tab_title"):
                parent.sync_tab_title(self, path)
        except Exception as e:  # noqa: BLE001
            logging.debug(f"[蜜演] 同步标签标题失败（忽略）: {e}")

    def save(self) -> bool:
        """
        保存到**当前文件**；没有当前文件时退化为"另存为"。

        这一条是审计报告里最严重的缺口（§2.7）：蜜演原先没有 `save()`，
        `app._save_current` 的两个分支都不命中 → **Ctrl+S 毫无反应、也没有提示**，
        而导出件（PPTX/PDF/HTML）**回不到编辑器** → 做好的稿子关掉就改不了。
        """
        self._save_canceled = False
        path = getattr(self, "_current_file_path", None)
        if not path:
            return self.save_as()
        return self._write_deck(path)

    def save_as(self) -> bool:
        """另存为（重新选择路径）。"""
        from PySide6.QtWidgets import QFileDialog

        self._save_canceled = False
        path, _ = QFileDialog.getSaveFileName(
            self, "保存演示文稿", self._suggested_deck_name(),
            "蜜演演示文稿 (*.beshow);;所有文件 (*)",
        )
        if not path:
            self._save_canceled = True
            return False
        return self._write_deck(path)

    def open_deck(self, path) -> bool:
        """
        打开一份 `.beshow` 文稿（读入编辑器 → 刷新预览 → 记住路径）。

        :return: 成功 True；读失败 False（**不静默变成空文稿**）
        """
        from PySide6.QtWidgets import QMessageBox

        from beeoffice.plugins import beeshow_doc

        text = beeshow_doc.load_deck(path)
        if text is None:
            QMessageBox.warning(
                self, "打开失败", f"无法读取：\n{path}\n\n可能是编码或权限问题。"
            )
            return False
        self._editor.setPlainText(text)
        try:
            self._update_preview()
        except Exception as e:  # noqa: BLE001
            logging.warning(f"[蜜演] 刷新预览失败（已忽略）: {e}")
        self._current_file_path = str(path)
        self._sync_tab_title(str(path))
        try:
            self._rehearsal_page_seconds = beeshow_doc.load_rehearsal(path)
        except Exception:  # noqa: BLE001
            self._rehearsal_page_seconds = {}
        return True

    def open_pptx(self, path) -> bool:
        """
        **导入 `.pptx`**（P0-1：「打开别人的 PPT」）。

        纯转换在 `beeshow_pptx_import.py`（无 Qt），这里只做界面接线：
        读入编辑器 → 刷新预览 → **不把当前路径设成 .pptx**（保存时必须另存为 `.beshow`，
        绝不覆盖用户的原始 PPT）→ 有损失时**如实弹一份损失清单**。

        :return: 成功 True；解析失败 False（**不静默变成空文稿**）
        """
        from PySide6.QtWidgets import QMessageBox

        from beeoffice.plugins.beeshow_pptx_import import import_pptx, loss_summary

        try:
            imported, markdown = import_pptx(path)
        except Exception as e:  # noqa: BLE001 - 解析失败要给可操作提示
            QMessageBox.warning(
                self, "导入失败",
                f"无法读取 {Path(path).name}：\n{e}\n\n"
                "（.pptx 导入需要 python-pptx：pip install python-pptx）",
            )
            return False

        self._editor.setPlainText(markdown)
        try:
            self._update_preview()
        except Exception as e:  # noqa: BLE001
            logging.warning(f"[蜜演] 刷新预览失败（已忽略）: {e}")

        # ⚠️ 不设 _current_file_path：源文件是 .pptx，本编辑器**不能**写回它。
        # 保存时走"另存为"，用户自己选 .beshow 路径 —— 这条是数据安全红线。
        self._current_file_path = None
        self._sync_tab_title(f"{Path(path).stem}（从 PPT 导入）")

        if imported.has_losses():
            QMessageBox.information(
                self, "已导入（部分元素未保留）",
                loss_summary(imported)
                + "\n\n保存时会提示另存为 .beshow 文稿；原 .pptx 不会被改动。",
            )
        return True

    def set_current_file_path(self, path):
        """记录当前文件路径（打开/导入路径调用）。"""
        self._current_file_path = str(path) if path else None
        self._sync_tab_title(str(path)) if path else None

    # ==================== 状态初始化 ====================
    def _init_state(self):
        """所有属性初始化（不涉及 UI 构建）"""
        # 幻灯片状态
        self._slides_html = []
        self._slides_md = []           # P1-13：保留每张幻灯片的 Markdown 源
        self._current_slide = 0
        self._current_theme = "简约白"
        self._is_playing = False
        self._speaker_notes = []
        self._slide_titles = []
        self._start_time = 0

        # 缓存
        self._css_cache = {}
        self._preloaded_slides = set()

        # 播放交互状态
        self._custom_bg = None

        # P0-4：保持导出时创建的 QWebEngineView 引用，避免被 GC
        self._export_views = []

        # v5.0.5：全屏播放窗口引用
        # 原代码只在 _start_play() 里创建，__init__ 里未初始化，
        # 导致测试里只设置 _is_playing = True 后调用
        # keyPressEvent / _show_play_slide 会抛 AttributeError
        self._play_window = None

        # ===== 排练计时 =====
        self._rehearsal_timer = QTimer(self)
        self._rehearsal_timer.timeout.connect(self._update_rehearsal_time)
        self._rehearsal_start_time = None
        self._rehearsal_elapsed = 0
        self._rehearsal_page_seconds = {}
        self._rehearsal_page_start = None

        self._rehearsal_label = QLabel("")
        self._rehearsal_label.setStyleSheet(
            "QLabel{color:#E65100;font-weight:bold;padding:2px 8px;"
            "background:#FFF3E0;border-radius:4px;}"
        )
        self._rehearsal_label.hide()

        # 供插件调用的别名
        self.rehearsal_timer = self._rehearsal_timer
        self.rehearsal_start_time = None

        # 任务 4.1：版本历史（最多保留 50 个快照）
        self._slide_history = []

        # 任务 4.2：评论与批注
        # 用 try/except 保护，CommentMixin 未挂载时不影响主流程
        try:
            self._init_comments_state()
        except AttributeError:
            self._slide_comments = {}
            self._comment_next_id = 1
            self._comment_panel = None

        # 任务 4.3：远程同步演示
        try:
            self._init_sync_state()
        except AttributeError:
            self._sync_server = None
            self._sync_enabled = False
            self._sync_url = ""
            self._last_laser_broadcast = 0.0
            self._laser_throttle_interval = 0.05

        # 任务 2.2：主 splitter 引用（由 _build_splitter 赋值）
        # 放在这里是为了保证属性存在，即使 _build_splitter 未执行
        if not hasattr(self, "_main_splitter"):
            self._main_splitter = None

        # 优化规划 §3.1：原先在此把 _ai_service / _pptx_engine / _font_embedder
        # 初始化为 None，但全仓（生产代码）没有任何读取点 —— 三者都是"延迟创建"
        # 的旧设计残留，真正用到的服务都是在调用处即时 import + 实例化
        # （beeshow_ai_service / PPTXEngine / FontEmbedder）。已删除。

    # ==================== UI 构建 ====================
    def _build_ui(self):
        """组装工具栏 / 信息栏 / 分屏 / 布局 / 快捷键"""
        main_toolbar = self._build_main_toolbar()
        info_bar = self._build_info_bar()
        splitter = self._build_splitter()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(main_toolbar)
        layout.addLayout(info_bar)
        layout.addWidget(splitter)

        self._build_shortcuts()

    # ==================== 初始内容 ====================
    def _apply_initial_content(self):
        """
        写入欢迎页并立即同步解析。

        修复：
          - 原实现只调 setPlainText，触发 _on_editor_changed 的
            150ms 防抖异步解析；实例化后立即检查 _slides_html 会是空的。
          - 现在：
            1. blockSignals 避免异步防抖触发
            2. 立即调 _update_preview 同步解析
            3. 保证实例化后 _slides_html 立即有内容
        """
        self._editor.blockSignals(True)
        self._editor.setPlainText(
            "# 欢迎使用蜜演 🎥\n\n"
            "- `---` 分隔幻灯片\n"
            "- 7种主题 | 5种动画 | 12种版式\n"
            "- AI 大纲 | AI 讲稿 | AI 配图\n"
            "- 动态数字 | 视频嵌入 | 图片拖拽\n"
            "- 版本历史 | 评论批注 | 远程同步\n"
            "- 表格编辑器 | F5 播放\n\n"
            "---\n\n"
            "## 功能一览\n\n"
            "| 功能 | 说明 |\n|------|------|\n"
            "| 导出 | PPTX/PDF/HTML/图片/GIF |\n"
            "| 播放 | 激光笔/画笔/平滑动画 |\n"
            "| 协作 | 二维码分享/远程同步 |\n"
            "| 美化 | 版式系统/元素编辑/图片拖拽 |"
        )
        self._editor.blockSignals(False)

        # 立即同步解析（不依赖 150ms 防抖）
        self._update_preview()
    # ==================== 关闭事件 ====================
    def closeEvent(self, event):
        # 停止播放（P0-4 / v5.0.5：内部已判空）
        self._stop_play()

        # 任务 4.3：停止同步服务器
        try:
            self._cleanup_sync()
        except AttributeError:
            pass

        # 停止排练计时
        if hasattr(self, '_rehearsal_timer') and self._rehearsal_timer.isActive():
            self._rehearsal_timer.stop()

        # P0-4：清理未完成的导出视图
        try:
            for v in list(getattr(self, "_export_views", [])):
                try:
                    v.deleteLater()
                except Exception:
                    pass
            self._export_views.clear()
        except Exception:
            pass

        event.accept()