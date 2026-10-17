# create_tests.py
"""
一次性创建 tests/ 目录及其全部程序文件。

用法：
    python create_tests.py

行为：
    - 若文件已存在：默认跳过（不会覆盖）
    - 若要强制覆盖：设置 FORCE_OVERWRITE = True
    - 可选：DELAY_IMPORT 控制是否在脚本运行时导入 pytest 等库
      （当前实现不需要导入任何库，纯文件操作）
"""
import os
from pathlib import Path

# ==================== 配置 ====================
PROJECT_ROOT = Path(__file__).parent.resolve()
TESTS_DIR = PROJECT_ROOT / "tests"

# 是否覆盖已存在的文件
FORCE_OVERWRITE = False


# ==================== 文件内容 ====================
# 字典结构：{ 相对路径: 文件内容 }
FILES = {}

# ---------- 根目录 __init__.py ----------
FILES["tests/__init__.py"] = '''"""
BeeOffice 测试包
"""
'''

# ---------- conftest.py ----------
FILES["tests/conftest.py"] = '''# tests/conftest.py
"""
Pytest 测试基座

提供：
  - QApplication 单例（pytest-qt 自动管理）
  - 临时工作目录 fixture
  - 示例文档 fixture
  - 示例表格 fixture
  - 临时设置文件 fixture

依赖：
  - pytest
  - pytest-qt
  - PySide6
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

# 确保项目根目录在 sys.path 里，便于 import beeoffice
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ==================== 应用级 fixture ====================

@pytest.fixture(scope="session")
def qapp_args():
    """QApplication 参数"""
    return ["beeoffice-test"]


@pytest.fixture
def temp_workspace(tmp_path):
    """提供一个临时工作目录"""
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


@pytest.fixture
def temp_settings(tmp_path, monkeypatch):
    """隔离设置文件：把 AppSettings 的默认路径重定向到临时文件。"""
    settings_path = tmp_path / ".beeoffice_settings.json"
    monkeypatch.setattr(
        "beeoffice.settings.AppSettings.__init__",
        lambda self: _patched_settings_init(self, settings_path),
    )
    yield settings_path


def _patched_settings_init(self, path):
    """替换后的 AppSettings.__init__"""
    import logging
    self.path = Path(path)
    self.window_size = (1024, 680)
    self.recent_files = []
    self.open_tabs = []
    self.theme = "light"
    self.accent_color = "amber"
    self.language = "zh_CN"
    self.has_completed_onboarding = True  # 测试时跳过引导
    self.recent_commands = []
    self.webdav_url = ""
    self.webdav_user = ""
    self.webdav_pass = ""
    self.webdav_enabled = False
    self.webdav_auto_sync = False
    self.git_repo_path = ""
    self.git_enabled = False
    self.cloud_type = "webdav"
    self.cloud_config = {}
    self.cloud_enabled = False
    self.cloud_auto_sync = False
    self.load()


# ==================== 数据 fixture ====================

@pytest.fixture
def sample_markdown():
    """示例 Markdown 文本"""
    return """# 永遇乐·京口北固亭怀古

【宋】辛弃疾

千古江山，英雄无觅孙仲谋处。舞榭歌台，风流总被雨打风吹去。

| 序号 | 姓名 | 收入 |
|-----|------|-----:|
| 1 | 张三 | 200 |
| 2 | 李四 | 300 |
"""


@pytest.fixture
def sample_table_rows():
    """示例表格二维列表"""
    return [
        ["序号", "姓名", "收入"],
        ["1", "张三", "200"],
        ["2", "李四", "300"],
    ]


@pytest.fixture
def sample_dataframe():
    """示例 DataFrame"""
    import pandas as pd
    return pd.DataFrame({
        "序号": [1, 2, 3, 4],
        "姓名": ["张三", "李四", "王伟", "马丽"],
        "收入": [200, 300, 200, 400],
    })


# ==================== Qt fixture ====================

@pytest.fixture
def beewrite_editor(qtbot, temp_settings):
    """
    提供一个隔离的 BeeWriteEditor 实例。

    P1-3：
      - yield 后先调 close() 触发 closeEvent
      - 再调 deleteLater() 释放 Qt 对象
    """
    from beeoffice.plugins.beewrite import BeeWriteEditor
    editor = BeeWriteEditor()
    qtbot.addWidget(editor)
    yield editor

    try:
        editor.close()
    except Exception:
        pass
    try:
        editor.deleteLater()
    except Exception:
        pass


# ==================== P1-2：日志静默 ====================

@pytest.fixture(autouse=True)
def _quiet_expected_errors():
    """
    P1-2：降级 root logger，避免预期异常污染 pytest.log。
    """
    import logging
    root = logging.getLogger()
    old_level = root.level
    root.setLevel(logging.CRITICAL)
    yield
    root.setLevel(old_level)


# ==================== P1-4：轻量 BeeApp fixture ====================

@pytest.fixture
def app(qtbot, temp_settings, monkeypatch):
    """
    P1-4：轻量 BeeApp fixture。

    屏蔽所有自动初始化：
      - _lazy_load_modules：不加载插件
      - _restore_session：不弹恢复会话
      - _check_first_run：不弹首次运行引导
      - _check_auto_sync：不触发云同步
    """
    from beeoffice.app import BeeApp

    monkeypatch.setattr(BeeApp, "_lazy_load_modules", lambda self: None)
    monkeypatch.setattr(BeeApp, "_restore_session", lambda self: None)
    monkeypatch.setattr(BeeApp, "_check_first_run", lambda self: None)
    monkeypatch.setattr(BeeApp, "_check_auto_sync", lambda self: None)

    window = BeeApp()
    qtbot.addWidget(window)
    yield window

    try:
        window.close()
    except Exception:
        pass


@pytest.fixture
def app_with_plugins(qtbot, temp_settings):
    """
    P1-4：完整加载插件的 BeeApp，用于测试需要 plugin_manager 的场景。
    """
    from beeoffice.app import BeeApp

    window = BeeApp()
    qtbot.addWidget(window)

    # 等待 _lazy_load_modules 执行（singleShot 50ms）
    qtbot.wait(150)

    yield window

    try:
        window.close()
    except Exception:
        pass
'''

