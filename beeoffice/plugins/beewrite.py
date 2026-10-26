# beeoffice/plugins/beewrite.py
"""
蜜写 BeeWrite —— 主编辑器（组装层）

各功能按职责拆分到 beewrite_*_mixin.py：
  - ToolbarMixin   : 工具栏构建
  - ModeMixin      : 模式切换 + 基础格式 + 内容接口
  - ParagraphMixin : 段落格式 + 字符底纹 + 多级列表
  - TableMixin     : 表格 + Markdown 表格 + Excel 数据
  - DocMixin       : 页眉页脚 + 目录 + 水印 + 页码 + 页面设置 + 打印
  - ExportMixin    : 导出 + 保存 + 模板
  - CommentMixin   : 批注 + 书签 + 修订
  - LinkMixin      : 超链接 + 交叉引用 + 图片 / 公式 / 文本框
  - AIMixin        : AI 辅助
  - ViewMixin      : 视图 + 查找替换 + 粘贴 + 撤销重做 + 状态栏

底层组件：
  - beewrite_utils.py          : 工具函数 + FORMAT_PAINTER
  - beewrite_rich_editor.py    : RichTextEditor(QTextEdit)
  - beewrite_md_table_dialog.py: MarkdownTableEditorDialog

历史更新（P0/P1 阶段）：
  - 修正所有 bewrite_* → beewrite_* 导入拼写
  - variable_panel 默认隐藏，避免占用 250px 压缩编辑区
  - 分屏初始宽度改为 [0, 500, 450, 0, 0]
  - 新增 _doc_kind 字段（"markdown" / "word"）
  - 新增 _current_file_path 字段（首次保存后记录路径）
  - 新增 set_doc_kind(kind) 方法（由 app.py 调用）
  - layout.addWidget(splitter, 1) 让编辑区占满剩余空间
  - 新增 closeEvent 方法（P0 阶段清理资源）

v5.0.2 图片修复：
  - 新增 set_current_file_path() 方法
    保存/打开文档后把路径同步到 rich_editor._current_file_dir，
    使粘贴/插入的图片保存到文档同目录的 media/ 而非 ~/media/
  - closeEvent 补充断开更多信号连接

v5.0.2 增强（本次）：
  - set_current_file_path 增强：同时设置 _current_file_path 和同步
    rich_editor._current_file_dir，并打印 debug 日志便于排查
  - 新增 get_current_file_path() 公开方法（供 RichTextEditor 兜底查找）
  - 新增 get_current_file_dir() 公开方法（返回当前文档所在目录）
  - closeEvent 清理 _current_file_path 时记录日志
"""
import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QSplitter, QStackedWidget,
    QPlainTextEdit, QTextEdit,
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QShortcut, QKeySequence

from beeoffice.plugins.find_replace import FindReplaceBar
from beeoffice.plugins.data_binding import DataSourceManager, BindingEngine
from beeoffice.plugins.variable_panel import VariablePanel

# ==================== 底层组件 ====================
from beeoffice.plugins.beewrite_utils import (
    FORMAT_PAINTER,
)
from beeoffice.plugins.beewrite_rich_editor import RichTextEditor

# ==================== 协作相关（已有文件） ====================
from beeoffice.plugins.beewrite_comment import (
    CommentManager,
    CommentPanel,
)
from beeoffice.plugins.beewrite_bookmark import BookmarkManager
from beeoffice.plugins.beewrite_revision import RevisionManager
from beeoffice.plugins.beewrite_crossref import CrossRefManager

# ==================== 插入对象（已有文件） ====================

# ==================== 视图组件（已有文件） ====================
from beeoffice.plugins.beewrite_outline import OutlinePanel

