# tests/conftest.py
"""
Pytest 测试基座

提供：
  - QApplication 单例（pytest-qt 自动管理）
  - 临时工作目录 fixture
  - 示例文档 fixture
  - 示例表格 fixture
  - 临时设置文件 fixture
  - 轻量 BeeApp fixture（P1-4）
  - 完整插件 BeeApp fixture（P1-4）
  - BeeShowView fixture（P1-12 / P0-2 / P0-4）
  - QtWebEngine 会话级清理（自动）

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
    """
    隔离设置文件：把 Path.home() 指向 tmp_path。

    这样 AppSettings() 会自然使用 tmp_path/.beeoffice_settings.json，
    且**所有默认值都来自 settings.py 本身**。

    历史教训：旧实现复制了一份默认值（_patched_settings_init），
    settings.py 新增 ai_api_key 等字段后 fixture 没跟上，
    save() 抛 AttributeError 被宽泛 except 吞掉，把配置写成空文件——
    表现为 4 个"莫名其妙"的测试失败。
    """
    settings_path = tmp_path / ".beeoffice_settings.json"
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    yield settings_path


# ==================== 数据 fixture ====================

@pytest.fixture
def sample_markdown():
    """示例 Markdown 文本"""
    return """# 永遇乐·京口北固亭怀古

【宋】辛弃疾

千古江山，英雄无觅孙仲谋处。舞榭歌台，风流总被雨打风吹去。斜阳草树，寻常巷陌，人道寄奴曾住。想当年，金戈铁马，气吞万里如虎。

元嘉草草，封狼居胥，赢得仓皇北顾。四十三年，望中犹记，烽火扬州路。可堪回首，佛狸祠下，一片神鸦社鼓。凭谁问：廉颇老矣，尚能饭否？

| 序号 | 姓名 | 收入 |
|-----|------|-----:|
| 1 | 张三 | 200 |
| 2 | 李四 | 300 |
| 3 | 王伟 | 200 |
| 4 | 马丽 | 400 |
"""


@pytest.fixture
def sample_table_rows():
    """示例表格二维列表"""
    return [
        ["序号", "姓名", "收入"],
        ["1", "张三", "200"],
        ["2", "李四", "300"],
        ["3", "王伟", "200"],
        ["4", "马丽", "400"],
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
      - yield 后先调 close() 触发 closeEvent（停定时器、清格式刷等）
      - 再调 deleteLater() 释放 Qt 对象

    v5.0.5：恢复 close() 调用。
      上次发的 conftest.py 只有 deleteLater()，缺 close()，
      导致 closeEvent 未触发（定时器未停、格式刷未清），
      虽然大部分测试能过，但会在跨测试场景留下僵尸定时器。
      此处恢复为"先 close 再 deleteLater"。
    """
    from beeoffice.plugins.beewrite import BeeWriteEditor
    editor = BeeWriteEditor()
    qtbot.addWidget(editor)
    yield editor

    # v5.0.5：先 close 触发 closeEvent 清理资源
    try:
        editor.close()
    except Exception:
        pass
    # 再 deleteLater 释放 Qt 对象
    try:
        editor.deleteLater()
    except Exception:
        pass


# ==================== P1-2：日志静默 ====================

@pytest.fixture(autouse=True)
def _quiet_expected_errors():
    """
    P1-2：降级 root logger，避免预期异常污染 pytest.log。

    很多测试故意触发 ValueError（如 VLOOKUP 未找到、MOD 除零），
    这些日志不需要出现在 pytest.log 里。

    autouse=True 表示本 fixture 对每个测试自动生效，
    无需在测试函数签名里显式声明。
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
      - _lazy_load_modules：不加载插件（否则每次创建窗口都会走
        discover_plugins + load_plugins，日志刷屏 + 拖慢测试）
      - _restore_session：不弹恢复会话（避免模态对话框阻塞）
      - _check_first_run：不弹首次运行引导
      - _check_auto_sync：不触发云同步

    与 app_with_plugins 的区别：
      - 本 fixture 创建后 plugin_manager 仍为 None，plugins 为空
      - 适用于大多数"只测 UI 逻辑"的测试
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
    P1-4：完整加载插件的 BeeApp，用于测试 plugin_manager 场景。

    不屏蔽 _lazy_load_modules，让它自然执行（QTimer.singleShot 50ms）。
    qtbot.wait(150) 给足够时间让插件加载完。

    与 app 的区别：
      - 本 fixture 创建后 plugin_manager 非 None，plugins 已加载
      - 适用于测试 plugin_manager / 插件注册 / 插件市场等场景
      - 代价是每次创建会更慢（约 100~200ms）
    """
    from beeoffice.app import BeeApp

    window = BeeApp()
    qtbot.addWidget(window)

    # 等待 _lazy_load_modules 执行（singleShot 50ms，留 150ms 余量）
    qtbot.wait(150)

    yield window

    try:
        window.close()
    except Exception:
        pass