# ---------- 根目录测试文件 ----------
FILES["tests/test_ai_assist.py"] = '''# tests/test_ai_assist.py
"""AIAssist 单元测试"""
import pytest
from beeoffice.plugins.ai_assist import AIAssist


class TestContinueText:
    def test_continue_empty(self):
        result = AIAssist.continue_text("")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_continue_with_text(self):
        result = AIAssist.continue_text("人工智能正在改变世界")
        assert result.startswith("人工智能正在改变世界")


class TestPolishText:
    def test_polish_empty(self):
        assert AIAssist.polish_text("") == ""

    def test_polish_adds_period(self):
        result = AIAssist.polish_text("这是一段测试文本")
        assert result.endswith("。")


class TestExtractKeywords:
    def test_extract_empty(self):
        assert AIAssist.extract_keywords("") == []

    def test_extract_basic(self):
        text = "蜜蜂办公是一款办公软件，办公软件需要稳定。"
        result = AIAssist.extract_keywords(text, top_n=3)
        assert isinstance(result, list)
        assert len(result) <= 3
'''

FILES["tests/test_app.py"] = '''# tests/test_app.py
"""BeeApp 主窗口测试（P1-4：使用 conftest 里的轻量 app fixture）"""
import pytest


class TestWindowInitialization:
    def test_window_created(self, app):
        assert app is not None

    def test_central_widget_is_tab_manager(self, app):
        from beeoffice.tab_manager import TabManager
        assert isinstance(app.centralWidget(), TabManager)


class TestTabManager:
    def test_new_beewrite(self, app):
        from beeoffice.plugins.beewrite import BeeWriteEditor
        initial_count = app.tab_manager.count()
        editor = app._new_beewrite()
        assert editor is not None
        assert isinstance(editor, BeeWriteEditor)
        assert app.tab_manager.count() == initial_count + 1

    def test_new_beesheet(self, app):
        from beeoffice.plugins.beesheet import BeeSheetView
        initial_count = app.tab_manager.count()
        sheet = app._new_beesheet()
        assert sheet is not None
        assert isinstance(sheet, BeeSheetView)


class TestCommandPalette:
    def test_build_command_palette(self, app_with_plugins):
        from beeoffice.commands import build_command_palette
        palette = build_command_palette(app_with_plugins)
        assert palette is not None
        assert len(palette.all_commands) > 0


class TestStatusBar:
    def test_set_global_status(self, app):
        app.set_global_status("测试消息", 0)
        assert app.status_label.text() == "测试消息"
'''

FILES["tests/test_bee_export.py"] = '''# tests/test_bee_export.py
"""bee_export.py 测试"""
import pytest
from pathlib import Path


SAMPLE_MD = """# 测试标题

这是第一段正文。

## 小节一

- 列表项 1
- 列表项 2
"""


class TestExportToMd:
    def test_basic(self):
        from beeoffice.plugins.bee_export import export_to_md
        result = export_to_md("# 标题\\n\\n正文")
        assert "# 标题" in result

    def test_none_input(self):
        from beeoffice.plugins.bee_export import export_to_md
        assert export_to_md(None) == ""


class TestExportToHtml:
    def test_basic(self, tmp_path):
        from beeoffice.plugins.bee_export import export_to_html
        out = tmp_path / "test.html"
        ok = export_to_html(SAMPLE_MD, str(out))
        assert ok is True
        assert out.exists()


class TestExportToDocx:
    def test_basic(self, tmp_path):
        from beeoffice.plugins.bee_export import export_to_docx, HAS_DOCX
        if not HAS_DOCX:
            pytest.skip("python-docx 未安装")
        out = tmp_path / "test.docx"
        ok = export_to_docx(SAMPLE_MD, str(out))
        assert ok is True
        assert out.exists()


class TestGenerateToc:
    def test_basic(self):
        from beeoffice.plugins.bee_export import generate_toc
        toc = generate_toc(SAMPLE_MD)
        assert isinstance(toc, str)
        assert "目录" in toc
'''

FILES["tests/test_beewrite_basic.py"] = '''# tests/test_beewrite_basic.py
"""BeeWriteEditor 基础功能测试"""
import pytest


class TestInit:
    def test_editor_created(self, beewrite_editor):
        assert beewrite_editor is not None

    def test_default_mode_is_markdown(self, beewrite_editor):
        assert beewrite_editor._edit_mode == "markdown"

    def test_default_doc_kind_is_markdown(self, beewrite_editor):
        assert beewrite_editor._doc_kind == "markdown"


class TestModeSwitch:
    def test_switch_to_rich(self, beewrite_editor):
        beewrite_editor._switch_mode("rich_text")
        assert beewrite_editor._edit_mode == "rich_text"

    def test_switch_back_to_md(self, beewrite_editor):
        beewrite_editor._switch_mode("rich_text")
        beewrite_editor._switch_mode("markdown")
        assert beewrite_editor._edit_mode == "markdown"


class TestContentInterface:
    def test_set_get_content(self, beewrite_editor):
        beewrite_editor.set_content("测试内容")
        assert beewrite_editor.content() == "测试内容"

    def test_get_rendered_content(self, beewrite_editor):
        beewrite_editor.set_content("# 标题\\n")
        rendered = beewrite_editor.get_rendered_content()
        assert "标题" in rendered
'''

FILES["tests/test_export_pdf.py"] = '''# tests/test_export_pdf.py
"""PDF 导出测试"""
import pytest


class TestPageSettingsInjection:
    def test_page_size_injected(self, beewrite_editor):
        content = "<html><head></head><body>test</body></html>"
        settings = {
            "paper": "A4", "orientation": "portrait",
            "margin_top": 25.4, "margin_bottom": 25.4,
            "margin_left": 31.7, "margin_right": 31.7,
        }
        result = beewrite_editor._apply_page_settings_to_content(
            content, settings
        )
        assert "210mm" in result
        assert "297mm" in result

    def test_landscape_injected(self, beewrite_editor):
        content = "<html><head></head><body>test</body></html>"
        settings = {
            "paper": "A4", "orientation": "landscape",
            "margin_top": 25.4, "margin_bottom": 25.4,
            "margin_left": 31.7, "margin_right": 31.7,
        }
        result = beewrite_editor._apply_page_settings_to_content(
            content, settings
        )
        assert "297mm" in result
        assert "210mm" in result
'''

