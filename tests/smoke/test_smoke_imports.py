# tests/test_smoke_imports.py
"""
导入冒烟测试

目的：
  1. 保证所有关键模块能被成功 import（无语法错误 / 无循环依赖）
  2. 提升覆盖率：import 会执行模块顶层代码（类定义、常量定义）
  3. 作为 CI 的第一道防线：如果某个模块 import 失败，这里会先于其他测试失败

覆盖范围：
  - 核心模块（settings / theme / i18n / utils / ...）
  - 云存储适配器（cloud_sync/*）
  - 云存储工厂 / 设置对话框
  - 模板管理
  - 所有插件模块

排除：
  - beeoffice.app（需要 QApplication，由 test_app.py 覆盖）
  - beeoffice.main（程序入口，由 test_main.py 单独测）

设计：
  - 用 pytest.mark.parametrize 参数化，每个模块独立报告结果
  - 失败时打印模块名 + 错误堆栈，便于定位
  - ImportError 单独处理，让错误信息更清晰
"""
import importlib

import pytest


# ==================== 待测试的模块清单 ====================
MODULES = [
    # ---------- 核心 ----------
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
    "beeoffice.plugin_base",
    "beeoffice.plugin_manager",

    # ---------- 云存储 ----------
    "beeoffice.cloud",
    "beeoffice.cloud_settings",
    "beeoffice.cloud_sync",
    "beeoffice.cloud_sync.base",
    "beeoffice.cloud_sync.webdav",
    "beeoffice.cloud_sync.onedrive",
    "beeoffice.cloud_sync.googledrive",
    "beeoffice.webdav",

    # ---------- 资源 ----------
    "beeoffice.resources",
    "beeoffice.resources.templates",
    "beeoffice.resources.template_manager",

    # ---------- 插件：蜜写 ----------
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

    # ---------- 插件：蜜算 ----------
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
    "beeoffice.plugins.beesheet_chart_mixin",
    "beeoffice.plugins.beesheet_context_menu_mixin",
    "beeoffice.plugins.beesheet_rowcol_mixin",
    "beeoffice.plugins.beesheet_ui_mixin",
    "beeoffice.plugins.beesheet_plugin",

    # ---------- 插件：蜜演 ----------
    "beeoffice.plugins.beeshow",
    "beeoffice.plugins.beeshow_plugin",

    # ---------- 插件：其它 ----------
    "beeoffice.plugins.ai_assist",
    "beeoffice.plugins.bee_export",
    "beeoffice.plugins.nl_formula",
    "beeoffice.plugins.data_binding",
    "beeoffice.plugins.variable_panel",
    "beeoffice.plugins.empty_state",
    "beeoffice.plugins.find_replace",
    "beeoffice.plugins.friendly_errors",
    "beeoffice.plugins.git_manager",
    "beeoffice.plugins.memory_monitor",
    "beeoffice.plugins.onboarding",
    "beeoffice.plugins.plugin_market",
    "beeoffice.plugins.webdav_sync",
]


# ==================== 测试 ====================
@pytest.mark.parametrize("module_name", MODULES)
def test_module_importable(module_name):
    """
    逐个 import 模块，确保无语法错误 / 无循环依赖。

    分类处理：
      - ImportError：进一步区分是"模块不存在"还是"依赖缺失"
      - 其它异常：直接 fail 并显示完整错误
    """
    try:
        importlib.import_module(module_name)
    except ImportError as e:
        # 判断是模块本身问题还是可选依赖问题
        error_msg = str(e)
        if "No module named" in error_msg:
            # 可能是 beeoffice 包未在 sys.path，或者依赖缺失
            pytest.fail(
                f"模块 {module_name} 导入失败（依赖缺失）: {error_msg}"
            )
        else:
            pytest.fail(
                f"模块 {module_name} 导入失败（ImportError）: {error_msg}"
            )
    except SyntaxError as e:
        pytest.fail(
            f"模块 {module_name} 存在语法错误: {e}\n"
            f"  文件: {getattr(e, 'filename', '?')}\n"
            f"  行号: {getattr(e, 'lineno', '?')}"
        )
    except Exception as e:
        pytest.fail(
            f"模块 {module_name} import 时抛出异常: "
            f"{type(e).__name__}: {e}"
        )