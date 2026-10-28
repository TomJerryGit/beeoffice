# beeoffice/plugins/beeshow_toolbar_mixin.py
"""
蜜演 UI 构建 Mixin

职责：
  - _build_main_toolbar : 主工具栏（主题 / 背景 / 版式 / 表格 / 播放 /
                          演讲者 / 导出 / 导入 / 模板 / AI大纲 / 图标 /
                          二维码 / 排练 / 备注 / AI讲稿 / 历史 / 评论 /
                          同步 / 配图）
  - _build_info_bar     : 信息栏（页码 + 计时器 + 排练标签 + 动画下拉）
  - _build_splitter     : 主分屏（编辑器 + 预览 + 缩略图）
  - _build_shortcuts    : 快捷键（F5 / Escape）
  - _show_ai_notes_menu   : 「🤖 讲稿」右键菜单（任务 1.2）
  - _show_history_menu    : 「🕐 历史」右键菜单（任务 4.1）
  - _show_comment_menu    : 「💬 评论」右键菜单（任务 4.2）
  - _show_table_menu      : 「📊 表格」右键菜单（v5.2 B1）
  - _on_sync_btn_clicked  : 「📱 同步」按钮点击（任务 4.3）

v5.2 B1 增量：
  - _build_main_toolbar 里加「📊 表格」按钮
  - 新增 _show_table_menu 方法（右键菜单）

依赖：
  - PySide6（QToolBar / QComboBox / QPushButton / QLabel / QPlainTextEdit /
             QListWidget / QSplitter / QWidget / QVBoxLayout / QHBoxLayout /
             QAbstractItemView / QMenu / QFont / QShortcut / QKeySequence / Qt）
  - beeshow_constants.SLIDE_THEMES

注意：
  - 所有方法依赖 self._editor / self._preview / self._thumb_list 等，
    这些控件由本 Mixin 在 _build_splitter 中创建
  - 不导入其他 beeshow_* Mixin，避免循环依赖
  - QWebEngineView 延迟 import（仅 _build_splitter 用到）
  - BeeOfficeWebEnginePage 延迟 import（任务 2.2）
"""