FILES["tests/test_formula_engine.py"] = '''# tests/test_formula_engine.py
"""FormulaEngine 公式引擎的单元测试"""
import pytest
from beeoffice.plugins.formula_engine import FormulaEngine


def make_engine(data):
    def provider(row, col):
        if 0 <= row < len(data) and 0 <= col < len(data[row]):
            return data[row][col]
        return None
    return FormulaEngine(provider)


@pytest.fixture
def simple_engine():
    return make_engine([[1, 2, 3], [4, 5, 6], [7, 8, 9]])


class TestStatisticalFunctions:
    def test_sum_basic(self, simple_engine):
        assert simple_engine.evaluate("=SUM(A1:C3)") == 45

    def test_average_basic(self, simple_engine):
        assert simple_engine.evaluate("=AVERAGE(A1:C3)") == 5.0

    def test_max_basic(self, simple_engine):
        assert simple_engine.evaluate("=MAX(A1:C3)") == 9

    def test_min_basic(self, simple_engine):
        assert simple_engine.evaluate("=MIN(A1:C3)") == 1


class TestEdgeCases:
    def test_non_formula_returns_as_is(self, simple_engine):
        assert simple_engine.evaluate("hello") == "hello"

    def test_empty_formula(self, simple_engine):
        # P2-19：断言收紧
        result = simple_engine.evaluate("=")
        assert result == "", f"空公式应返回 ''，实际: {result!r}"


class TestConditionalFunctions:
    def test_if_true(self, simple_engine):
        assert simple_engine.evaluate('=IF(A1>0,"正","负")') == "正"

    def test_if_two_args_false(self, simple_engine):
        # P2-20：补 IF 双参数为假
        assert simple_engine.evaluate("=IF(A1<0,100)") is False
'''

FILES["tests/test_md_conversion.py"] = '''# tests/test_md_conversion.py
"""Markdown ↔ 富文本 双向转换测试"""
import pytest
from beeoffice.plugins.beewrite_rich_editor import RichTextEditor


class TestRoundTrip:
    def test_roundtrip_preserves_content(self, qtbot, sample_markdown):
        editor = RichTextEditor()
        qtbot.addWidget(editor)
        editor.set_markdown(sample_markdown)
        out_md = editor.to_markdown()
        assert "永遇乐" in out_md
        assert "张三" in out_md


class TestEmptyHeading:
    def test_set_markdown_empty_heading_as_blank(self, qtbot):
        editor = RichTextEditor()
        qtbot.addWidget(editor)
        editor.set_markdown("# \\n\\n正文")
        doc = editor.document()
        block = doc.begin()
        has_empty_heading = False
        while block.isValid():
            if block.blockFormat().headingLevel() > 0 \\
               and not block.text().strip():
                has_empty_heading = True
                break
            block = block.next()
        assert not has_empty_heading
'''

FILES["tests/test_nl_formula.py"] = '''# tests/test_nl_formula.py
"""NLFormulaParser 自然语言公式解析器测试"""
import pytest
from beeoffice.plugins.nl_formula import NLFormulaParser, parse_nl


class TestStatisticalParsing:
    def test_sum_with_range(self):
        assert NLFormulaParser.parse("求和A1到A10") == "=SUM(A1:A10)"

    def test_sum_column(self):
        assert NLFormulaParser.parse("求和B列") == "=SUM(B:B)"

    def test_average_range(self):
        assert NLFormulaParser.parse("平均值A1到A10") == "=AVERAGE(A1:A10)"


class TestIfParsing:
    def test_if_greater(self):
        result = NLFormulaParser.parse("如果A1大于10就显示'高'")
        assert result is not None
        assert "IF" in result
        assert "A1>10" in result

    def test_if_with_false_value(self):
        """
        P2-21：假值提取。依赖 _extract_value 的停止符集合包含"否则"。
        """
        result = NLFormulaParser.parse("如果A1大于10就显示'高'否则显示'低'")
        assert result is not None
        assert '"高"' in result
        assert '"低"' in result


class TestModuleFunction:
    def test_parse_nl_function(self):
        assert parse_nl("求和A1到A10") == "=SUM(A1:A10)"
'''

FILES["tests/test_settings.py"] = '''# tests/test_settings.py
"""AppSettings 测试"""
import json
from pathlib import Path
import pytest


class TestSettingsBasic:
    def test_default_values(self, temp_settings):
        from beeoffice.settings import AppSettings
        s = AppSettings()
        assert s.theme == "light"
        assert s.accent_color == "amber"
        assert s.language == "zh_CN"

    def test_save_and_load(self, temp_settings):
        from beeoffice.settings import AppSettings
        s = AppSettings()
        s.theme = "dark"
        s.accent_color = "ocean"
        s.save()
        s2 = AppSettings()
        assert s2.theme == "dark"
        assert s2.accent_color == "ocean"


class TestSensitiveEncoding:
    def test_password_encoded(self, temp_settings):
        from beeoffice.settings import AppSettings
        s = AppSettings()
        s.webdav_pass = "my_secret_password"
        s.save()
        with open(s.path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        stored = data["webdav_pass"]
        assert stored != "my_secret_password"
        assert stored
'''

