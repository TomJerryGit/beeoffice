# tools/check_imports.py
"""
模块导入检查脚本

在 CI 中运行，确保所有关键模块可正常 import。
用法：
    python tools/check_imports.py
"""
import importlib
import sys
import traceback
from pathlib import Path

# 项目根目录加入 sys.path
ROOT = Path(__file__).parent.parent.resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Windows 控制台默认是 GBK，脚本里的 emoji（🐝 等）会直接抛
# UnicodeEncodeError 让整个检查以退出码 1 结束——CI 上会被误判为"导入失败"。
# 这里强制 stdout/stderr 使用 UTF-8 并对无法编码的字符做替换。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 需要检查的模块列表
MODULES_TO_CHECK = [
    # 核心
    "beeoffice.__version__",
    "beeoffice.settings",
    "beeoffice.theme",
    "beeoffice.i18n",
    "beeoffice.utils",
    "beeoffice.icon",
    "beeoffice.shortcuts",
    "beeoffice.crash_handler",
    "beeoffice.async_task",
    "beeoffice.tab_manager",
    "beeoffice.command_palette",
    "beeoffice.commands",
    "beeoffice.menus",
    "beeoffice.mobile",
    "beeoffice.templates",
    "beeoffice.cloud_settings",
    "beeoffice.plugin_base",
    "beeoffice.plugin_manager",
    # 蜜写
    "beeoffice.plugins.beewrite",
    "beeoffice.plugins.beewrite_utils",
    "beeoffice.plugins.beewrite_rich_editor",
    "beeoffice.plugins.beewrite_md_table_dialog",
    "beeoffice.plugins.beewrite_toolbar_mixin",
    "beeoffice.plugins.beewrite_mode_mixin",
    "beeoffice.plugins.beewrite_paragraph_mixin",
    "beeoffice.plugins.beewrite_table_mixin",
    "beeoffice.plugins.beewrite_doc_mixin",
    "beeoffice.plugins.beewrite_export_mixin",
    "beeoffice.plugins.beewrite_comment_mixin",
    "beeoffice.plugins.beewrite_link_mixin",
    "beeoffice.plugins.beewrite_ai_mixin",
    "beeoffice.plugins.beewrite_view_mixin",
    "beeoffice.plugins.beewrite_comment",
    "beeoffice.plugins.beewrite_bookmark",
    "beeoffice.plugins.beewrite_revision",
    "beeoffice.plugins.beewrite_hyperlink",
    "beeoffice.plugins.beewrite_crossref",
    "beeoffice.plugins.beewrite_image",
    "beeoffice.plugins.beewrite_formula",
    "beeoffice.plugins.beewrite_textbox",
    "beeoffice.plugins.beewrite_page_extras",
    "beeoffice.plugins.beewrite_outline",
    "beeoffice.plugins.beewrite_plugin",
    # 蜜算
    "beeoffice.plugins.beesheet",
    "beeoffice.plugins.beesheet_utils",
    "beeoffice.plugins.beesheet_commands",
    "beeoffice.plugins.beesheet_delegate",
    "beeoffice.plugins.beesheet_loaders",
    "beeoffice.plugins.beesheet_engine",
    "beeoffice.plugins.beesheet_model",
    "beeoffice.plugins.beesheet_dialogs",
    "beeoffice.plugins.beesheet_formula_mixin",
    "beeoffice.plugins.beesheet_style_mixin",
    "beeoffice.plugins.beesheet_audit_mixin",
    "beeoffice.plugins.beesheet_data_mixin",
    "beeoffice.plugins.beesheet_plugin",
    # 蜜演
    "beeoffice.plugins.beeshow",
    "beeoffice.plugins.beeshow_plugin",
    # 其它插件
    "beeoffice.plugins.ai_assist",
    "beeoffice.plugins.bee_export",
    "beeoffice.plugins.nl_formula",
    # formula_engine 已删除：旧版实例式公式引擎，生产代码零引用，
    # 且带一处未加固的裸 eval（见 BeeOffice-分析报告.md §3.1）
    "beeoffice.plugins.pdf_annotator",
    "beeoffice.plugins.pdf_annotator_plugin",
    "beeoffice.plugins.plugin_market",
    "beeoffice.plugins.memory_monitor",
    "beeoffice.plugins.onboarding",
    "beeoffice.plugins.friendly_errors",
    "beeoffice.plugins.heading_numbering",
    "beeoffice.plugins.image_utils",
    "beeoffice.plugins.find_replace",
    "beeoffice.plugins.data_binding",
    "beeoffice.plugins.variable_panel",
    "beeoffice.plugins.empty_state",
    # 云存储
    "beeoffice.cloud_sync.base",
    "beeoffice.cloud_sync.webdav",
    "beeoffice.cloud_sync.onedrive",
    "beeoffice.cloud_sync.googledrive",
]


def check_module(module_name: str) -> tuple:
    """
    尝试导入模块
    :return: (success: bool, error_msg: str)
    """
    try:
        importlib.import_module(module_name)
        return True, ""
    except Exception as e:
        tb = traceback.format_exc()
        return False, f"{type(e).__name__}: {e}\n{tb}"


def main():
    print("=" * 60)
    print("  🐝 BeeOffice 模块导入检查")
    print("=" * 60)
    print()

    failed = []
    success_count = 0
    for module_name in MODULES_TO_CHECK:
        ok, err = check_module(module_name)
        if ok:
            print(f"  ✅ {module_name}")
            success_count += 1
        else:
            print(f"  ❌ {module_name}")
            print(f"     {err.splitlines()[0]}")
            failed.append((module_name, err))

    print()
    print("=" * 60)
    print(f"  总数: {len(MODULES_TO_CHECK)}")
    print(f"  成功: {success_count}")
    print(f"  失败: {len(failed)}")
    print("=" * 60)

    if failed:
        print()
        print("失败详情：")
        for module_name, err in failed:
            print()
            print(f"❌ {module_name}")
            print(err)
        sys.exit(1)
    else:
        print()
        print("🎉 所有模块导入成功！")
        sys.exit(0)


if __name__ == "__main__":
    main()