# ==================== P1-12 / P0-2 / P0-4：BeeShowView 公共 fixture ====================

@pytest.fixture
def beeshow_view(qtbot):
    """
    BeeShowView fixture。

    职责：
      - 构造 BeeShowView
      - 测试结束后做"软清理"：
          · 停止播放（停定时器、关播放窗口）
          · 断开 preview 父子关系，主动 deleteLater 释放 WebEngine profile
        目的：消除 pytest 退出时的警告：
            Release of profile requested but WebEnginePage still not deleted.

    为什么不主动 view.deleteLater()：
      pytest-qt 的 qtbot.addWidget() 会在测试结束时统一 close + deleteLater。
      若 fixture 里也 deleteLater，会触发双重删除，抛：
          RuntimeError: Internal C++ object (BeeShowView) already deleted.
      （v5.0.5 修：移除 fixture 末尾的 view.deleteLater + qtbot.wait，
        由 qtbot.addWidget 兜底）

    适用于：
      - P1-12 演讲者模式
      - P0-2 _PlayWindow 键盘转发
      - P0-4 导出时 QWebEngineView 引用保持
      - P1-13 拖拽重排序
    """
    from beeoffice.plugins.beeshow import BeeShowView

    view = BeeShowView()
    qtbot.addWidget(view)
    yield view

    # 软清理 1：停止播放，关闭 _play_window / _notes_window
    try:
        view._stop_play()
    except Exception:
        pass

    # 软清理 2：主动释放 _preview 的 WebEngine profile
    # （preview 是 view 的 child，view 被 qtbot 删时会连带删，
    #   但 profile 释放是异步的，主动断父子关系能加速回收）
    try:
        if hasattr(view, "_preview") and view._preview is not None:
            view._preview.setParent(None)
            view._preview.deleteLater()
    except Exception:
        pass

    # ★ 不再手动 view.deleteLater() / qtbot.wait()
    #    —— qtbot.addWidget 已在测试结束时统一清理


# ==================== QtWebEngine 会话级清理 ====================

@pytest.fixture(scope="session", autouse=True)
def _cleanup_webengine_at_session_end():
    """
    会话结束时清理 QtWebEngine，减轻以下警告：

        Release of profile requested but WebEnginePage still not deleted.
        Expect troubles !

    v5.0.6（CI 友好）：不再依赖 pytest-qt 的 qapp fixture。
        - 未安装 PySide6 时直接跳过，纯逻辑测试（公式引擎、设置迁移等）
          可以在没有 GUI 依赖的机器 / CI 容器里运行。
        - 通过 QApplication.instance() 判断是否真的有 GUI 环境，
          避免"为了跑一条公式测试先装 200MB Qt"。

    背景：
      QWebEngineProfile 是全局单例，持有所有 QWebEngineView 的 page 引用。
      page 的销毁走 deleteLater + 事件循环，异步完成。
      pytest 退出太快，事件循环没跑完，profile 清理时发现 page 还在，
      就报上述警告。

    本 fixture 在会话结束时：
      1. 跑几轮事件循环 + DeferredDelete，让 pending deleteLater 执行
      2. 遍历 QApplication 里所有 QWebEngineView，主动 deleteLater 其 page
      3. 再跑几轮事件循环

    说明：
      - 这是 best-effort，不保证 100% 消除警告
      - 警告本身无害，只影响 stderr 可读性
      - 若 QtWebEngine 版本/平台差异导致仍报，可在 run_tests.bat
        里把 stderr 重定向到 tests/stderr.log
    """
    yield

    # 没有 GUI 依赖时直接跳过（纯逻辑测试不需要 Qt）
    try:
        import time
        from PySide6.QtCore import QEvent, QCoreApplication
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return
    if QApplication.instance() is None:
        return

    def _drain(rounds=10, delay=0.05):
        """跑几轮事件循环 + DeferredDelete，让 pending deleteLater 执行。"""
        for _ in range(rounds):
            QCoreApplication.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            time.sleep(delay)
            QCoreApplication.processEvents()

    # 1. 先跑一轮，让之前 pending 的 deleteLater 执行
    _drain(rounds=5)

    # 2. 主动清理所有 QWebEngineView 的 page
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            views = [
                w for w in app.allWidgets()
                if isinstance(w, QWebEngineView)
            ]
            for view in views:
                try:
                    page = view.page()
                    if page is not None:
                        page.deleteLater()
                    view.setParent(None)
                    view.deleteLater()
                except Exception:
                    pass
    except Exception:
        pass

    # 3. 再跑几轮，让刚触发的 deleteLater 也执行完
    _drain(rounds=10)