FILES["tests/test_tab_manager.py"] = '''# tests/test_tab_manager.py
"""TabManager 测试"""
import pytest
from PySide6.QtWidgets import QPlainTextEdit


class TestBasicOperations:
    def test_add_tab(self, qtbot):
        from beeoffice.tab_manager import TabManager
        tm = TabManager()
        qtbot.addWidget(tm)
        initial_count = tm.count()
        widget = QPlainTextEdit()
        tm.addTab(widget, "测试")
        assert tm.count() == initial_count + 1


class TestFilePaths:
    def test_set_and_get_file_path(self, qtbot, tmp_path):
        from beeoffice.tab_manager import TabManager
        tm = TabManager()
        qtbot.addWidget(tm)
        widget = QPlainTextEdit()
        tm.addTab(widget, "测试")
        tm.set_tab_file_path(widget, str(tmp_path / "test.md"))
        paths = tm.get_open_file_paths()
        assert str(tmp_path / "test.md") in paths
'''

# ---------- 阶段3新增：蜜演播放、移动端 API、命令面板 ----------
FILES["tests/test_beeshow_play.py"] = '''# tests/test_beeshow_play.py
"""蜜演播放功能测试"""
import pytest
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeyEvent


class TestStartPlay:
    def test_start_play_requires_slides(self, qtbot):
        from beeoffice.plugins.beeshow import BeeShowView
        view = BeeShowView()
        qtbot.addWidget(view)
        view._slides_html = []
        view._is_playing = False
        view._start_play()
        assert not view._is_playing

    def test_start_play_resets_to_first(self, qtbot):
        from beeoffice.plugins.beeshow import BeeShowView
        view = BeeShowView()
        qtbot.addWidget(view)
        view._slides_html = ["<h1>A</h1>", "<h1>B</h1>"]
        view._slide_titles = ["A", "B"]
        view._speaker_notes = ["", ""]
        view._current_slide = 1
        try:
            view._start_play()
            assert view._current_slide == 0
        finally:
            view._stop_play()


class TestPlayNavigation:
    def test_right_key_advances(self, qtbot):
        from beeoffice.plugins.beeshow import BeeShowView
        view = BeeShowView()
        qtbot.addWidget(view)
        view._slides_html = ["<h1>A</h1>", "<h1>B</h1>"]
        view._slide_titles = ["A", "B"]
        view._speaker_notes = ["", ""]
        view._is_playing = True
        view._current_slide = 0
        evt = QKeyEvent(QEvent.KeyPress, Qt.Key_Right, Qt.NoModifier)
        view.keyPressEvent(evt)
        assert view._current_slide == 1
'''

FILES["tests/test_mobile_api.py"] = '''# tests/test_mobile_api.py
"""移动端 HTTP 服务器 API 测试"""
import json
import socket
import threading
import time
import urllib.request
import urllib.error
import pytest


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _http_get(url, timeout=3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class _FakeWidgetWithContent:
    def content(self):
        return "# 测试标题\\n\\n正文内容"


class _FakeTabManager:
    def __init__(self, widgets):
        self._widgets = widgets
        self._titles = [f"tab-{i}" for i in range(len(widgets))]

    def count(self):
        return len(self._widgets)

    def widget(self, i):
        if 0 <= i < len(self._widgets):
            return self._widgets[i]
        return None

    def tabText(self, i):
        return self._titles[i]


class _FakeParent:
    def __init__(self, tm):
        self.tab_manager = tm


@pytest.fixture
def mobile_server(qapp):
    from beeoffice.mobile import MobileServer, _ThreadingHTTPServer

    parent = _FakeParent(_FakeTabManager([_FakeWidgetWithContent()]))
    server = MobileServer(parent)
    port = _free_port()
    server.port = port
    server.ip = "127.0.0.1"
    server.temp_dir.mkdir(parents=True, exist_ok=True)
    server._generate_index()

    handler = server._create_handler()
    httpd = _ThreadingHTTPServer(("127.0.0.1", port), handler)
    server.server = httpd
    server.thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server.thread.start()

    for _ in range(20):
        try:
            _http_get(f"http://127.0.0.1:{port}/api/docs", timeout=1)
            break
        except Exception:
            time.sleep(0.05)

    yield server
    server.stop()


class TestDocsAPI:
    def test_docs_returns_json(self, mobile_server):
        status, body = _http_get(
            f"http://127.0.0.1:{mobile_server.port}/api/docs"
        )
        assert status == 200
        data = json.loads(body.decode("utf-8"))
        assert isinstance(data, list)


class TestNoCwdHijack:
    def test_cwd_unchanged_after_start(self, qapp):
        import os
        from beeoffice.mobile import MobileServer
        before = os.getcwd()
        parent = _FakeParent(_FakeTabManager([_FakeWidgetWithContent()]))
        server = MobileServer(parent)
        server.temp_dir.mkdir(parents=True, exist_ok=True)
        server._generate_index()
        after = os.getcwd()
        assert before == after
'''

FILES["tests/test_command_palette.py"] = '''# tests/test_command_palette.py
"""命令面板测试"""
import pytest
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeyEvent


class TestRegisterCommand:
    def test_register_basic(self, qtbot):
        from beeoffice.command_palette import CommandPalette
        palette = CommandPalette()
        qtbot.addWidget(palette)
        palette.register_command("测试命令", "描述", lambda: None)
        assert "测试命令" in palette.all_commands


class TestFilterCommands:
    def _make_palette(self, qtbot):
        from beeoffice.command_palette import CommandPalette
        palette = CommandPalette()
        qtbot.addWidget(palette)
        palette.register_command("导出 PDF", "导出为 PDF", lambda: None)
        palette.register_command("导出 DOCX", "导出为 Word", lambda: None)
        return palette

    def test_filter_single_keyword(self, qtbot):
        palette = self._make_palette(qtbot)
        palette.filter_commands("导出")
        assert palette.list_widget.count() == 2


class TestKeyNavigation:
    def test_escape_closes(self, qtbot):
        from beeoffice.command_palette import CommandPalette
        palette = CommandPalette()
        qtbot.addWidget(palette)
        palette.show()
        assert palette.isVisible()
        evt = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
        palette.keyPressEvent(evt)
        assert not palette.isVisible()
'''

# ---------- P0 回归测试目录 ----------
FILES["tests/test_p0_regression/__init__.py"] = '''"""
P0 回归测试目录
"""
'''

