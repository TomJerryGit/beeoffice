# beeoffice/menus.py
"""
菜单构建模块：集中定义主窗口的所有菜单和动作

优化要点：
  1. 所有菜单项接入 i18n（tr 函数），与 locales/zh_CN.json、en_US.json 键名对齐
  2. 强调色子菜单使用 theme.accent.* 翻译键，并显示当前勾选状态
  3. 补充缺失菜单项：从模板新建、保存为模板、导出子菜单、生成报告、
     PDF 批注、批量转换、AI 辅助、宏、关联表格到文档等
  4. 新增「工具」菜单，集中放置文档处理类功能
  5. 撤销/重做动作连接到当前控件（QPlainTextEdit / QTextEdit）
  6. 新增插件菜单注册入口（调用 Plugin.register_menus 钩子）
  7. 「WebDAV 设置」更名为「云存储设置」，与实际能力一致（支持 WebDAV / OneDrive / Google Drive）

## i18n 决策（2026-10-20）
界面**中文优先（B 路线）**：不再提供语言切换入口 —— 实测 `tr()` 包装率仅约 11%，
切到 en_US 后大部分界面仍是中文（"半英文"体验比纯中文更差）。
`beeoffice/i18n.py` 与 `locales/*.json` **保留**，作为未来按模块 tr 化的基础设施；
`tools/i18n_audit.py` 的 GUI 硬编码棘轮继续阻止新增债务。
"""
import logging

from PySide6.QtGui import QAction, QActionGroup, QKeySequence

from beeoffice.i18n import tr
from beeoffice.theme import Theme


# ==================== 内部辅助函数 ====================
def _resolve_editor(widget):
    """
    从标签页控件中解析出可撤销/重做的编辑器。

    兼容三种情况：
      · 蜜写：`widget.editor`（**活动**编辑器，见 `beewrite_mode_mixin.editor`），
        或旧的 `markdown_editor`；
      · 蜜算这类"**视图自己就是撤销目标**"的模块：它没有 `editor` 属性，
        但自己实现了 `undo()`/`redo()`（走它自己的命令栈），直接把视图给它。

    为什么加最后一条：蜜算原先自己在 `_build_shortcuts()` 里注册了
    Ctrl+Z/Ctrl+Y 的 QShortcut，与这里的菜单 QAction **同键** →
    Qt 报 `Ambiguous shortcut overload: Ctrl+Z / Ctrl+Y`，
    **两个都不触发** → 蜜算里按 Ctrl+Z 完全失效。
    Qt 的上下文只决定"是否匹配"、不做优先级，所以只能**只留一个来源**：
    统一由菜单动作负责，撤销目标由本函数解析。
    """
    if widget is None:
        return None
    if hasattr(widget, "editor"):
        return widget.editor
    if hasattr(widget, "markdown_editor"):
        return widget.markdown_editor
    if hasattr(widget, "undo") and hasattr(widget, "redo"):
        return widget
    return None


def _apply_undo(main_window):
    """对当前控件执行撤销（若支持）"""
    widget = main_window.tab_manager.currentWidget()
    editor = _resolve_editor(widget)
    if editor is not None and hasattr(editor, "undo"):
        editor.undo()


def _apply_redo(main_window):
    """对当前控件执行重做（若支持）"""
    widget = main_window.tab_manager.currentWidget()
    editor = _resolve_editor(widget)
    if editor is not None and hasattr(editor, "redo"):
        editor.redo()


def _build_accent_menu(main_window, parent_menu):
    """
    构建强调色子菜单（使用 i18n，并显示当前勾选状态）
    :param main_window: BeeApp 实例
    :param parent_menu: 挂载到的父菜单（视图菜单）
    """
    accent_menu = parent_menu.addMenu(tr("menu.view.accent", "🎨 强调色"))
    current_accent = getattr(main_window.settings, "accent_color", "amber")
    accent_group = QActionGroup(main_window)
    accent_group.setExclusive(True)

    for accent_key in list(Theme.ACCENT_COLORS.keys()):
        display_name = tr(
            f"theme.accent.{accent_key}",
            accent_key.capitalize(),
        )
        action = QAction(display_name, main_window)
        action.setCheckable(True)
        action.setChecked(current_accent == accent_key)
        action.triggered.connect(
            lambda checked=False, n=accent_key: main_window._set_accent(n)
        )
        accent_group.addAction(action)
        accent_menu.addAction(action)


