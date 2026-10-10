# tests/test_smoke_beeshow.py
"""
蜜演 BeeShow 烟雾测试

覆盖：
  - A1：所有 beeshow_*.py 模块可导入
  - A2：BeeShowView 及各 Mixin 可实例化
  - A3：关键方法存在性检查

设计目标：
  防止本次 QTimer 导入错误这类"运行时才崩"的问题再次发生。

v5.2 B1 修复：
  - test_mro_order 断言修正：
    原实现错误地假设 QWidget 在 MRO 倒数第二个位置，
    实际 QWidget 后面还有 QObject / QPaintDevice / Object / object 四个类。
    现在改为检查：
      1. BeeShowView 是第一个
      2. 所有 Mixin 在 QWidget 之前
      3. QWidget 之后必须有 QObject

用法：
  pytest tests/test_smoke_beeshow.py -v
"""
import importlib
import pkgutil
import pytest


# ==================== A1：导入烟雾测试 ====================
class TestImportSmoke:
    """A1：所有 beeshow_*.py 模块必须能导入"""

    def test_all_beeshow_modules_importable(self):
        """遍历 beeoffice.plugins 下所有 beeshow 开头的模块，逐个导入"""
        import beeoffice.plugins as plugins_pkg

        failed = []
        for mod_info in pkgutil.iter_modules(plugins_pkg.__path__):
            name = mod_info.name
            if not name.startswith("beeshow"):
                continue
            full_name = f"beeoffice.plugins.{name}"
            try:
                importlib.import_module(full_name)
            except Exception as e:
                failed.append((full_name, repr(e)))

        if failed:
            msg = "\n".join(f"  {n} → {e}" for n, e in failed)
            pytest.fail(f"以下模块导入失败：\n{msg}")

    def test_main_module_importable(self):
        """主模块 beeshow 必须可导入"""
        importlib.import_module("beeoffice.plugins.beeshow")

    def test_constants_importable(self):
        """常量模块必须可导入"""
        importlib.import_module("beeoffice.plugins.beeshow_constants")

    def test_key_classes_importable(self):
        """关键类必须能 import"""
        from beeoffice.plugins.beeshow import BeeShowView
        from beeoffice.plugins.beeshow_constants import (
            SLIDE_THEMES, ICON_LIBRARY, TEMPLATE_LIBRARY,
            LAYOUTS, LAYOUT_CSS, _PlayWindow,
        )
        assert BeeShowView is not None
        assert len(SLIDE_THEMES) >= 7
        assert len(LAYOUTS) >= 10


# ==================== A2：实例化烟雾测试 ====================
class TestInstantiateSmoke:
    """A2：BeeShowView 必须能实例化"""

    def test_beeshow_view_instantiable(self, qtbot):
        """BeeShowView() 能正常创建"""
        from beeoffice.plugins.beeshow import BeeShowView
        view = BeeShowView()
        qtbot.addWidget(view)
        assert view is not None

    def test_beeshow_view_has_key_attributes(self, qtbot):
        """实例化后关键属性都已初始化"""
        from beeoffice.plugins.beeshow import BeeShowView
        view = BeeShowView()
        qtbot.addWidget(view)

        required_attrs = [
            # 拆分时的基础状态
            "_slides_html", "_slides_md", "_current_slide",
            "_current_theme", "_is_playing", "_speaker_notes",
            "_slide_titles", "_export_views", "_play_window",
            # 任务 4.1 版本历史
            "_slide_history",
            # 任务 4.2 评论
            "_slide_comments", "_comment_next_id", "_comment_panel",
            # 任务 4.3 同步
            "_sync_server", "_sync_enabled", "_sync_url",
            # 任务 2.2 主 splitter
            "_main_splitter",
            # 任务 1.1 AI 服务
            "_ai_service",
            # 任务 3.1 PPTX 引擎
            "_pptx_engine",
        ]
        missing = [a for a in required_attrs if not hasattr(view, a)]
        if missing:
            pytest.fail(f"以下属性未初始化：{missing}")

    def test_beeshow_view_has_key_widgets(self, qtbot):
        """实例化后关键 UI 控件都已创建"""
        from beeoffice.plugins.beeshow import BeeShowView
        view = BeeShowView()
        qtbot.addWidget(view)

        required_widgets = [
            "_editor", "_notes_editor", "_preview", "_thumb_list",
            "_theme_combo", "_play_btn", "_anim_combo",
            "_slide_label", "_timer_label", "_rehearsal_label",
        ]
        missing = [w for w in required_widgets if not hasattr(view, w)]
        if missing:
            pytest.fail(f"以下控件未创建：{missing}")

    def test_initial_content_loaded(self, qtbot):
        """初始欢迎页应已写入编辑器"""
        from beeoffice.plugins.beeshow import BeeShowView
        view = BeeShowView()
        qtbot.addWidget(view)
        text = view._editor.toPlainText()
        assert "欢迎使用蜜演" in text
        assert len(view._slides_html) >= 1


