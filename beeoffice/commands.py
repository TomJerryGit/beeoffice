# beeoffice/commands.py
"""
命令面板命令注册中心：集中注册所有内置命令和插件命令

i18n（v5.1）：命令名与描述全部走 tr()。
    约定：key 为 `cmd.palette.<slug>`，中文作为默认值写在代码里，
    英文放在 locales/en_US.json。缺 key 时 tr() 回退到中文默认值，
    因此**新增命令不会因为忘记加翻译而报错**。
"""
import logging

from beeoffice.command_palette import CommandPalette
from beeoffice.i18n import tr


# (slug, 中文命令名, 中文描述, 主窗口方法名)
BUILTIN_COMMANDS = [
    # ---------- 文件 ----------
    ("new_md", "新建 Markdown", "创建一个蜜写文档", "_new_beewrite"),
    ("new_word", "新建 Word 文档", "创建一个可直接导出为 Word 的文档", "_new_word_doc"),
    ("new_sheet", "新建表格", "创建一个蜜算表格", "_new_beesheet"),
    ("new_show", "新建幻灯片", "创建一个蜜演演示文稿", "_new_beeshow"),
    ("open", "打开文件", "打开本地文件", "tab_manager.open_file"),
    ("save", "保存文件", "保存当前文档", "_save_current"),
    ("save_as", "另存为", "将文件保存到新位置", "_save_as_current"),
    ("save_template", "保存为模板", "将当前文档保存为模板", "_save_as_template"),
    ("from_template", "从模板新建", "选择模板创建新文档", "_show_template_picker"),

    # ---------- 导出 ----------
    ("export_docx", "导出 DOCX", "导出为 Word 文档", "_export_docx"),
    ("export_pdf", "导出 PDF", "导出为 PDF 文件", "_export_pdf"),
    ("export_html", "导出 HTML", "导出为网页文件", "_export_html"),
    ("report", "生成报告", "一键将模板+数据源导出为 PDF", "_generate_report"),
    ("export_pptx", "导出 PPTX", "导出幻灯片为 PPTX", "_export_beeshow_pptx"),
    ("batch_docx2md", "批量 DOCX 转 MD", "批量转换 DOCX 为 Markdown", "_batch_docx_to_md"),
    ("batch_md2docx", "批量 MD 转 DOCX", "批量转换 Markdown 为 DOCX", "_batch_md_to_docx"),

    # ---------- 蜜写 ----------
    ("find", "查找替换", "在当前文档中查找替换", "_find_current"),
    ("ai_continue", "AI 续写", "基于当前文本续写", "_ai_continue"),
    ("ai_polish", "AI 润色", "润色选中文本", "_ai_polish"),
    ("ai_summarize", "AI 总结", "总结当前文档", "_ai_summarize"),

    # ---------- 蜜算 ----------
    ("analyze", "智能数据分析", "分析当前选中数据", "_analyze_current_sheet"),
    ("nl_formula", "自然语言生成公式", "用中文指令生成公式", "_nl_formula"),
    ("link_sheet", "关联表格到文档", "将当前蜜算数据绑定到蜜写", "_link_sheet_to_write"),
    ("play_macro", "播放宏", "执行已录制的宏", "_play_macro"),
    ("record_macro", "录制宏", "开始/停止录制宏", "_toggle_macro"),

    # ---------- 蜜演 ----------
    ("play_slides", "播放幻灯片", "全屏播放 (F5)", "_play_beeshow"),

    # ---------- PDF ----------
    ("pdf_annotate", "PDF 批注", "打开 PDF 批注工具", "_open_pdf_annotator"),

    # ---------- 云同步 ----------
    ("cloud_settings", "WebDAV 设置", "配置云同步", "_show_webdav_settings"),
    ("sync_now", "立即同步", "手动触发云同步", "_sync_now"),

    # ---------- 工具 ----------
    ("memory", "内存监控", "查看内存使用情况", "_show_memory_monitor"),
    ("shortcuts", "快捷键帮助", "查看所有快捷键", "_show_shortcuts"),
    ("plugin_market", "插件市场", "浏览和安装插件", "_show_plugin_market"),
    ("mobile", "移动端查看", "启动 HTTP 服务供手机访问", "_start_mobile_server"),
]


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
                    logging.error(
                        f"插件 {getattr(plugin, 'name', '未知')} 注册命令失败: {e}"
                    )

    return palette


def _resolve_target(parent, path: str):
    """把 "tab_manager.open_file" 这种点号路径解析成可调用对象。"""
    obj = parent
    for part in path.split("."):
        obj = getattr(obj, part)
    return obj


def _register_builtin_commands(palette, parent):
    """注册内置命令到命令面板（名称/描述走 i18n）"""
    for slug, zh_name, zh_desc, target in BUILTIN_COMMANDS:
        name = tr(f"cmd.palette.{slug}", zh_name)
        desc = tr(f"cmd.palette.{slug}_desc", zh_desc)
        try:
            callback = _resolve_target(parent, target)
        except AttributeError as e:
            # 某个功能尚未挂载时跳过，而不是让整个面板构建失败
            logging.warning(f"命令 {slug} 的目标方法不存在: {e}")
            continue
        palette.register_command(name, desc, callback)
