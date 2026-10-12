# beeoffice/commands.py
"""
命令面板命令注册中心：集中注册所有内置命令和插件命令
"""
import logging

from beeoffice.command_palette import CommandPalette


def build_command_palette(parent):
    """
    构建命令面板：注册所有内置命令，并遍历插件注册插件命令
    :param parent: 主窗口实例（BeeApp）
    :return: 已注册命令的 CommandPalette 实例
    """
    palette = CommandPalette(parent)

    # 注册内置命令
    _register_builtin_commands(palette, parent)

    # 遍历插件，让插件注册自己的命令
    if hasattr(parent, 'plugin_manager') and parent.plugin_manager:
        for plugin in parent.plugin_manager.plugins:
            if hasattr(plugin, 'register_commands'):
                try:
                    plugin.register_commands(palette)
                except Exception as e:
                    logging.error(f"插件 {getattr(plugin, 'name', '未知')} 注册命令失败: {e}")

    return palette


def _register_builtin_commands(palette, parent):
    """注册内置命令到命令面板"""
    # ---------- 文件相关 ----------
    palette.register_command("新建 Markdown", "创建一个蜜写文档", parent._new_beewrite)
    palette.register_command("新建 Word 文档", "创建一个可直接导出为 Word 的文档", parent._new_word_doc)
    palette.register_command("新建表格", "创建一个蜜算表格", parent._new_beesheet)
    palette.register_command("新建幻灯片", "创建一个蜜演演示文稿", parent._new_beeshow)
    palette.register_command("打开文件", "打开本地文件", parent.tab_manager.open_file)
    palette.register_command("保存文件", "保存当前文档", parent._save_current)
    palette.register_command("另存为", "将文件保存到新位置", parent._save_as_current)
    palette.register_command("保存为模板", "将当前文档保存为模板", parent._save_as_template)
    palette.register_command("从模板新建", "选择模板创建新文档", parent._show_template_picker)

    # ---------- 导出相关 ----------
    palette.register_command("导出 DOCX", "导出为 Word 文档", parent._export_docx)
    palette.register_command("导出 PDF", "导出为 PDF 文件", parent._export_pdf)
    palette.register_command("生成报告", "一键将模板+数据源导出为 PDF", parent._generate_report)
    palette.register_command("导出 PPTX", "导出幻灯片为 PPTX", parent._export_beeshow_pptx)
    palette.register_command("批量 DOCX 转 MD", "批量转换 DOCX 为 Markdown", parent._batch_docx_to_md)
    palette.register_command("批量 MD 转 DOCX", "批量转换 Markdown 为 DOCX", parent._batch_md_to_docx)

    # ---------- 蜜写相关 ----------
    palette.register_command("查找替换", "在当前文档中查找替换", parent._find_current)
    palette.register_command("AI 续写", "基于当前文本续写", parent._ai_continue)
    palette.register_command("AI 润色", "润色选中文本", parent._ai_polish)
    palette.register_command("AI 总结", "总结当前文档", parent._ai_summarize)

    # ---------- 蜜算相关 ----------
    palette.register_command("智能数据分析", "分析当前选中数据", parent._analyze_current_sheet)
    palette.register_command("自然语言生成公式", "用中文指令生成公式", parent._nl_formula)
    palette.register_command("关联表格到文档", "将当前蜜算数据绑定到蜜写", parent._link_sheet_to_write)

    # ---------- 蜜演相关 ----------
    palette.register_command("播放幻灯片", "全屏播放 (F5)", parent._play_beeshow)

    # ---------- PDF 相关 ----------
    palette.register_command("PDF 批注", "打开 PDF 批注工具", parent._open_pdf_annotator)

    # ---------- 云同步相关 ----------
    palette.register_command("WebDAV 设置", "配置云同步", parent._show_webdav_settings)
    palette.register_command("立即同步", "手动触发云同步", parent._sync_now)

    # ---------- 工具相关 ----------
    palette.register_command("内存监控", "查看内存使用情况", parent._show_memory_monitor)
    palette.register_command("快捷键帮助", "查看所有快捷键", parent._show_shortcuts)
    palette.register_command("插件市场", "浏览和安装插件", parent._show_plugin_market)
    palette.register_command("移动端查看", "启动 HTTP 服务供手机访问", parent._start_mobile_server)