# ==================== A3：Mixin 方法存在性 ====================
class TestMixinMethodsExist:
    """A3：所有 Mixin 的入口方法都必须存在"""

    def test_split_base_methods(self, qtbot):
        """拆分时的 8 个文件对应的方法"""
        from beeoffice.plugins.beeshow import BeeShowView
        view = BeeShowView()
        qtbot.addWidget(view)

        methods = [
            # ToolbarMixin
            "_build_main_toolbar", "_build_info_bar",
            "_build_splitter", "_build_shortcuts",
            # SlideMixin
            "_on_editor_changed", "_update_preview", "_md_to_html",
            "_update_thumbnails", "_show_slide",
            "_on_slides_reordered", "_add_slide", "_delete_slide",
            # PlayMixin
            "_start_play", "_stop_play", "_show_play_slide",
            "_start_presenter_mode", "keyPressEvent",
            "toggle_rehearsal", "start_rehearsal", "stop_rehearsal",
            # ExportMixin
            "_export_pptx", "_export_pdf", "_export_html",
            "_export_images", "_export_gif",
            # NotesMixin
            "edit_current_notes", "add_speaker_notes", "_set_status",
            # AIMixin
            "_show_icon_picker", "_show_template_menu",
            "_ai_generate_outline", "_import_markdown",
            "_generate_qrcode",
        ]
        missing = [m for m in methods if not hasattr(view, m)]
        if missing:
            pytest.fail(f"以下基础方法缺失：{missing}")

    def test_v51_new_methods(self, qtbot):
        """v5.1 新增的 14 个任务的入口方法"""
        from beeoffice.plugins.beeshow import BeeShowView
        view = BeeShowView()
        qtbot.addWidget(view)

        methods = [
            # 任务 1.1 AI 大纲
            "_ai_generate_outline",
            # 任务 1.2 AI 讲稿
            "_ai_generate_notes", "_ai_generate_all_notes",
            # 任务 1.3 AI 配图
            "_show_image_suggester", "_show_image_picker_dialog",
            "_insert_image_url",
            # 任务 2.1 版式
            "_show_layout_picker", "_apply_layout", "_get_layout_css",
            # 任务 2.2 元素编辑
            "_on_element_edit_applied",
            # 任务 2.3 图片编辑
            "_on_image_edit_applied",
            # 任务 3.1 / 3.2 PPTX（通过 _export_pptx 间接）
            "_export_pptx_legacy",
            # 任务 4.1 版本历史
            "_save_snapshot", "_show_history_panel",
            "_restore_last_snapshot", "_clear_history",
            # 任务 4.2 评论
            "_add_comment", "_show_comment_panel",
            "_refresh_comment_panel", "_edit_comment",
            "_delete_comment", "_toggle_comment_resolved",
            # 任务 4.3 同步
            "_init_sync_state", "_start_sync_mode",
            "_stop_sync_mode", "_broadcast_slide",
            "_broadcast_laser", "_broadcast_theme",
            "_cleanup_sync",
            # 任务 5.1 动态数字
            "_process_dynamic_numbers", "_get_dynamic_number_js",
            "_render_dynamic_numbers_for_export",
            # 任务 5.2 平滑动画
            "_process_morph_ids", "_get_morph_js",
            "_is_morph_mode", "_get_morph_ids_for_current_slide",
            # 任务 5.3 视频嵌入
            "_process_videos",
            "_copy_videos_for_html_export",
            "_replace_videos_with_posters",
        ]
        missing = [m for m in methods if not hasattr(view, m)]
        if missing:
            msg = "\n".join(f"  - {m}" for m in missing)
            pytest.fail(f"以下 v5.1 方法缺失：\n{msg}")

    def test_mro_order(self):
        """
        检查 MRO 顺序：
          - BeeShowView 必须在第一个
          - 所有 Mixin 都必须在 QWidget 之前
          - QWidget 必须在最后（在 Qt 内部基类之前）

        v5.2 B1 修复：
          原实现断言 `widget_idx == len(mro) - 2`，
          假设 QWidget 是倒数第二个。但实际 MRO 中 QWidget 后还有
          QObject / QPaintDevice / Object / object 四个类，
          所以这个断言是错的。
          现在改为：
            1. BeeShowView 是第一个
            2. QWidget 在 MRO 里
            3. 所有 Mixin 都在 QWidget 之前
            4. QWidget 之后必有 QObject
        """
        from beeoffice.plugins.beeshow import BeeShowView
        mro = [c.__name__ for c in BeeShowView.__mro__]

        # 1. BeeShowView 是第一个
        assert mro[0] == "BeeShowView"

        # 2. QWidget 必须存在
        assert "QWidget" in mro, f"MRO 中缺少 QWidget：{mro}"

        # 3. 所有 Mixin 都在 QWidget 之前
        widget_idx = mro.index("QWidget")
        required_mixins = [
            "ToolbarMixin", "SlideMixin", "LayoutMixin", "TableMixin",
            "PlayMixin", "ExportMixin", "NotesMixin", "HistoryMixin",
            "DynamicMixin", "VideoMixin", "CommentMixin", "SyncMixin",
            "MorphMixin", "AIMixin",
        ]
        for mixin in required_mixins:
            assert mixin in mro, f"Mixin {mixin} 未在 MRO 中"
            mixin_idx = mro.index(mixin)
            assert mixin_idx < widget_idx, (
                f"{mixin} 应在 QWidget 之前，"
                f"实际位置 {mixin_idx} vs QWidget {widget_idx}"
            )

        # 4. QWidget 之后必须有 QObject
        after_widget = mro[widget_idx + 1:]
        assert "QObject" in after_widget, (
            f"QWidget 之后应有 QObject，实际：{after_widget}"
        )