from PySide6.QtWidgets import (
    QToolBar, QComboBox, QPushButton, QLabel, QPlainTextEdit,
    QListWidget, QSplitter, QWidget, QVBoxLayout, QHBoxLayout,
    QAbstractItemView, QMenu,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QShortcut, QKeySequence

from beeoffice.plugins.beeshow_constants import SLIDE_THEMES
from beeoffice.theme import Theme
from beeoffice.plugins.ribbon_widget import RibbonBar


class ToolbarMixin:
    """蜜演 UI 构建 Mixin"""

    def apply_theme(self):
        """主题切换后刷新蜜演工具栏/分组（阶段 3）。"""
        try:
            self._main_toolbar.setStyleSheet(Theme.toolbar_qss())
        except Exception:  # noqa: BLE001
            pass
        try:
            self._ribbon.apply_theme()
        except Exception:  # noqa: BLE001
            pass

    # ==================== 主工具栏 ====================
    def _build_main_toolbar(self) -> QToolBar:
        toolbar = QToolBar()
        toolbar.setStyleSheet(Theme.toolbar_qss())

        toolbar.addWidget(QLabel("🎥 蜜演 "))
        toolbar.addWidget(QLabel("主题:"))
        self._theme_combo = QComboBox()
        self._theme_combo.addItems(SLIDE_THEMES.keys())
        self._theme_combo.currentTextChanged.connect(self._on_theme_changed)
        toolbar.addWidget(self._theme_combo)

        btn_bg = QPushButton("🎨 背景")
        btn_bg.clicked.connect(self._customize_background)
        toolbar.addWidget(btn_bg)

        # 任务 2.1：版式选择
        btn_layout = QPushButton("📐 版式")
        btn_layout.setToolTip("选择幻灯片版式（12 种预定义）")
        btn_layout.clicked.connect(self._show_layout_picker)
        toolbar.addWidget(btn_layout)

        # v5.2 B1：表格编辑器
        btn_table = QPushButton("📊 表格")
        btn_table.setToolTip(
            "打开表格编辑器（右键编辑当前页已有表格）"
        )
        btn_table.clicked.connect(self._show_table_editor)
        btn_table.setContextMenuPolicy(Qt.CustomContextMenu)
        btn_table.customContextMenuRequested.connect(
            lambda pos, btn=btn_table: self._show_table_menu(
                btn.mapToGlobal(pos)
            )
        )
        toolbar.addWidget(btn_table)

        toolbar.addSeparator()

        self._play_btn = QPushButton("▶ 播放 (F5)")
        self._play_btn.setStyleSheet(
            "background:#FFB300;color:#000;font-weight:bold;padding:6px 12px;"
        )
        self._play_btn.clicked.connect(self._start_play)
        toolbar.addWidget(self._play_btn)

        btn_presenter = QPushButton("🎤 演讲者模式")
        btn_presenter.clicked.connect(self._start_presenter_mode)
        toolbar.addWidget(btn_presenter)

        # P1-B：打印预览（幻灯片 / 讲义 / 备注页 / 大纲）
        btn_print = QPushButton("🖨️ 打印")
        btn_print.setToolTip(
            "打印预览：幻灯片、讲义（每页多张）、备注页、大纲\n"
            "快捷键 Ctrl+P"
        )
        btn_print.clicked.connect(self._print_preview)
        toolbar.addWidget(btn_print)
        toolbar.addSeparator()

        for text, slot in [
            ("📄 PPTX", self._export_pptx),
            ("📕 PDF", self._export_pdf),
            ("🌐 HTML", self._export_html),
            ("🖼️ 图片", self._export_images),
            ("🎬 GIF", self._export_gif),
            ("📹 录制", self._record_presentation),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            toolbar.addWidget(btn)
        toolbar.addSeparator()

        btn_import = QPushButton("📂 导入MD")
        btn_import.clicked.connect(self._import_markdown)
        toolbar.addWidget(btn_import)

        btn_template = QPushButton("📋 模板")
        btn_template.clicked.connect(self._show_template_menu)
        toolbar.addWidget(btn_template)

        btn_ai = QPushButton("🤖 AI大纲")
        btn_ai.clicked.connect(self._ai_generate_outline)
        toolbar.addWidget(btn_ai)

        btn_icon = QPushButton("🎭 图标")
        btn_icon.clicked.connect(self._show_icon_picker)
        toolbar.addWidget(btn_icon)

        btn_qr = QPushButton("📱 二维码")
        btn_qr.clicked.connect(self._generate_qrcode)
        toolbar.addWidget(btn_qr)

        toolbar.addSeparator()

        btn_rehearsal = QPushButton("⏱ 排练")
        btn_rehearsal.setToolTip("开始/停止排练计时")
        btn_rehearsal.clicked.connect(self.toggle_rehearsal)
        toolbar.addWidget(btn_rehearsal)

        btn_notes = QPushButton("📝 备注")
        btn_notes.setToolTip("编辑当前幻灯片备注")
        btn_notes.clicked.connect(self.edit_current_notes)
        toolbar.addWidget(btn_notes)

        # 任务 1.2：AI 演讲稿
        btn_ai_notes = QPushButton("🤖 讲稿")
        btn_ai_notes.setToolTip(
            "AI 为当前页生成演讲稿（右键批量生成）"
        )
        btn_ai_notes.clicked.connect(self._ai_generate_notes)
        btn_ai_notes.setContextMenuPolicy(Qt.CustomContextMenu)
        btn_ai_notes.customContextMenuRequested.connect(
            lambda pos, btn=btn_ai_notes: self._show_ai_notes_menu(
                btn.mapToGlobal(pos)
            )
        )
        toolbar.addWidget(btn_ai_notes)

        # 任务 4.1：版本历史
        btn_history = QPushButton("🕐 历史")
        btn_history.setToolTip(
            "查看版本历史（右键快速回滚上一个版本）"
        )
        btn_history.clicked.connect(self._show_history_panel)
        btn_history.setContextMenuPolicy(Qt.CustomContextMenu)
        btn_history.customContextMenuRequested.connect(
            lambda pos, btn=btn_history: self._show_history_menu(
                btn.mapToGlobal(pos)
            )
        )
        toolbar.addWidget(btn_history)

        # 任务 4.2：评论
        btn_comment = QPushButton("💬 评论")
        btn_comment.setToolTip(
            "为当前页添加评论（右键查看评论面板）"
        )
        btn_comment.clicked.connect(self._add_comment)
        btn_comment.setContextMenuPolicy(Qt.CustomContextMenu)
        btn_comment.customContextMenuRequested.connect(
            lambda pos, btn=btn_comment: self._show_comment_menu(
                btn.mapToGlobal(pos)
            )
        )
        toolbar.addWidget(btn_comment)

        # 任务 4.3：远程同步演示
        btn_sync = QPushButton("📱 同步")
        btn_sync.setToolTip(
            "开启远程同步演示（观众扫码跟随翻页）"
        )
        btn_sync.setCheckable(True)
        btn_sync.clicked.connect(self._on_sync_btn_clicked)
        self._sync_btn = btn_sync
        toolbar.addWidget(btn_sync)

        # 任务 1.3：AI 配图
        btn_image_suggest = QPushButton("🖼️ 配图")
        btn_image_suggest.setToolTip(
            "根据当前页内容推荐配图"
        )
        btn_image_suggest.clicked.connect(
            self._show_image_suggester
        )
        toolbar.addWidget(btn_image_suggest)

        # WPS 式外壳：文件 / 开始 / 插入 / 放映 / 视图
        ribbon = RibbonBar()

        def _clone_click(target):
            def _go():
                for action in toolbar.actions():
                    widget = toolbar.widgetForAction(action)
                    if (widget is not None and hasattr(widget, "text")
                            and target in widget.text()):
                        widget.click()
                        return
            return _go

        # 文件：保存/导出/打印，两行大按钮（WPS 多行组）
        page = ribbon.add_tab("文件")
        group = ribbon.add_group(page, "📄 文件与导出")
        for label, target, icon_name in (
            ("💾\n保存", "保存", "save"),
            ("📄\n导出 PPTX", "PPTX", "export"),
        ):
            group.add_large_button(
                label, target, _clone_click(target), icon_name=icon_name
            )
        group.add_row()
        for label, target, icon_name in (
            ("📕\n导出 PDF", "PDF", "export"),
            ("🖨\n打印", "打印", "print"),
        ):
            group.add_large_button(
                label, target, _clone_click(target), icon_name=icon_name
            )

        # 开始：原有编辑/导出工具
        page = ribbon.add_tab("开始")
        group = ribbon.add_group(page, "🎥 编辑与导出")
        group.add_widget(toolbar)

        # 插入：背景/版式/表格/图片
        page = ribbon.add_tab("插入")
        group = ribbon.add_group(page, "🎨 插入与版式")
        for label, target, icon_name in (
            ("🎨\n背景", "背景", "image"),
            ("📐\n版式", "版式", "page"),
            ("📊\n表格", "表格", "table"),
            ("🖼\n图片", "图片", "image"),
        ):
            group.add_large_button(
                label, target, _clone_click(target), icon_name=icon_name
            )

        # 放映
        page2 = ribbon.add_tab("放映")
        group2 = ribbon.add_group(page2, "▶ 放映控制")
        group2.add_large_button("▶\n播放", "开始播放 (F5)", self._start_play, icon_name="play")
        group2.add_large_button("🎤\n演讲者", "演讲者模式", self._start_presenter_mode, icon_name="play")
        group2.add_large_button("🖨\n打印", "打印预览", self._print_preview, icon_name="print")
        group2.add_large_button("⏱\n排练", "开始/停止排练计时", self.toggle_rehearsal, icon_name="track")

        # 视图：主题/背景/版式
        page = ribbon.add_tab("视图")
        group = ribbon.add_group(page, "👁 主题与视图")
        for label, target, icon_name in (
            ("🎨\n背景", "背景", "image"),
            ("📐\n版式", "版式", "page"),
            ("🎭\n图标", "图标", "insert"),
        ):
            group.add_large_button(
                label, target, _clone_click(target), icon_name=icon_name
            )
        ribbon.add_quick_action("💾", "保存 (Ctrl+S)", self.save, icon_name="save")
        ribbon.add_quick_action("▶", "播放 (F5)", self._start_play, icon_name="play")
        self._ribbon = ribbon
        return ribbon

    # ==================== 右键菜单（任务 1.2 / 4.1 / 4.2 / v5.2 B1） ====================
    def _show_ai_notes_menu(self, global_pos):
        """「🤖 讲稿」按钮的右键菜单（任务 1.2）"""
        menu = QMenu(self)
        menu.addAction("📄 为当前页生成").triggered.connect(
            self._ai_generate_notes
        )
        menu.addAction("📚 为所有页批量生成").triggered.connect(
            self._ai_generate_all_notes
        )
        menu.exec(global_pos)

    def _show_history_menu(self, global_pos):
        """「🕐 历史」按钮的右键菜单（任务 4.1）"""
        menu = QMenu(self)
        menu.addAction("📜 查看版本历史").triggered.connect(
            self._show_history_panel
        )
        menu.addAction("↩ 回滚到上一个版本").triggered.connect(
            self._restore_last_snapshot
        )
        menu.addSeparator()
        menu.addAction("🧹 清空历史").triggered.connect(
            self._clear_history
        )
        menu.exec(global_pos)

    def _show_comment_menu(self, global_pos):
        """「💬 评论」按钮的右键菜单（任务 4.2）"""
        menu = QMenu(self)
        menu.addAction("➕ 为当前页添加评论").triggered.connect(
            self._add_comment
        )
        menu.addAction("📋 显示 / 隐藏评论面板").triggered.connect(
            self._show_comment_panel
        )
        menu.exec(global_pos)

    def _show_table_menu(self, global_pos):
        """「📊 表格」按钮的右键菜单（v5.2 B1）"""
        menu = QMenu(self)
        menu.addAction("🆕 新建表格").triggered.connect(
            self._show_table_editor
        )
        menu.addAction("✏️ 编辑当前页表格").triggered.connect(
            self._edit_current_table
        )
        menu.exec(global_pos)

    # ==================== 同步按钮点击（任务 4.3） ====================
    def _on_sync_btn_clicked(self, checked):
        """「📱 同步」按钮点击（任务 4.3）"""
        if checked:
            self._start_sync_mode()
            # 若启动失败，取消按钮选中
            if not self._sync_enabled:
                self._sync_btn.setChecked(False)
        else:
            self._stop_sync_mode()

    # ==================== 信息栏 ====================
    def _build_info_bar(self) -> QHBoxLayout:
        info_bar = QHBoxLayout()
        info_bar.setContentsMargins(8, 2, 8, 2)

        self._slide_label = QLabel("幻灯片: 0 页")
        info_bar.addWidget(self._slide_label)

        self._timer_label = QLabel("")
        self._timer_label.hide()
        info_bar.addWidget(self._timer_label)

        info_bar.addWidget(self._rehearsal_label)
        info_bar.addStretch()

        info_bar.addWidget(QLabel("动画:"))
        self._anim_combo = QComboBox()
        # 任务 5.2：加「平滑」选项
        self._anim_combo.addItems(
            ["无", "淡入", "滑入", "缩放", "平滑"]
        )
        info_bar.addWidget(self._anim_combo)

        return info_bar

    # ==================== 主分屏 ====================
    def _build_splitter(self) -> QSplitter:
        splitter = QSplitter(Qt.Horizontal)

        # 左侧：编辑器 + 备注编辑器
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self._editor = QPlainTextEdit()
        self._editor.setPlaceholderText(
            "在此编写幻灯片...\n"
            "--- 分隔每页\n"
            "<!-- 备注 --> 添加演讲备注\n"
            "{{number: 12345}} 动态数字\n"
            "{{video: path.mp4}} 视频嵌入\n"
            "{#element-id} 平滑动画标记\n"
            "| 表头1 | 表头2 | Markdown 表格"
        )
        self._editor.setFont(QFont("Consolas", 13))
        self._editor.textChanged.connect(self._on_editor_changed)
        left_layout.addWidget(self._editor, 3)

        self._notes_editor = QPlainTextEdit()
        self._notes_editor.setPlaceholderText("演讲者备注...")
        self._notes_editor.setMaximumHeight(60)
        self._notes_editor.textChanged.connect(self._on_notes_changed)
        left_layout.addWidget(self._notes_editor)

        splitter.addWidget(left)

        # 中间：预览（延迟 import QWebEngineView）
        # 任务 2.2：使用自定义 QWebEnginePage 拦截 beeoffice:// 协议
        from PySide6.QtWebEngineWidgets import QWebEngineView
        self._preview = QWebEngineView()

        # 任务 2.2：注入自定义 Page
        try:
            from beeoffice.plugins.beeshow_element_editor import (
                BeeOfficeWebEnginePage,
            )
            if BeeOfficeWebEnginePage is not None:
                self._preview.setPage(
                    BeeOfficeWebEnginePage(self, self._preview)
                )
        except Exception:
            # 元素编辑器未安装时降级为默认 Page
            pass

        self._preview.setMinimumWidth(350)
        splitter.addWidget(self._preview)

        # 右侧：缩略图
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.addWidget(QLabel("📑 导航 (可拖拽排序)"))

        self._thumb_list = QListWidget()
        self._thumb_list.setMaximumWidth(180)
        self._thumb_list.setDragDropMode(QAbstractItemView.InternalMove)
        self._thumb_list.setDefaultDropAction(Qt.MoveAction)
        self._thumb_list.model().rowsMoved.connect(self._on_slides_reordered)
        self._thumb_list.itemClicked.connect(self._on_thumb_clicked)
        self._thumb_list.itemDoubleClicked.connect(self._on_thumb_double_clicked)
        right_layout.addWidget(self._thumb_list)

        for text, slot in [
            ("➕ 添加", self._add_slide),
            ("➖ 删除", self._delete_slide),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            right_layout.addWidget(btn)

        splitter.addWidget(right)
        splitter.setSizes([350, 400, 180])

        # 任务 4.2：保留主 splitter 引用，供评论面板添加
        self._main_splitter = splitter

        return splitter

    # ==================== 快捷键 ====================
    def _build_shortcuts(self):
        QShortcut(QKeySequence("F5"), self).activated.connect(self._start_play)
        QShortcut(QKeySequence("Escape"), self).activated.connect(self._stop_play)
        # P1-B：打印预览（与蜜写/蜜算保持一致用 Ctrl+P）
        QShortcut(QKeySequence("Ctrl+P"), self).activated.connect(
            self._print_preview
        )