# ==================== Mixin 层 ====================
from beeoffice.plugins.beewrite_toolbar_mixin import ToolbarMixin
from beeoffice.plugins.ribbon_widget import RibbonBar
from beeoffice.plugins.beewrite_mode_mixin import ModeMixin
from beeoffice.plugins.beewrite_paragraph_mixin import ParagraphMixin
from beeoffice.plugins.beewrite_table_mixin import TableMixin
from beeoffice.plugins.beewrite_doc_mixin import DocMixin
from beeoffice.plugins.beewrite_export_mixin import ExportMixin
from beeoffice.plugins.beewrite_comment_mixin import CommentMixin
from beeoffice.plugins.beewrite_link_mixin import LinkMixin
from beeoffice.plugins.beewrite_ai_mixin import AIMixin
from beeoffice.plugins.beewrite_view_mixin import ViewMixin


# ==================== 主编辑器 ====================
class BeeWriteEditor(
    ToolbarMixin,
    ModeMixin,
    ParagraphMixin,
    TableMixin,
    DocMixin,
    ExportMixin,
    CommentMixin,
    LinkMixin,
    AIMixin,
    ViewMixin,
    QWidget,
):
    """蜜写主编辑器：组装所有 Mixin + 底层组件"""

    contentChanged = Signal()

    # ==================== 初始化 ====================
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BeeWrite")

        # ---------- 核心状态 ----------
        self.data_source_manager = DataSourceManager()
        self.binding_engine = BindingEngine(self.data_source_manager)
        self._edit_mode = "markdown"

        # 文档类型："markdown"（默认）或 "word"
        self._doc_kind = "markdown"
        # 当前文件路径（用于 Ctrl+S 直接写回 + 图片相对路径解析）
        self._current_file_path = None
        # 切模式时的 Markdown 源码缓存（用于保留样式）
        self._md_cache_before_switch = None

        # 页面设置
        # 单位约定：页边距一律以 **mm** 存储（优化规划 §2.2）。
        # 默认 25.4mm / 31.7mm = 1 英寸 / 1.25 英寸，即中文 Word 的常用默认值。
        # 原值为 2.54 / 3.17 —— 那是同样的数字以 cm 表示，但所有消费方
        # （DOCX 的 Mm()、PDF 的 @page、设置对话框的 /10 显示）都按 mm 解释，
        # 于是默认导出的页边距只有 1/10。页面设置对话框里也已写明单位是 mm。
        self._page_settings = {
            "paper": "A4",
            "orientation": "portrait",
            "margin_top": 25.4,
            "margin_bottom": 25.4,
            "margin_left": 31.7,
            "margin_right": 31.7,
        }

        # 协作管理器
        self._comment_manager = CommentManager()
        self._bookmark_manager = BookmarkManager()
        self._revision_manager = RevisionManager()
        self._crossref_manager = CrossRefManager()

        # 水印 / 页码
        self._watermark_config = None
        self._page_number_config = None

        # 阅读 / 双屏状态
        self._reading_mode = False
        self._split_view_active = False

        # ---------- 工具栏（由 ToolbarMixin 构建） ----------
        self._toolbar1 = self._build_toolbar1()
        self._toolbar2 = self._build_toolbar2()
        self._mode_toolbar = self._build_mode_toolbar()
        self._quick_toolbar = self._build_quick_toolbar()
        self._status_bar = self._build_status_bar()

        # ---------- 编辑器栈 ----------
        self.editor_stack = QStackedWidget()

        # Markdown 源码编辑器
        self.markdown_editor = QPlainTextEdit()
        self.markdown_editor.setFont(QFont("Consolas", 13))
        self.markdown_editor.setStyleSheet(
            "QPlainTextEdit{border:none;padding:8px;background:#FAFAFA}"
        )
        self.editor_stack.addWidget(self.markdown_editor)

        # 富文本编辑器
        self.rich_editor = RichTextEditor()
        self.rich_editor.cursorPositionChanged.connect(
            self._update_format_state
        )
        self.editor_stack.addWidget(self.rich_editor)

        # ---------- 预览区 ----------
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setStyleSheet(
            "QTextEdit{background:#FFF;border:none;padding:12px}"
        )

        # ---------- 变量面板（默认隐藏） ----------
        self.variable_panel = VariablePanel()
        self.variable_panel.setVisible(False)
        self.variable_panel.refresh_requested.connect(self._refresh_variables)
        self.variable_panel.bind_data_source.connect(
            self._bind_external_source
        )

        # ---------- 批注面板 ----------
        self._comment_panel = CommentPanel()
        self._comment_panel.setVisible(False)
        self._comment_panel.jump_requested.connect(self._on_comment_jump)
        self._comment_panel.delete_requested.connect(self._on_comment_delete)
        self._comment_panel.resolve_requested.connect(
            self._on_comment_resolve
        )
        self._comment_panel.reply_requested.connect(self._on_comment_reply)
        self._comment_panel.close_requested.connect(
            lambda: self._comment_panel.setVisible(False)
        )

        # ---------- 大纲面板 ----------
        self._outline_panel = OutlinePanel()
        self._outline_panel.setVisible(False)
        self._outline_panel.jump_requested.connect(self._on_outline_jump)
        self._outline_panel.close_requested.connect(
            lambda: self._outline_panel.setVisible(False)
        )

        # ---------- 主分屏（初始宽度调整） ----------
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._outline_panel)
        splitter.addWidget(self.editor_stack)
        splitter.addWidget(self.preview)
        splitter.addWidget(self._comment_panel)
        splitter.addWidget(self.variable_panel)
        splitter.setSizes([0, 500, 450, 0, 0])
        self._main_splitter = splitter

        # ---------- 查找栏 ----------
        self.find_bar = FindReplaceBar()
        self.find_bar.hide()

        # ---------- 工具栏容器 ----------
        toolbar_container = QVBoxLayout()
        toolbar_container.setContentsMargins(0, 0, 0, 0)
        toolbar_container.setSpacing(1)
        # WPS 式 Ribbon：把两行平铺工具栏收进「开始 / 插入」标签页
        self._ribbon = RibbonBar()
        # 开始：模式切换（Markdown/所见即所得）+ 字体/段落
        page = self._ribbon.add_tab("开始")
        group = self._ribbon.add_group(page, "📝 模式")
        group.add_layout(self._mode_toolbar)
        group = self._ribbon.add_group(page, "🖋 字体与段落")
        group.add_widget(self._toolbar1)
        # 插入：表格/图片/链接/分页/批注/修订等
        page = self._ribbon.add_tab("插入")
        group = self._ribbon.add_group(page, "📋 插入与对象")
        group.add_widget(self._toolbar2)
        # 页面：导出/保存/页面设置/页眉页脚/页面视图/拼写检查
        page = self._ribbon.add_tab("页面")
        group = self._ribbon.add_group(page, "📄 文件与页面")
        group.add_layout(self._quick_toolbar)
        toolbar_container.addWidget(self._ribbon)
        self._ribbon.add_quick_action("💾", "保存 (Ctrl+S)", self.save)
        self._ribbon.add_quick_action("🖨", "页面视图", self._print_preview)

        # ---------- 总布局 ----------
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(toolbar_container)
        # 关键修复：加 stretch=1，让分屏占满剩余空间，消除下方空白
        layout.addWidget(splitter, 1)
        layout.addWidget(self.find_bar)
        layout.addLayout(self._status_bar)

        # ---------- 信号连接 ----------
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._smart_refresh)

        self.markdown_editor.textChanged.connect(
            self._on_markdown_text_changed
        )
        self.rich_editor.textChanged.connect(
            lambda: self.contentChanged.emit()
        )

        # 状态栏更新
        self.markdown_editor.textChanged.connect(self._update_status_bar)
        self.rich_editor.textChanged.connect(self._update_status_bar)
        self.markdown_editor.cursorPositionChanged.connect(
            self._update_cursor_position
        )
        self.rich_editor.cursorPositionChanged.connect(
            self._update_cursor_position
        )

        # Markdown 编辑器双击 → 表格可视化编辑
        self.markdown_editor.mouseDoubleClickEvent = self._on_md_double_click

        # ---------- 快捷键 ----------
        # ⚠️ **这里不再注册 Ctrl+S**（实测踩过两次）
        # `menus.py:188` 已经为「保存」注册了窗口级 QAction。原先这里又注册了一遍，
        # 两者同键 → Qt 报 `Ambiguous shortcut overload: Ctrl+S`，**两个槽都不执行**
        # → 在蜜写里按 Ctrl+S 完全没有反应。
        # 我先后试过把它改成 `WidgetWithChildrenShortcut`，**仍然歧义** ——
        # Qt 的上下文只用于"是否匹配"，**不做优先级排序**，两个都匹配就判歧义。
        # 正确做法是**只保留一个来源**：由菜单的窗口级动作负责（它同样会调到
        # `widget.save()`，见 `app._save_current`）。
        QShortcut(QKeySequence("Ctrl+B"), self).activated.connect(
            self._toggle_bold
        )
        QShortcut(QKeySequence("Ctrl+I"), self).activated.connect(
            self._toggle_italic
        )
        QShortcut(QKeySequence("Ctrl+U"), self).activated.connect(
            self._toggle_underline
        )
        QShortcut(QKeySequence("Ctrl+K"), self).activated.connect(
            self._insert_hyperlink
        )
        QShortcut(QKeySequence("Ctrl+Shift+V"), self).activated.connect(
            self._paste_plain
        )
        QShortcut(QKeySequence("Ctrl+P"), self).activated.connect(
            self._print_preview
        )
        QShortcut(QKeySequence("Ctrl+Shift+I"), self).activated.connect(
            self._insert_image
        )
        QShortcut(QKeySequence("Ctrl+Shift+E"), self).activated.connect(
            self._insert_formula
        )
        QShortcut(QKeySequence("Ctrl+Shift+R"), self).activated.connect(
            self._toggle_revision
        )
        QShortcut(QKeySequence("Ctrl+Alt+M"), self).activated.connect(
            self._add_comment
        )
        QShortcut(QKeySequence("Ctrl+Shift+B"), self).activated.connect(
            self._add_bookmark
        )
        QShortcut(QKeySequence("Ctrl+B, G"), self).activated.connect(
            self._show_bookmark_list
        )
        QShortcut(QKeySequence("Ctrl+Shift+O"), self).activated.connect(
            self._toggle_outline
        )
        QShortcut(QKeySequence("F11"), self).activated.connect(
            self._toggle_reading_mode
        )
        QShortcut(QKeySequence("Escape"), self).activated.connect(
            self._close_find_bar
        )
        QShortcut(QKeySequence("F3"), self).activated.connect(
            lambda: (
                self.find_bar.find_next()
                if self.find_bar.isVisible()
                else self._find_current()
            )
        )
        QShortcut(QKeySequence("Shift+F3"), self).activated.connect(
            lambda: (
                self.find_bar.find_prev()
                if self.find_bar.isVisible()
                else self._find_current()
            )
        )

        # Markdown 表格快捷操作
        QShortcut(QKeySequence("Alt+Down"), self).activated.connect(
            self._md_add_row_below
        )
        QShortcut(QKeySequence("Alt+Up"), self).activated.connect(
            self._md_add_row_above
        )
        QShortcut(QKeySequence("Alt+Right"), self).activated.connect(
            self._md_add_col_right
        )
        QShortcut(QKeySequence("Alt+Left"), self).activated.connect(
            self._md_add_col_left
        )

        # ---------- 初始化状态 ----------
        self._refresh_preview()
        self._refresh_variables()
        self._toolbar1.setVisible(False)
        self._toolbar2.setVisible(False)

        self._update_status_bar()
        self._update_cursor_position()

    # ==================== 文档类型切换 ====================
    def set_doc_kind(self, kind: str):
        """
        由外部（app.py）设置文档类型。

        :param kind: "markdown" 或 "word"
        """
        if kind not in ("markdown", "word"):
            return
        self._doc_kind = kind
        # 同步保存按钮文字
        if hasattr(self, "_update_save_btn_text"):
            self._update_save_btn_text()

    # ==================== v5.0.2 新增：同步文件路径 ====================
    def set_current_file_path(self, path: str):
        """
        v5.0.2 新增：设置当前文件路径，并同步到 rich_editor 的 _current_file_dir。

        目的：使富文本模式下粘贴/插入的图片，保存到文档所在目录的 media/，
              而非用户主目录 ~/media/。

        调用时机：
          - ExportMixin._write_docx 保存成功后
          - ExportMixin._write_md   保存成功后
          - app.py._open_text_file  打开成功后
          - app.py._open_docx_file  打开成功后

        v5.0.2 增强：
          - 打印 debug 日志，便于排查图片路径问题
          - 同时保存 self._current_file_path 与 rich_editor._current_file_dir

        :param path: 文档的绝对路径
        """
        if not path:
            return
        self._current_file_path = str(path)
        try:
            from pathlib import Path as _Path
            base_dir = _Path(path).parent
            if hasattr(self, "rich_editor"):
                self.rich_editor.set_current_file_dir(str(base_dir))
                logging.debug(
                    f"[BeeWriteEditor.set_current_file_path] "
                    f"file_path={path}, "
                    f"rich_editor._current_file_dir={base_dir}"
                )
        except Exception as e:
            logging.error(f"同步 rich_editor 目录失败: {e}")

    # ==================== v5.0.2 新增：路径访问器 ====================
    def get_current_file_path(self) -> str:
        """
        v5.0.2 新增：返回当前文档路径（可能为 None）。

        供 RichTextEditor 在解析图片相对路径时兜底查找。
        """
        return self._current_file_path

    def get_current_file_dir(self) -> str:
        """
        v5.0.2 新增：返回当前文档所在目录（可能为 None）。

        优先级：
          1. _current_file_path 的父目录
          2. rich_editor._current_file_dir

        用途：RichTextEditor._insert_image_by_path 查找图片基准目录。
        """
        try:
            if self._current_file_path:
                from pathlib import Path as _Path
                return str(_Path(self._current_file_path).parent)
        except Exception:
            pass
        if hasattr(self, "rich_editor"):
            return getattr(self.rich_editor, "_current_file_dir", None)
        return None

    # ==================== 通用工具方法 ====================
    def _set_status(self, msg, timeout=0):
        """向上查找主窗口并设置全局状态"""
        p = self
        while p:
            if hasattr(p, "set_global_status"):
                p.set_global_status(msg, timeout)
                return
            p = p.parent()

    def _find_main_window(self):
        """向上查找主窗口（带 tab_manager 的对象）"""
        p = self
        while p:
            if hasattr(p, "tab_manager"):
                return p
            p = p.parent()
        return None

    # ==================== 预览 / 变量刷新 ====================
    def _refresh_preview(self):
        """刷新右侧预览"""
        md = self.content()
        if not md.strip():
            self.preview.setHtml("<p style='color:#AAA'>预览区域</p>")
            return
        try:
            import markdown
            rendered, _ = self.binding_engine.render(md)
            html = markdown.markdown(
                rendered,
                extensions=[
                    "tables",
                    "fenced_code",
                    "nl2br",
                    "sane_lists",
                    "toc",
                ],
            )
            self.preview.setHtml(html)
        except Exception as e:
            logging.error(f"预览渲染失败: {e}")
            self.preview.setPlainText(f"预览出错：{e}")

    def _refresh_variables(self):
        """刷新变量面板"""
        self.variable_panel.update_variables(
            self.binding_engine.preview(self.content()),
            self.data_source_manager.source_names,
        )

    def _smart_refresh(self):
        """防抖刷新：预览 + 变量"""
        self._refresh_preview()
        self._refresh_variables()

    # ==================== Markdown 文本变化 ====================
    def _on_markdown_text_changed(self):
        """Markdown 内容变化：防抖刷新 + 大纲延迟刷新"""
        self._update_timer.start(300)
        self.contentChanged.emit()
        if self._outline_panel.isVisible():
            if not hasattr(self, "_outline_refresh_timer"):
                self._outline_refresh_timer = QTimer(self)
                self._outline_refresh_timer.setSingleShot(True)
                self._outline_refresh_timer.timeout.connect(
                    self._refresh_outline_if_visible
                )
            self._outline_refresh_timer.start(600)

    # ==================== 数据源绑定 ====================
    def _bind_external_source(self, name, filepath):
        """绑定外部数据源文件"""
        try:
            self.data_source_manager.register_file(name, filepath)
        except Exception as e:
            self._set_status(f"绑定失败: {e}", 3000)

    def register_sheet_source(self, name, df):
        """注册来自蜜算的 DataFrame 数据源"""
        self.data_source_manager.register_dataframe(name, df)

    # ==================================================================
    # 关闭事件（P0 阶段新增：清理资源）
    # ==================================================================
    def closeEvent(self, event):
        """
        关闭时清理资源：
          - 停止定时器
          - 停止线程池任务
          - 清空格式刷状态
          - 断开信号连接
          - 隐藏面板
          - 清空管理器引用
        """
        # 1. 停止防抖定时器
        try:
            if hasattr(self, "_update_timer") and self._update_timer:
                self._update_timer.stop()
            if (hasattr(self, "_outline_refresh_timer")
                    and self._outline_refresh_timer):
                self._outline_refresh_timer.stop()
        except Exception as e:
            logging.error(f"停止定时器失败: {e}")

        # 2. 清空格式刷状态
        try:
            FORMAT_PAINTER.clear()
        except Exception as e:
            logging.error(f"清空格式刷失败: {e}")

        # 3. 停止异步任务（若有，最多等 500ms，避免阻塞退出）
        try:
            from beeoffice.async_task import AsyncTaskManager
            AsyncTaskManager.wait_for_done(500)
        except Exception:
            pass

        # 4. 断开 RichTextEditor 的信号连接
        try:
            if hasattr(self, "rich_editor"):
                try:
                    self.rich_editor.cursorPositionChanged.disconnect()
                except Exception:
                    pass
                try:
                    self.rich_editor.textChanged.disconnect()
                except Exception:
                    pass
        except Exception as e:
            logging.error(f"断开信号失败: {e}")

        # 5. 断开 Markdown 编辑器的信号连接
        try:
            if hasattr(self, "markdown_editor"):
                try:
                    self.markdown_editor.textChanged.disconnect()
                except Exception:
                    pass
                try:
                    self.markdown_editor.cursorPositionChanged.disconnect()
                except Exception:
                    pass
        except Exception as e:
            logging.error(f"断开 Markdown 编辑器信号失败: {e}")

        # 6. 隐藏批注面板 / 大纲面板 / 变量面板
        try:
            if hasattr(self, "_comment_panel"):
                self._comment_panel.setVisible(False)
            if hasattr(self, "_outline_panel"):
                self._outline_panel.setVisible(False)
            if hasattr(self, "variable_panel"):
                self.variable_panel.setVisible(False)
        except Exception:
            pass

        # 7. 清空管理器引用（帮助 GC）
        try:
            self._comment_manager = None
            self._bookmark_manager = None
            self._revision_manager = None
            self._crossref_manager = None
        except Exception:
            pass

        # 8. 保留 _current_file_path 直到销毁（供日志/调试用途）
        try:
            if self._current_file_path:
                logging.debug(
                    f"[BeeWriteEditor.closeEvent] "
                    f"closing, file={self._current_file_path}"
                )
        except Exception:
            pass

        logging.info("BeeWriteEditor 已关闭，资源已清理")
        event.accept()