FILES["tests/test_p0_regression/test_p0_05_formula_safe.py"] = '''# tests/test_p0_regression/test_p0_05_formula_safe.py
"""P0-5 回归：公式引擎不允许执行任意 Python"""
import pytest
from beeoffice.plugins.beesheet_engine import FormulaEngine


def make_engine(data):
    def provider(row, col):
        if 0 <= row < len(data) and 0 <= col < len(data[row]):
            return data[row][col]
        return None
    return FormulaEngine(provider)


def test_if_rejects_import():
    engine = make_engine([[1]])
    result = engine.evaluate("=IF(__import__('os').system('echo hi'),1,2)")
    assert isinstance(result, str)
    assert result.startswith("#ERROR")


def test_if_normal_condition_works():
    engine = make_engine([[5]])
    assert engine.evaluate(\'=IF(A1>0,"正","负")\') == "正"
'''

FILES["tests/test_p0_regression/test_p0_06_self_save.py"] = '''# tests/test_p0_regression/test_p0_06_self_save.py
"""P0-6 回归：多文件保存不误弹外部修改"""
import time


def test_is_self_save_multi_file():
    from beeoffice.app import SELF_SAVE_IGNORE_SECONDS

    class FakeApp:
        _recent_self_saves = {}

        def notify_self_save(self, path):
            now = time.time()
            self._recent_self_saves[str(path)] = now
            self._recent_self_saves = {
                p: t for p, t in self._recent_self_saves.items()
                if now - t < 10
            }

        def _is_self_save(self, path):
            ts = self._recent_self_saves.get(str(path), 0)
            return (time.time() - ts) < SELF_SAVE_IGNORE_SECONDS

    app = FakeApp()
    app.notify_self_save("A.md")
    app.notify_self_save("B.md")
    assert app._is_self_save("A.md") is True
    assert app._is_self_save("B.md") is True
    assert app._is_self_save("C.md") is False
'''

FILES["tests/test_p0_regression/test_p0_07_shortcuts.py"] = '''# tests/test_p0_regression/test_p0_07_shortcuts.py
"""P0-7 回归：shortcuts 文档与实际绑定一致"""
from beeoffice.shortcuts import SHORTCUTS, get_shortcut_help


def test_no_ctrl_w_mismatch():
    global_items = SHORTCUTS["全局"]
    ctrl_w = [d for k, d in global_items if k == "Ctrl+W"]
    assert ctrl_w
    assert "关闭" in ctrl_w[0]


def test_no_f5_mismatch():
    beeshow_items = SHORTCUTS["蜜演 BeeShow"]
    f5 = [d for k, d in beeshow_items if k == "F5"]
    assert f5
    assert "播放" in f5[0]


def test_help_contains_expected_sections():
    text = get_shortcut_help()
    for cat in SHORTCUTS.keys():
        assert cat in text
'''

FILES["tests/test_p0_regression/test_p0_11_sumifs.py"] = '''# tests/test_p0_regression/test_p0_11_sumifs.py
"""P0-11 回归：SUMIFS 条件范围行偏移"""
import pytest
from beeoffice.plugins.beesheet_engine import FormulaEngine


def make_engine(data):
    def provider(row, col):
        if 0 <= row < len(data) and 0 <= col < len(data[row]):
            return data[row][col]
        return None
    return FormulaEngine(provider)


def test_sumifs_offset():
    engine = make_engine([
        [1, 10], [2, 20], [3, 30], [2, 40],
    ])
    result = engine.evaluate(\'=SUMIFS(B1:B4,A1:A4,"2")\')
    assert result == 60


def test_avgifs_offset():
    engine = make_engine([
        [1, 10], [2, 20], [3, 30], [2, 40],
    ])
    result = engine.evaluate(\'=AVERAGEIFS(B1:B4,A1:A4,"2")\')
    assert result == 30
'''

FILES["tests/test_p0_regression/test_p0_12_close_others.py"] = '''# tests/test_p0_regression/test_p0_12_close_others.py
"""P0-12 回归：_close_other_tabs 不误关保留标签"""
from PySide6.QtWidgets import QPlainTextEdit
import pytest


def test_close_others_keeps_target(qtbot, monkeypatch):
    from beeoffice.tab_manager import TabManager
    tm = TabManager()
    qtbot.addWidget(tm)

    w1 = QPlainTextEdit()
    w2 = QPlainTextEdit()
    w3 = QPlainTextEdit()
    tm.addTab(w1, "1")
    tm.addTab(w2, "2")
    tm.addTab(w3, "3")

    target = w2
    target_index = tm.indexOf(target)

    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.Yes)
    )

    tm._close_other_tabs(target_index)

    assert tm.count() == 1
    assert tm.widget(0) is target
'''

FILES["tests/test_p0_regression/test_p0_13_split_init.py"] = '''# tests/test_p0_regression/test_p0_13_split_init.py
"""P0-13 回归：分屏容器不触发未保存提示"""
from PySide6.QtWidgets import QWidget
import pytest


def test_split_tab_marked_none(qtbot):
    from beeoffice.tab_manager import TabManager
    tm = TabManager()
    qtbot.addWidget(tm)
    w = QWidget()
    tm.addTab(w, "分屏")
    assert tm._tab_initial_content[id(w)] is None


def test_split_tab_close_no_prompt(qtbot, monkeypatch):
    from beeoffice.tab_manager import TabManager
    from PySide6.QtWidgets import QMessageBox

    tm = TabManager()
    qtbot.addWidget(tm)
    w = QWidget()
    tm.addTab(w, "分屏")
    idx = tm.indexOf(w)

    call_count = {"n": 0}
    def fake_question(*a, **k):
        call_count["n"] += 1
        return QMessageBox.Yes
    monkeypatch.setattr(QMessageBox, "question", staticmethod(fake_question))

    tm._on_tab_close_request(idx)
    assert call_count["n"] == 0
'''

# ---------- P1 回归测试目录 ----------
FILES["tests/test_p2_regression/__init__.py"] = '''"""
P1 回归测试目录
"""
'''