def _register_plugin_menus(main_window, menu_bar):
    """
    遍历插件，让插件通过 register_menus 钩子注册自己的菜单
    :param main_window: BeeApp 实例
    :param menu_bar: QMenuBar 实例
    """
    plugin_manager = getattr(main_window, "plugin_manager", None)
    if not plugin_manager:
        # 插件管理器尚未初始化（启动早期）——静默跳过
        return

    for plugin in getattr(plugin_manager, "plugins", []) or []:
        if hasattr(plugin, "register_menus"):
            try:
                plugin.register_menus(menu_bar)
            except Exception as e:
                logging.error(
                    f"插件 {getattr(plugin, 'name', '未知')} 注册菜单失败: {e}"
                )


# ==================== 主函数 ====================
def setup_menus(main_window):
    """
    为指定主窗口构建菜单栏
    :param main_window: BeeApp 实例
    """
    menu_bar = main_window.menuBar()

    # ==================== 文件菜单 ====================
    file_menu = menu_bar.addMenu(tr("menu.file", "文件"))

    # ---- 新建子菜单 ----
    new_menu = file_menu.addMenu(tr("menu.file.new", "新建"))

    new_doc_action = new_menu.addAction(tr("menu.file.new_doc", "新建蜜写文档"))
    new_doc_action.setShortcut(QKeySequence("Ctrl+N"))
    new_doc_action.triggered.connect(main_window._new_beewrite)

    new_word_action = new_menu.addAction(tr("menu.file.new_word", "新建 Word 文档"))
    new_word_action.triggered.connect(main_window._new_word_doc)

    new_sheet_action = new_menu.addAction(tr("menu.file.new_sheet", "新建蜜算表格"))
    new_sheet_action.setShortcut(QKeySequence("Ctrl+T"))
    new_sheet_action.triggered.connect(main_window._new_beesheet)

    new_show_action = new_menu.addAction(tr("menu.file.new_show", "新建蜜演"))
    new_show_action.triggered.connect(main_window._new_beeshow)

    new_menu.addSeparator()

    # 从模板新建
    new_tpl_action = new_menu.addAction(tr("cmd.template_new", "从模板新建"))
    new_tpl_action.setShortcut(QKeySequence("Ctrl+Shift+T"))
    new_tpl_action.triggered.connect(main_window._show_template_picker)

    file_menu.addSeparator()

    # ---- 打开 ----
    open_action = QAction(tr("menu.file.open", "打开"), main_window)
    open_action.setShortcut(QKeySequence.Open)
    open_action.triggered.connect(main_window.tab_manager.open_file)
    file_menu.addAction(open_action)

    file_menu.addSeparator()

    # ---- 保存 / 另存为 / 保存为模板 ----
    save_action = QAction(tr("menu.file.save", "保存"), main_window)
    save_action.setShortcut(QKeySequence.Save)
    save_action.triggered.connect(main_window._save_current)
    file_menu.addAction(save_action)

    save_as_action = QAction(tr("menu.file.save_as", "另存为"), main_window)
    save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
    save_as_action.triggered.connect(main_window._save_as_current)
    file_menu.addAction(save_as_action)

    save_tpl_action = QAction(tr("cmd.template_save", "保存为模板"), main_window)
    save_tpl_action.triggered.connect(main_window._save_as_template)
    file_menu.addAction(save_tpl_action)

    file_menu.addSeparator()

    # ---- 导出子菜单 ----
    export_menu = file_menu.addMenu(tr("menu.file.export", "导出"))

    export_docx_action = export_menu.addAction(tr("cmd.export_docx", "导出 DOCX"))
    export_docx_action.triggered.connect(main_window._export_docx)

    export_pdf_action = export_menu.addAction(tr("cmd.export_pdf", "导出 PDF"))
    export_pdf_action.triggered.connect(main_window._export_pdf)

    # 优化规划 §2.6「补」：蜜写侧已实现 export_html()，入口重新接上
    export_html_action = export_menu.addAction(tr("cmd.export_html", "导出 HTML"))
    export_html_action.triggered.connect(main_window._export_html)

    export_menu.addSeparator()

    export_pptx_action = export_menu.addAction(tr("cmd.export_pptx", "导出 PPTX"))
    export_pptx_action.triggered.connect(main_window._export_beeshow_pptx)

    generate_report_action = export_menu.addAction(
        tr("cmd.generate_report", "生成报告")
    )
    generate_report_action.triggered.connect(main_window._generate_report)

    file_menu.addSeparator()

    # ---- 最近打开子菜单 ----
    # 注意：_update_recent_menu 会读写 main_window.recent_menu，必须提前挂载
    main_window.recent_menu = file_menu.addMenu(
        tr("menu.file.recent", "最近打开")
    )
    main_window._update_recent_menu()

    file_menu.addSeparator()

    # ---- 退出 ----
    exit_action = QAction(tr("menu.file.exit", "退出"), main_window)
    exit_action.setShortcut(QKeySequence.Quit)
    exit_action.triggered.connect(main_window.close)
    file_menu.addAction(exit_action)

    # ==================== 编辑菜单 ====================
    edit_menu = menu_bar.addMenu(tr("menu.edit", "编辑"))

    undo_action = QAction(tr("menu.edit.undo", "撤销"), main_window)
    undo_action.setShortcut(QKeySequence.Undo)
    undo_action.triggered.connect(lambda: _apply_undo(main_window))
    edit_menu.addAction(undo_action)

    redo_action = QAction(tr("menu.edit.redo", "重做"), main_window)
    redo_action.setShortcut(QKeySequence.Redo)
    redo_action.triggered.connect(lambda: _apply_redo(main_window))
    edit_menu.addAction(redo_action)

    edit_menu.addSeparator()

    # 命令面板
    palette_action = QAction(
        tr("menu.edit.command_palette", "命令面板"), main_window
    )
    palette_action.setShortcut(QKeySequence("Ctrl+Shift+P"))
    palette_action.triggered.connect(main_window.show_command_palette)
    edit_menu.addAction(palette_action)

    # 查找替换
    find_action = QAction(tr("menu.edit.find_replace", "查找替换"), main_window)
    find_action.setShortcut(QKeySequence("Ctrl+F"))
    find_action.triggered.connect(main_window._find_current)
    edit_menu.addAction(find_action)

    # ==================== 工具菜单 ====================
    tools_menu = menu_bar.addMenu(tr("menu.tools", "工具"))

    # ---- AI 辅助 ----
    ai_menu = tools_menu.addMenu(tr("menu.tools.ai", "AI 辅助"))

    ai_continue_action = ai_menu.addAction(tr("cmd.ai_continue", "AI 续写"))
    ai_continue_action.triggered.connect(main_window._ai_continue)

    ai_polish_action = ai_menu.addAction(tr("cmd.ai_polish", "AI 润色"))
    ai_polish_action.triggered.connect(main_window._ai_polish)

    ai_summarize_action = ai_menu.addAction(tr("cmd.ai_summarize", "AI 总结"))
    ai_summarize_action.triggered.connect(main_window._ai_summarize)

    tools_menu.addSeparator()

    # ---- 恢复未保存的内容（P0-5 的手动入口）----
    # 审计发现 `_check_recoverable_drafts(force=True)` 没有任何调用方（死参数）：
    # 启动弹框一旦点了"否"，此前的草稿就再也找不到了。这里补一个菜单入口。
    restore_drafts_action = tools_menu.addAction(
        tr("cmd.restore_drafts", "恢复未保存的内容…")
    )
    restore_drafts_action.triggered.connect(
        lambda: main_window._check_recoverable_drafts(force=True)
    )

    tools_menu.addSeparator()

    # ---- 蜜算专项 ----
    analyze_action = tools_menu.addAction(
        tr("cmd.analyze_sheet", "智能数据分析")
    )
    analyze_action.triggered.connect(main_window._analyze_current_sheet)

    # 刷新透视表：规格存在文件的隐藏表里（P1）
    refresh_pivot_action = tools_menu.addAction(
        tr("cmd.refresh_pivot", "刷新透视表")
    )
    refresh_pivot_action.setToolTip(
        "按文件里保存的透视表配置重新汇总（数据取当前表格）"
    )
    main_window.refresh_pivot_action = refresh_pivot_action

    def _refresh_pivot_from_menu():
        from PySide6.QtWidgets import QMessageBox

        widget = main_window.tab_manager.currentWidget()
        if widget is not None and hasattr(widget, "_refresh_pivot"):
            widget._refresh_pivot()
        else:
            QMessageBox.information(
                main_window, "刷新透视表",
                "当前标签页不是表格，无法刷新透视表。",
            )

    refresh_pivot_action.triggered.connect(_refresh_pivot_from_menu)

    nl_formula_action = tools_menu.addAction(
        tr("cmd.nl_formula", "自然语言生成公式")
    )
    nl_formula_action.triggered.connect(main_window._nl_formula)

    link_sheet_action = tools_menu.addAction(
        tr("cmd.link_sheet", "关联表格到文档")
    )
    link_sheet_action.triggered.connect(main_window._link_sheet_to_write)

    tools_menu.addSeparator()

    # ---- 批量转换 ----
    batch_menu = tools_menu.addMenu(tr("menu.tools.batch", "批量转换"))

    batch_docx_action = batch_menu.addAction(
        tr("cmd.batch_docx_to_md", "批量 DOCX 转 MD")
    )
    batch_docx_action.triggered.connect(main_window._batch_docx_to_md)

    batch_md_action = batch_menu.addAction(
        tr("cmd.batch_md_to_docx", "批量 MD 转 DOCX")
    )
    batch_md_action.triggered.connect(main_window._batch_md_to_docx)

    tools_menu.addSeparator()

    # ---- PDF 批注 ----
    pdf_action = tools_menu.addAction(tr("cmd.pdf_annotator", "PDF 批注"))
    pdf_action.triggered.connect(lambda: main_window._open_pdf_annotator())

    # ---- PDF 工具箱（S1） ----
    pdf_toolbox_action = tools_menu.addAction("🧰 PDF 工具箱")
    pdf_toolbox_action.triggered.connect(main_window.show_pdf_toolbox)

    # ==================== 视图菜单 ====================
    view_menu = menu_bar.addMenu(tr("menu.view", "视图"))

    # 主题：浅色 / 深色（阶段 2：全局主题，持久化）
    theme_menu = view_menu.addMenu(tr("menu.view.theme", "🎨 主题"))
    theme_group = QActionGroup(main_window)
    theme_group.setExclusive(True)
    light_action = QAction("☀️ 浅色", main_window, checkable=True)
    light_action.setChecked(main_window.settings.theme != "dark")
    light_action.triggered.connect(
        lambda _=False: main_window._set_theme("light")
    )
    dark_action = QAction("🌙 深色", main_window, checkable=True)
    dark_action.setChecked(main_window.settings.theme == "dark")
    dark_action.triggered.connect(
        lambda _=False: main_window._set_theme("dark")
    )
    theme_group.addAction(light_action)
    theme_group.addAction(dark_action)
    theme_menu.addAction(light_action)
    theme_menu.addAction(dark_action)

    # 强调色子菜单
    _build_accent_menu(main_window, view_menu)

    view_menu.addSeparator()

    # 分屏
    split_action = QAction(tr("menu.view.split", "分屏"), main_window)
    split_action.setShortcut(QKeySequence("Ctrl+\\"))
    split_action.triggered.connect(main_window.tab_manager.split_with_current)
    view_menu.addAction(split_action)

    # 任务窗格原型（S0 壳）
    taskpane_action = QAction("🧩 任务窗格（原型）", main_window)
    taskpane_action.triggered.connect(main_window.show_task_pane_demo)
    view_menu.addAction(taskpane_action)

    # 语言子菜单已移除（2026-10-20 i18n 决策：中文优先，不再提供半成品英文界面）

    # ==================== 帮助菜单 ====================
    help_menu = menu_bar.addMenu(tr("menu.help", "帮助"))

    # 关于
    about_action = QAction(tr("menu.help.about", "关于"), main_window)
    about_action.triggered.connect(main_window.show_about)
    help_menu.addAction(about_action)

    # 快捷键
    shortcuts_action = QAction(tr("menu.help.shortcuts", "快捷键"), main_window)
    shortcuts_action.triggered.connect(main_window._show_shortcuts)
    help_menu.addAction(shortcuts_action)

    help_menu.addSeparator()

    # 查看错误日志
    log_action = QAction(tr("menu.help.log", "查看错误日志"), main_window)
    log_action.triggered.connect(main_window._open_log_directory)
    help_menu.addAction(log_action)

    # 内存监控
    monitor_action = QAction(
        tr("menu.help.memory_monitor", "内存监控"), main_window
    )
    monitor_action.triggered.connect(main_window._show_memory_monitor)
    help_menu.addAction(monitor_action)

    help_menu.addSeparator()

    # 云存储设置（由「WebDAV 设置」更名，实际支持 WebDAV / OneDrive / Google Drive）
    cloud_action = QAction(
        tr("menu.help.webdav_settings", "☁️ 云存储设置"), main_window
    )
    cloud_action.triggered.connect(main_window._show_webdav_settings)
    help_menu.addAction(cloud_action)

    # AI 设置（服务商 / Key / 地址 / 模型 / 测试连接）。
    # 之前 AI 功能没有任何可视化配置入口，用户得手动改 settings.json。
    ai_action = QAction(
        tr("menu.help.ai_settings", "🤖 AI 设置"), main_window
    )
    ai_action.setToolTip("配置 AI 大纲/讲稿使用的服务商与 API Key")
    ai_action.triggered.connect(main_window._show_ai_settings)
    help_menu.addAction(ai_action)

    # 立即同步
    sync_action = QAction(tr("cmd.sync_now", "立即同步"), main_window)
    sync_action.triggered.connect(main_window._sync_now)
    help_menu.addAction(sync_action)

    # P1：同步目录默认是空的，用户不知道该把文件放哪 —— 给个明确入口
    add_sync_action = QAction(
        tr("cmd.add_to_sync", "把当前文档加入同步目录"), main_window
    )
    add_sync_action.setToolTip("复制当前文件到云同步目录，下次同步会上传它")
    add_sync_action.triggered.connect(main_window._add_current_to_sync_dir)
    help_menu.addAction(add_sync_action)

    # R6：备份与恢复（本地历史版本；WPS 有"备份中心"，我们原先只有自动保存）
    backup_action = QAction(
        tr("menu.help.backup_center", "🗂️ 备份与恢复"), main_window
    )
    backup_action.setToolTip("查看历史版本、恢复、立即备份")
    backup_action.triggered.connect(main_window._show_backup_center)
    help_menu.addAction(backup_action)

    backup_now_action = QAction(
        tr("cmd.backup_now", "立即备份当前文件"), main_window
    )
    backup_now_action.triggered.connect(main_window._backup_now)
    help_menu.addAction(backup_now_action)

    help_menu.addSeparator()

    # ⚠️ 2026-10-15：原「📱 移动端下载」菜单项已**移除**（审计报告 §1.2）。
    # 它的实现只是 `webbrowser.open("https://github.com/TomJerryGit/beeoffice/releases")`
    # —— 没有任何版本比较/下载/校验，而且该仓库**实测 HTTP 404**，
    # 用户点到的是一条死链。留一个"点了就报错/跳到空页面"的菜单项比没有更伤信任。
    # 「移动端查看」（下面是真功能：本机 HTTP 服务 + 手机浏览器看文档）保留。

    # 移动端查看
    mobile_view_action = QAction(
        tr("menu.help.mobile_view", "📱 移动端查看"), main_window
    )
    mobile_view_action.setToolTip(
        "用手机浏览器查看当前文档（需要电脑与手机在同一局域网）"
    )
    mobile_view_action.triggered.connect(main_window._start_mobile_server)
    help_menu.addAction(mobile_view_action)

    # 插件市场
    plugin_market_action = QAction(
        tr("menu.help.plugin_market", "🔌 插件市场"), main_window
    )
    plugin_market_action.triggered.connect(main_window._show_plugin_market)
    help_menu.addAction(plugin_market_action)

    # ==================== 插件菜单注册 ====================
    _register_plugin_menus(main_window, menu_bar)