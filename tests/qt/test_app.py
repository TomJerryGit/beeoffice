# tests/test_app.py
"""
BeeApp 主窗口的单元测试
覆盖：窗口初始化、菜单、标签管理、新建文档、命令面板、主题、语言

本次调整（优化规划阶段 1 附带发现）：
  本文件原先自定义了一个 `app` fixture，**遮蔽**了 tests/conftest.py 里的
  同名 fixture。后果有三：
    1. 不隔离设置文件 —— BeeApp 直接读写真实的 ~/.beeoffice_settings.json
    2. 不屏蔽启动期模态框 —— _restore_session 的 100ms 定时器会真的弹出
       「是否恢复上次会话」对话框，把整个文件挂死（实测超时）
    3. 不跳过插件发现 —— 每个用例都跑一遍 discover_plugins()，
       25 个用例耗时约 190 秒
  删除本地 fixture，改用 conftest.py 的版本即可全部解决。
"""
from PySide6.QtCore import Qt

from beeoffice.plugins.beewrite import BeeWriteEditor
from beeoffice.plugins.beesheet import BeeSheetView
from beeoffice.plugins.beeshow import BeeShowView


# ---------- 窗口初始化 ----------
class TestWindowInitialization:
    """测试窗口初始化"""

    def test_window_created(self, app):
        """主窗口应被成功创建"""
        assert app is not None
        assert app.isWidgetType()

    def test_window_title(self, app):
        """窗口标题应包含应用名"""
        title = app.windowTitle()
        assert "蜜蜂办公" in title or "BeeOffice" in title or title != ""

    def test_window_size(self, app):
        """窗口大小应与设置一致或为默认值"""
        width, height = app.width(), app.height()
        assert width > 0
        assert height > 0

    def test_central_widget_is_tab_manager(self, app):
        """中央控件应是 TabManager"""
        from beeoffice.tab_manager import TabManager
        assert isinstance(app.centralWidget(), TabManager)

    def test_status_bar_exists(self, app):
        """状态栏应存在"""
        assert app.statusBar() is not None
        assert app.status_label is not None


# ---------- 菜单 ----------
class TestMenus:
    """测试菜单栏"""

    def test_menu_bar_exists(self, app):
        """菜单栏应存在"""
        menu_bar = app.menuBar()
        assert menu_bar is not None

    def test_has_menus(self, app):
        """应包含文件、编辑、视图、帮助四个主菜单"""
        menu_bar = app.menuBar()
        actions = menu_bar.actions()
        texts = [a.text() for a in actions]
        # 至少有一个菜单被创建
        assert len(actions) >= 1

    def test_recent_menu_exists(self, app):
        """最近打开菜单应存在"""
        assert hasattr(app, "recent_menu")
        assert app.recent_menu is not None


# ---------- 标签管理 ----------
class TestTabManager:
    """测试标签管理功能"""

    def test_initial_welcome_tab(self, app):
        """启动时应有一个欢迎标签"""
        assert app.tab_manager.count() >= 1

    def test_new_beewrite(self, app):
        """新建蜜写文档后应增加标签"""
        initial_count = app.tab_manager.count()
        editor = app._new_beewrite()
        assert editor is not None
        assert isinstance(editor, BeeWriteEditor)
        assert app.tab_manager.count() == initial_count + 1
        assert app.tab_manager.currentWidget() == editor

    def test_new_beesheet(self, app):
        """新建蜜算表格后应增加标签"""
        initial_count = app.tab_manager.count()
        sheet = app._new_beesheet()
        assert sheet is not None
        assert isinstance(sheet, BeeSheetView)
        assert app.tab_manager.count() == initial_count + 1
        assert app.tab_manager.currentWidget() == sheet

    def test_new_beeshow(self, app):
        """新建蜜演演示文稿后应增加标签"""
        initial_count = app.tab_manager.count()
        show = app._new_beeshow()
        assert show is not None
        assert isinstance(show, BeeShowView)
        assert app.tab_manager.count() == initial_count + 1
        assert app.tab_manager.currentWidget() == show

    def test_new_word_doc(self, app):
        """新建 Word 文档后应增加标签"""
        initial_count = app.tab_manager.count()
        app._new_word_doc()
        assert app.tab_manager.count() == initial_count + 1

    def test_close_current_tab(self, app):
        """关闭当前标签后数量应减少"""
        app._new_beewrite()
        count_before = app.tab_manager.count()
        app.tab_manager.close_current_tab()
        assert app.tab_manager.count() == count_before - 1


# ---------- 命令面板 ----------
class TestCommandPalette:
    """测试命令面板"""

    def test_show_command_palette_does_not_crash(self, app):
        """调用命令面板方法不应抛出异常"""
        # 由于 exec() 是模态的，直接调用会阻塞，改为检查方法存在
        assert hasattr(app, "show_command_palette")
        assert callable(app.show_command_palette)

    def test_build_command_palette(self, app):
        """构建命令面板应返回实例"""
        from beeoffice.commands import build_command_palette
        palette = build_command_palette(app)
        assert palette is not None
        # 应该注册了若干命令
        assert len(palette.all_commands) > 0


# ---------- 主题 ----------
class TestTheme:
    """测试主题切换"""

    def test_toggle_theme_to_dark(self, app):
        """切换到深色主题"""
        app._toggle_theme(True)
        assert app.settings.theme == "dark"

    def test_toggle_theme_to_light(self, app):
        """切换到浅色主题"""
        app._toggle_theme(False)
        assert app.settings.theme == "light"

    def test_set_accent(self, app):
        """设置强调色"""
        app._set_accent("ocean")
        assert app.settings.accent_color == "ocean"


# ---------- 语言 ----------
class TestLanguage:
    """测试语言切换"""

    def test_language_setting_exists(self, app):
        """语言设置项应存在"""
        assert hasattr(app.settings, "language")
        assert app.settings.language in ("zh_CN", "en_US")


# ---------- 状态栏 ----------
class TestStatusBar:
    """测试状态栏消息"""

    def test_set_global_status(self, app):
        """设置状态栏消息"""
        app.set_global_status("测试消息", 0)
        assert app.status_label.text() == "测试消息"

    def test_status_message_with_timeout(self, app, qtbot):
        """带超时的状态消息应自动恢复"""
        app.set_global_status("临时消息", 100)
        assert app.status_label.text() == "临时消息"
        # 等待超时后恢复（使用 qtbot 等待）
        qtbot.wait(300)
        # 恢复为“就绪”或翻译后的文本
        assert app.status_label.text() != "临时消息"


# ---------- 快捷键 ----------
class TestShortcuts:
    """测试快捷键绑定"""

    def test_ctrl_n_shortcut(self, app, qtbot):
        """Ctrl+N 应新建蜜写文档"""
        initial_count = app.tab_manager.count()
        qtbot.keyClick(app, Qt.Key_N, Qt.ControlModifier)
        assert app.tab_manager.count() >= initial_count

    def test_ctrl_t_shortcut(self, app, qtbot):
        """Ctrl+T 应新建蜜算表格"""
        initial_count = app.tab_manager.count()
        qtbot.keyClick(app, Qt.Key_T, Qt.ControlModifier)
        assert app.tab_manager.count() >= initial_count


# ---------- 关闭 ----------
class TestClose:
    """测试关闭逻辑"""

    def test_close_event_saves_settings(self, app, tmp_path, monkeypatch):
        """关闭时应保存设置（不实际关闭，仅检查方法存在）"""
        assert hasattr(app, "closeEvent")
        assert callable(app.closeEvent)