# beeoffice/menus.py
"""
菜单构建模块：集中定义主窗口的所有菜单和动作

优化要点：
  1. 所有菜单项接入 i18n（tr 函数），与 locales/zh_CN.json、en_US.json 键名对齐
  2. 动态发现可用语言包，避免硬编码语言列表
  3. 强调色子菜单使用 theme.accent.* 翻译键，并显示当前勾选状态
  4. 补充缺失菜单项：从模板新建、保存为模板、导出子菜单、生成报告、
     PDF 批注、批量转换、AI 辅助、宏、关联表格到文档等
  5. 新增「工具」菜单，集中放置文档处理类功能
  6. 撤销/重做动作连接到当前控件（QPlainTextEdit / QTextEdit）
  7. 新增插件菜单注册入口（调用 Plugin.register_menus 钩子）
  8. 「WebDAV 设置」更名为「云存储设置」，与实际能力一致（支持 WebDAV / OneDrive / Google Drive）
"""
import logging

from PySide6.QtGui import QAction, QKeySequence

from beeoffice.i18n import tr, I18nManager
from beeoffice.theme import Theme


# ==================== 常量 ====================
# 语言代码 → 显示名（语言包中若存在 app.lang_name 键，可优先使用）
_LANGUAGE_DISPLAY_NAMES = {
    "zh_CN": "中文",
    "en_US": "English",
}

# 默认语言包列表（当无法从 I18nManager 获取时回退）
_DEFAULT_LANGUAGES = ["zh_CN", "en_US"]


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


def _build_language_menu(main_window, parent_menu):
    """
    构建语言子菜单（动态发现可用语言包）
    :param main_window: BeeApp 实例
    :param parent_menu: 挂载到的父菜单（视图菜单）
    """
    lang_menu = parent_menu.addMenu("🌐 " + tr("menu.view.language", "语言"))

    try:
        i18n = I18nManager()
        available = list(i18n._translations.keys())
    except Exception as e:
        logging.error(f"获取语言列表失败: {e}")
        available = []

    if not available:
        available = _DEFAULT_LANGUAGES

    current_lang = getattr(main_window.settings, "language", "zh_CN")

    for code in sorted(available):
        display = _LANGUAGE_DISPLAY_NAMES.get(code, code)
        action = QAction(display, main_window)
        action.setCheckable(True)
        action.setChecked(current_lang == code)
        action.triggered.connect(
            lambda checked=False, c=code: main_window._switch_language(c)
        )
        lang_menu.addAction(action)


def _build_accent_menu(main_window, parent_menu):
    """
    构建强调色子菜单（使用 i18n，并显示当前勾选状态）
    :param main_window: BeeApp 实例
    :param parent_menu: 挂载到的父菜单（视图菜单）
    """
    accent_menu = parent_menu.addMenu(tr("menu.view.accent", "强调色"))
    current_accent = getattr(main_window.settings, "accent_color", "amber")

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

    # ---- 蜜算专项 ----
    analyze_action = tools_menu.addAction(
        tr("cmd.analyze_sheet", "智能数据分析")
    )
    analyze_action.triggered.connect(main_window._analyze_current_sheet)

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

    # ==================== 视图菜单 ====================
    view_menu = menu_bar.addMenu(tr("menu.view", "视图"))

    # 深色主题切换
    theme_action = QAction(
        tr("menu.view.dark_theme", "深色主题"), main_window, checkable=True
    )
    theme_action.setChecked(main_window.settings.theme == "dark")
    theme_action.triggered.connect(main_window._toggle_theme)
    view_menu.addAction(theme_action)

    # 强调色子菜单
    _build_accent_menu(main_window, view_menu)

    view_menu.addSeparator()

    # 分屏
    split_action = QAction(tr("menu.view.split", "分屏"), main_window)
    split_action.setShortcut(QKeySequence("Ctrl+\\"))
    split_action.triggered.connect(main_window.tab_manager.split_with_current)
    view_menu.addAction(split_action)

    view_menu.addSeparator()

    # 语言子菜单（动态发现可用语言包）
    _build_language_menu(main_window, view_menu)

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