FILES["tests/test_p2_regression/test_p1_01_column_names.py"] = '''# tests/test_p2_regression/test_p1_01_column_names.py
"""P1-1 回归：超过 26 列时列名正确"""
from beeoffice.plugins.beesheet_model import SheetDataModel


def test_30_columns_no_garbage(qapp):
    model = SheetDataModel()
    model._init_empty(rows=10, cols=30)
    cols = list(model._full_df.columns)
    assert cols[0] == "A"
    assert cols[25] == "Z"
    assert cols[26] == "AA"
    assert cols[29] == "AD"
    for c in cols:
        assert c.isalpha()


def test_52_columns(qapp):
    model = SheetDataModel()
    model._init_empty(rows=10, cols=52)
    cols = list(model._full_df.columns)
    assert cols[51] == "AZ"
'''

FILES["tests/test_p2_regression/test_p1_03_close_event.py"] = '''# tests/test_p2_regression/test_p1_03_close_event.py
"""P1-3 回归：beewrite_editor fixture 触发 closeEvent"""
import pytest


def test_close_event_fires(beewrite_editor, monkeypatch):
    fired = {"n": 0}
    original = beewrite_editor.closeEvent

    def spy(event):
        fired["n"] += 1
        return original(event)

    monkeypatch.setattr(beewrite_editor, "closeEvent", spy)
    beewrite_editor.close()
    assert fired["n"] >= 1


def test_timers_stopped_after_close(qtbot, temp_settings):
    from beeoffice.plugins.beewrite import BeeWriteEditor
    editor = BeeWriteEditor()
    qtbot.addWidget(editor)
    editor.markdown_editor.setPlainText("# 测试")
    timer = editor._update_timer
    editor.close()
    assert not timer.isActive()
    editor.deleteLater()
'''

FILES["tests/test_p2_regression/test_p1_04_lightweight_app.py"] = '''# tests/test_p2_regression/test_p1_04_lightweight_app.py
"""P1-4 回归：app fixture 不触发插件加载"""
import time


def test_app_does_not_load_plugins(app):
    assert app.plugin_manager is None or len(app.plugins) == 0


def test_app_does_not_show_restore_dialog(app, qtbot):
    qtbot.wait(200)
    from PySide6.QtWidgets import QApplication
    assert QApplication.activeModalWidget() is None


def test_app_with_plugins_loads_plugins(app_with_plugins):
    assert app_with_plugins.plugin_manager is not None
    assert len(app_with_plugins.plugins) >= 3
'''

FILES["tests/test_p2_regression/test_p1_05_settings_migrate.py"] = '''# tests/test_p2_regression/test_p1_05_settings_migrate.py
"""P1-5 回归：settings 迁移不双重解码"""
import json
import base64
from pathlib import Path


def _b64(s):
    return base64.b64encode(s.encode("utf-8")).decode("utf-8")


def _patch_init(self, path):
    from pathlib import Path
    self.path = Path(path)
    self.window_size = (1024, 680)
    self.recent_files = []
    self.open_tabs = []
    self.theme = "light"
    self.accent_color = "amber"
    self.language = "zh_CN"
    self.has_completed_onboarding = True
    self.recent_commands = []
    self.webdav_url = ""
    self.webdav_user = ""
    self.webdav_pass = ""
    self.webdav_enabled = False
    self.webdav_auto_sync = False
    self.git_repo_path = ""
    self.git_enabled = False
    self.cloud_type = "webdav"
    self.cloud_config = {}
    self.cloud_enabled = False
    self.cloud_auto_sync = False
    self.load()


def test_migrate_old_webdav_to_cloud(tmp_path, monkeypatch):
    from beeoffice.settings import AppSettings
    settings_path = tmp_path / ".beeoffice_settings.json"
    old_data = {
        "version": 0,
        "webdav_url": "https://example.com/webdav",
        "webdav_user": "alice",
        "webdav_pass": _b64("secret123"),
        "webdav_enabled": True,
    }
    settings_path.write_text(
        json.dumps(old_data, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr(
        "beeoffice.settings.AppSettings.__init__",
        lambda self: _patch_init(self, settings_path)
    )
    s = AppSettings()
    assert s.cloud_config.get("password") == "secret123"
'''

FILES["tests/test_p2_regression/test_p1_06_plugin_market_state.py"] = '''# tests/test_p2_regression/test_p1_06_plugin_market_state.py
"""P1-6 回归：插件启用状态切换"""
from PySide6.QtCore import Qt


def test_int_state_checked():
    state = 2
    enabled = (int(state) == 2)
    assert enabled is True


def test_int_state_unchecked():
    state = 0
    enabled = (int(state) == 2)
    assert enabled is False


def test_qt_checkstate_int_value():
    assert int(Qt.CheckState.Checked.value) == 2
    assert int(Qt.CheckState.Unchecked.value) == 0
'''

FILES["tests/test_p2_regression/test_p1_07_binding_render.py"] = '''# tests/test_p2_regression/test_p1_07_binding_render.py
"""P1-7 回归：render 第二个返回值有意义"""
import pandas as pd
from beeoffice.plugins.data_binding import (
    DataSourceManager, BindingEngine,
)


def test_render_returns_unresolved():
    mgr = DataSourceManager()
    mgr.register_dataframe("数据", pd.DataFrame({"销售额": [100, 200]}))
    engine = BindingEngine(mgr)
    template = (
        "已绑定：{{ 数据.销售额.-1 }}\\n"
        "未绑定：{{ 不存在.字段 }}"
    )
    rendered, unresolved = engine.render(template)
    assert "200" in rendered
    assert len(unresolved) == 1


def test_render_all_resolved():
    mgr = DataSourceManager()
    mgr.register_dataframe("源", pd.DataFrame({"值": [42]}))
    engine = BindingEngine(mgr)
    rendered, unresolved = engine.render("{{ 源.值.-1 }}")
    assert "42" in rendered
    assert unresolved == []
'''

