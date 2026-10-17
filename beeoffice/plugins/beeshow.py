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

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import QTimer

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
    QWidget,
):
    """蜜演主视图（组装层）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BeeShow")
        self._init_state()
        self._build_ui()
        self._apply_initial_content()

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
        self._laser_active = False
        self._drawing_active = False
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

        # 任务 1.1：AI 服务（延迟创建，用到时才实例化）
        self._ai_service = None

        # 任务 3.1：PPTX 引擎（延迟创建）
        self._pptx_engine = None

        # 任务 3.2：字体嵌入器（延迟创建）
        self._font_embedder = None

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