# ==================== A4（额外）：核心操作烟雾测试 ====================
class TestCoreOperationsSmoke:
    """补充：核心操作必须不崩"""

    def test_update_preview_works(self, qtbot):
        """_update_preview 能正常解析内容"""
        from beeoffice.plugins.beeshow import BeeShowView
        view = BeeShowView()
        qtbot.addWidget(view)

        view._editor.setPlainText(
            "# 测试标题\n\n- 要点1\n- 要点2\n\n---\n\n## 第二页\n\n内容"
        )
        view._update_preview()
        assert len(view._slides_html) == 2

    def test_save_snapshot_works(self, qtbot):
        """版本历史快照能保存"""
        from beeoffice.plugins.beeshow import BeeShowView
        view = BeeShowView()
        qtbot.addWidget(view)

        view._editor.setPlainText("# 测试")
        view._update_preview()
        view._save_snapshot(force=True)
        assert len(view._slide_history) >= 1

    def test_dynamic_number_processing(self, qtbot):
        """动态数字语法能解析"""
        from beeoffice.plugins.beeshow import BeeShowView
        view = BeeShowView()
        qtbot.addWidget(view)

        result = view._process_dynamic_numbers(
            "销售额 {{number: 12345}} 元"
        )
        assert "dynamic-number" in result
        assert "data-to=\"12345\"" in result

    def test_layout_css_returns_string(self, qtbot):
        """版式 CSS 返回非空字符串"""
        from beeoffice.plugins.beeshow import BeeShowView
        view = BeeShowView()
        qtbot.addWidget(view)

        css = view._get_layout_css()
        assert isinstance(css, str)
        assert len(css) > 100

    def test_table_editor_methods_exist(self, qtbot):
        """
        v5.2 B1：表格编辑器方法存在性

        这是为了防止 `beeshow.py` 忘记加 TableMixin 时崩溃。
        """
        from beeoffice.plugins.beeshow import BeeShowView
        view = BeeShowView()
        qtbot.addWidget(view)

        methods = [
            "_show_table_editor",
            "_edit_current_table",
            "_extract_current_table",
            "_insert_table_md",
            "_replace_current_table",
            "_show_table_menu",
        ]
        missing = [m for m in methods if not hasattr(view, m)]
        if missing:
            pytest.fail(f"表格编辑器方法缺失：{missing}")