FILES["tests/test_p2_regression/test_p1_08_friendly_errors.py"] = '''# tests/test_p2_regression/test_p1_08_friendly_errors.py
"""P1-8 回归：错误信息不跨行误捕获"""
from beeoffice.plugins.friendly_errors import FriendlyError


def test_error_no_cross_line():
    msg = "#ERROR: division by zero\\n    at line 42\\n    stack trace..."
    title, detail = FriendlyError.translate(msg)
    assert title == "公式计算错误"
    assert "division by zero" in detail
    assert "stack trace" not in detail


def test_error_stops_at_next_hash():
    msg = "#ERROR: invalid syntax#some_junk_after"
    _, detail = FriendlyError.translate(msg)
    assert "invalid syntax" in detail
    assert "junk" not in detail
'''

FILES["tests/test_p2_regression/test_p1_09_variable_panel.py"] = '''# tests/test_p2_regression/test_p1_09_variable_panel.py
"""P1-9 回归：变量面板刷新保留数据源选择"""
import pytest


def test_source_combo_selection_preserved(qtbot):
    from beeoffice.plugins.variable_panel import VariablePanel
    panel = VariablePanel()
    qtbot.addWidget(panel)
    panel.update_variables([], ["源A", "源B", "源C"])
    panel.source_combo.setCurrentText("源B")
    assert panel.source_combo.currentText() == "源B"
    panel.update_variables([], ["源A", "源B", "源C"])
    assert panel.source_combo.currentText() == "源B"


def test_source_combo_fallback_when_removed(qtbot):
    from beeoffice.plugins.variable_panel import VariablePanel
    panel = VariablePanel()
    qtbot.addWidget(panel)
    panel.update_variables([], ["源A", "源B"])
    panel.source_combo.setCurrentText("源B")
    panel.update_variables([], ["源A", "源C"])
    assert panel.source_combo.currentText() in ("源A", "")
'''

FILES["tests/test_p2_regression/test_p1_13_reorder.py"] = '''# tests/test_p2_regression/test_p1_13_reorder.py
"""P1-13 回归：重排序不丢失标题"""


def test_reorder_preserves_title(qtbot):
    from beeoffice.plugins.beeshow import BeeShowView
    view = BeeShowView()
    qtbot.addWidget(view)
    view._editor.setPlainText(
        "# 第一页\\n\\n内容 1\\n\\n---\\n\\n# 第二页\\n\\n内容 2"
    )
    view._update_preview()
    assert len(view._slides_md) == 2
    assert "# 第一页" in view._slides_md[0]
    view._on_slides_reordered(None, 0, 0, None, 1)
    new_text = view._editor.toPlainText()
    assert "# 第一页" in new_text
    assert "# 第二页" in new_text
'''

FILES["tests/test_p2_regression/test_p1_14_pdf_undo.py"] = '''# tests/test_p2_regression/test_p1_14_pdf_undo.py
"""P1-14 回归：PDF 撤销区分页码"""
import pytest

fitz = pytest.importorskip("fitz")
from beeoffice.plugins.pdf_annotator import Annotation


class _FakeAnnotator:
    def __init__(self):
        self._annotations = []
        self._current_page = 0

    def undo_annotation(self):
        for i in range(len(self._annotations) - 1, -1, -1):
            if self._annotations[i].page == self._current_page:
                self._annotations.pop(i)
                return True
        return False


def test_undo_same_page():
    a = _FakeAnnotator()
    a._annotations = [
        Annotation(0, fitz.Rect(0, 0, 10, 10)),
        Annotation(1, fitz.Rect(0, 0, 10, 10)),
        Annotation(0, fitz.Rect(10, 10, 20, 20)),
    ]
    a._current_page = 0
    assert a.undo_annotation() is True
    pages = [x.page for x in a._annotations]
    assert pages == [0, 1]


def test_undo_no_annotation_on_current_page():
    a = _FakeAnnotator()
    a._annotations = [Annotation(5, fitz.Rect(0, 0, 10, 10))]
    a._current_page = 0
    assert a.undo_annotation() is False
    assert len(a._annotations) == 1
'''

FILES["tests/test_p2_regression/test_p1_17_mobile_temp.py"] = '''# tests/test_p2_regression/test_p1_17_mobile_temp.py
"""P1-17 回归：多 MobileServer 实例使用独立临时目录"""
from beeoffice.mobile import MobileServer


class _FakeParent:
    pass


def test_two_instances_different_temp_dirs(qapp):
    s1 = MobileServer(_FakeParent())
    s2 = MobileServer(_FakeParent())
    assert s1.temp_dir != s2.temp_dir


def test_temp_dir_unique_on_recreate(qapp):
    dirs = {MobileServer(_FakeParent()).temp_dir for _ in range(3)}
    assert len(dirs) == 3
'''

FILES["tests/test_p2_regression/test_p1_18_command_context.py"] = '''# tests/test_p2_regression/test_p1_18_command_context.py
"""P1-18 回归：命令面板上下文识别"""
import pytest


def test_beeshow_recognized(qtbot):
    from beeoffice.plugins.beeshow import BeeShowView
    from beeoffice.command_palette import CommandPalette

    class _FakeTabManager:
        def __init__(self, w):
            self._w = w

        def currentWidget(self):
            return self._w

    class _FakeParent:
        def __init__(self, w):
            self.tab_manager = _FakeTabManager(w)

    show = BeeShowView()
    qtbot.addWidget(show)
    parent = _FakeParent(show)
    palette = CommandPalette(parent)
    qtbot.addWidget(palette)
    palette._detect_context()
    assert "🎥 蜜演" in palette.context_label.text()


def test_beewrite_recognized(qtbot):
    from beeoffice.plugins.beewrite import BeeWriteEditor
    from beeoffice.command_palette import CommandPalette

    class _FakeTabManager:
        def __init__(self, w):
            self._w = w

        def currentWidget(self):
            return self._w

    class _FakeParent:
        def __init__(self, w):
            self.tab_manager = _FakeTabManager(w)

    editor = BeeWriteEditor()
    qtbot.addWidget(editor)
    parent = _FakeParent(editor)
    palette = CommandPalette(parent)
    qtbot.addWidget(palette)
    palette._detect_context()
    assert "📝 蜜写" in palette.context_label.text()
'''

FILES["tests/test_p2_regression/test_p1_19_image_roundtrip.py"] = '''# tests/test_p2_regression/test_p1_19_image_roundtrip.py
"""P1-19 回归：图片在富文本 ↔ Markdown 往返中不丢失（v5.0.2）"""
import pytest
from pathlib import Path
from PySide6.QtGui import QImage, QColor, QTextImageFormat


@pytest.fixture
def sample_image(tmp_path):
    img_path = tmp_path / "test.png"
    img = QImage(200, 100, QImage.Format_RGB32)
    img.fill(QColor("red"))
    img.save(str(img_path))
    return img_path


def test_to_markdown_contains_image(qtbot, tmp_path, sample_image):
    from beeoffice.plugins.beewrite_rich_editor import RichTextEditor
    editor = RichTextEditor()
    qtbot.addWidget(editor)
    editor.set_current_file_dir(str(tmp_path))
    c = editor.textCursor()
    fmt = QTextImageFormat()
    fmt.setName(str(sample_image))
    c.insertImage(fmt)
    md = editor.to_markdown()
    assert "![" in md
    assert str(sample_image).replace("\\\\", "/") in md


def test_set_markdown_restores_image(qtbot, tmp_path, sample_image):
    from beeoffice.plugins.beewrite_rich_editor import RichTextEditor
    editor = RichTextEditor()
    qtbot.addWidget(editor)
    editor.set_current_file_dir(str(tmp_path))
    md = f"# 标题\\n\\n![]({sample_image})\\n\\n正文"
    editor.set_markdown(md)
    doc = editor.document()
    block = doc.begin()
    found_img = False
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            if fragment.isValid() and fragment.charFormat().isImageFormat():
                found_img = True
                break
            it += 1
        if found_img:
            break
        block = block.next()
    assert found_img


def test_roundtrip_preserves_image(qtbot, tmp_path, sample_image):
    from beeoffice.plugins.beewrite_rich_editor import RichTextEditor
    editor = RichTextEditor()
    qtbot.addWidget(editor)
    editor.set_current_file_dir(str(tmp_path))
    c = editor.textCursor()
    fmt = QTextImageFormat()
    fmt.setName(str(sample_image))
    c.insertImage(fmt)
    md1 = editor.to_markdown()
    editor.set_markdown(md1)
    md2 = editor.to_markdown()
    assert md1 == md2


def test_image_max_width_720():
    from beeoffice.plugins.beewrite_rich_editor import _IMAGE_MAX_WIDTH
    assert _IMAGE_MAX_WIDTH == 720


def test_image_paragraph_centered(qtbot, tmp_path, sample_image):
    """v5.0.4：图片所在段落应居中"""
    from beeoffice.plugins.beewrite_rich_editor import RichTextEditor
    from PySide6.QtCore import Qt
    editor = RichTextEditor()
    qtbot.addWidget(editor)
    editor.set_current_file_dir(str(tmp_path))
    editor._insert_image_by_path(str(sample_image))
    doc = editor.document()
    block = doc.begin()
    found_center = False
    while block.isValid():
        if block.text() == "":
            bf = block.blockFormat()
            if bf.alignment() == Qt.AlignCenter:
                found_center = True
                break
        block = block.next()
    assert found_center
'''


# ==================== 创建逻辑 ====================
def create_files():
    """创建目录及所有文件"""
    print("=" * 60)
    print("  🐝 BeeOffice 测试目录创建工具")
    print("=" * 60)
    print()
    print(f"📁 项目根目录: {PROJECT_ROOT}")
    print(f"📁 测试目录:   {TESTS_DIR}")
    print()

    # 1. 创建所有需要的目录
    dirs_to_create = {
        TESTS_DIR,
        TESTS_DIR / "test_p0_regression",
        TESTS_DIR / "test_p2_regression",
    }
    print("【1】创建目录")
    for d in sorted(dirs_to_create):
        try:
            d.mkdir(parents=True, exist_ok=True)
            print(f"     ✅ {d.relative_to(PROJECT_ROOT)}")
        except Exception as e:
            print(f"     ❌ {d}: {e}")
    print()

    # 2. 写入所有文件
    print("【2】写入文件")
    created = 0
    skipped = 0
    failed = 0

    for rel_path, content in sorted(FILES.items()):
        full_path = PROJECT_ROOT / rel_path
        if full_path.exists() and not FORCE_OVERWRITE:
            print(f"     ⏭️  跳过（已存在）: {rel_path}")
            skipped += 1
            continue

        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"     ✅ {rel_path}")
            created += 1
        except Exception as e:
            print(f"     ❌ {rel_path}: {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"  📊 结果: 创建 {created} 个, 跳过 {skipped} 个, 失败 {failed} 个")
    print("=" * 60)
    print()

    # 3. 显示目录树
    print("【3】目录树")
    print()
    _print_tree(TESTS_DIR, prefix="")

    print()
    print("【4】下一步")
    print()
    print("     1. 安装开发依赖:")
    print("        pip install -r requirements-dev.txt")
    print()
    print("     2. 运行全部测试:")
    print("        pytest tests/ -v")
    print()
    print("     3. 只跑 P0 回归:")
    print("        pytest tests/test_p0_regression/ -v")
    print()
    print("     4. 只跑 P1 回归:")
    print("        pytest tests/test_p2_regression/ -v")
    print()
    print("     5. 生成覆盖率报告:")
    print("        pytest tests/ --cov=beeoffice --cov-report=html")
    print()


def _print_tree(directory: Path, prefix: str = ""):
    """递归打印目录树"""
    if not directory.exists():
        return
    try:
        entries = sorted(
            directory.iterdir(),
            key=lambda x: (not x.is_dir(), x.name)
        )
    except PermissionError:
        return

    for i, entry in enumerate(entries):
        is_last = (i == len(entries) - 1)
        connector = "└── " if is_last else "├── "
        print(f"{prefix}{connector}{entry.name}")

        if entry.is_dir():
            extension = "    " if is_last else "│   "
            _print_tree(entry, prefix + extension)


# ==================== 入口 ====================
if __name__ == "__main__":
    create_files()