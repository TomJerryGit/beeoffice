# beeoffice/app.py
"""
蜜蜂办公 BeeOffice —— 主窗口

本次更新：
  - 新增 _make_tab_title 辅助方法，标签命名精确到秒 + 同名自动加序号
  - 新增 notify_self_save 方法：标记某文件为自己保存的，避免 fileChanged 误触发
  - _on_file_changed 增加"自己保存"过滤：2 秒内自己保存的文件不再提示
  - _new_beewrite / _new_word_doc / _new_beesheet / _new_beeshow 四处使用新命名
  - _new_beewrite 调用 editor.set_doc_kind("markdown")
  - _new_word_doc 调用 editor.set_doc_kind("word")
  - _open_text_file 设置 markdown 类型并记录路径
  - _open_docx_file 改用 _new_word_doc() 并设置 word 类型

v5.0.1 修复（P0-6）：
  - notify_self_save / _is_self_save 从单文件记录改为多文件时间戳 dict
    原因：原实现只记一个文件路径，多文件保存时前一个文件的"自己保存"
    标记会被后一个文件覆盖，导致误弹"文件已被外部修改"对话框

v5.0.2 图片修复：
  - _open_text_file / _open_docx_file 打开文档后调用 set_current_file_path
    使后续粘贴/插入的图片保存到文档所在目录的 media/，而非 ~/media/

v5.0.3 修复（核心）：
  - 修正 _open_docx_file.on_result 的调用顺序：
      BUG：原顺序 set_content → _switch_mode → set_current_file_path
           导致 _switch_mode 内 set_markdown 解析 ![](相对路径) 时
           rich_editor._current_file_dir 仍是默认 ~/，
           图片找不到 → 插入 [图片缺失] 占位文字 → 保存后图片彻底丢失
      FIX：先 set_current_file_path（同步目录），
           再 set_content / _switch_mode（加载内容并解析图片）
  - _open_text_file 同步调整（一致性）

v5.0.4：
  - 本文件无改动（图片段落居中修复在 beewrite_rich_editor.py /
    beewrite_export_mixin.py 里）

v5.0.5 修复：
  - set_global_status 改用 self._status_timer（QTimer(self) 绑定生命周期），
    替代原来的 QTimer.singleShot(lambda: ...)
    原因：singleShot 不绑定控件生命周期，窗口关闭后定时器回调仍会执行，
          status_label 已析构时抛 RuntimeError:
          "Internal C++ object (PySide6.QtWidgets.QLabel) already deleted"
  - 新增 _reset_status_text 辅助方法，带 RuntimeError 保护
  - 新增 try/except 包裹 status_label.setText，防止关闭期间调用崩溃
"""
import os
import sys
import time
import logging
import subprocess
from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import (
    QMainWindow, QStatusBar, QLabel, QMessageBox, QFileDialog,
    QDialog, QVBoxLayout, QTextEdit,
)
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtCore import Qt, QTimer, Signal, QFileSystemWatcher

from beeoffice.tab_manager import TabManager
from beeoffice.settings import AppSettings
from beeoffice.theme import Theme
from beeoffice.icon import create_app_icon
from beeoffice.i18n import tr, set_language
from beeoffice.async_task import AsyncTaskManager


TEXT_EXTENSIONS = (".md", ".txt")
SHEET_EXTENSIONS = (".csv", ".xlsx", ".xls")
AUTOSAVE_INTERVAL_MS = 5 * 60 * 1000
CTRL_LONG_PRESS_SECONDS = 1.0
RESTORE_SESSION_DELAY_MS = 100
FIRST_RUN_CHECK_DELAY_MS = 900
# 自己保存后多少秒内忽略 fileChanged 信号
SELF_SAVE_IGNORE_SECONDS = 2.0
# 自己保存记录的过期清理阈值（秒）——超过此值从 dict 中移除
SELF_SAVE_RECORD_TTL = 10.0


class BeeApp(QMainWindow):
    """蜜蜂办公主窗口"""

    status_message = Signal(str)

    def __init__(self):
        super().__init__()

        self.settings = AppSettings()
        Theme.set_theme(self.settings.theme)
        Theme.set_accent(self.settings.accent_color)
        set_language(self.settings.language)

        self.setWindowTitle(tr("app.title"))
        self.resize(*self.settings.window_size)
        self.setWindowIcon(create_app_icon())

        self.plugins = []
        self.plugin_manager = None
        self._modules_loaded = False

        self.tab_manager = TabManager(self)
        self.setCentralWidget(self.tab_manager)

        from beeoffice.menus import setup_menus
        setup_menus(self)

        self.status = QStatusBar()
        self.status_label = QLabel(tr("app.ready"))
        self.status.addWidget(self.status_label)
        self.setStatusBar(self.status)

        self._apply_theme()

        self._sync_worker = None
        # 优化规划 §3.1 附带发现：`AsyncTaskManager.run()` 返回的是 QRunnable
        # （Worker），**没有 `isRunning()`**；原先 `_sync_now` 靠它判断"是否正在
        # 同步"，AttributeError 被宽 except 吞掉 → 该守卫永不生效，重复点击
        # 「立即同步」（或自动同步与手动同步叠加）会并发启动多次上传。
        # 改用显式布尔标记。
        self._sync_in_progress = False
        self.mobile_server = None
        self._shortcuts_dlg = None
        self._onboarding_overlay = None

        self.file_watcher = QFileSystemWatcher(self)
        self.file_watcher.fileChanged.connect(self._on_file_changed)
        self._last_file_change_prompt = None
        # P0-6：多文件自己保存记录 {path: timestamp}
        # 原实现只记一个文件，多文件保存时容易误弹"外部修改"对话框
        self._recent_self_saves = {}

        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self._autosave)
        self.autosave_timer.start(AUTOSAVE_INTERVAL_MS)

        # v5.0.5：状态栏文字重置定时器
        # 使用 QTimer(self) 而非 QTimer.singleShot，
        # 因为 singleShot 不绑定控件生命周期，
        # 窗口关闭后回调仍会执行，导致 status_label 已析构时崩溃。
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self._reset_status_text)

        self._ctrl_pressed_time = 0.0
        self._ctrl_timer = QTimer(self)
        self._ctrl_timer.setInterval(100)
        self._ctrl_timer.timeout.connect(self._check_ctrl_press)

        QShortcut(QKeySequence("Ctrl+W"), self).activated.connect(
            self.tab_manager.close_current_tab
        )
        QShortcut(QKeySequence("Ctrl+Tab"), self).activated.connect(self._next_tab)
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), self).activated.connect(
            self._prev_tab
        )

        # 启动期的延迟初始化：使用**绑定到本窗口**的单次 QTimer，
        # 而不是 QTimer.singleShot(ms, callable)。
        #
        # 这与 v5.0.5 为状态栏修的是同一类问题（见 _status_timer 的注释）：
        # singleShot 不绑定接收者生命周期，窗口关闭后回调仍会执行。实测后果：
        # 上一个窗口遗留的定时器会在下一个窗口（或下一个测试）的事件循环里
        # 弹出"是否恢复上次会话"模态框，把界面/自动化卡死。
        # 绑定到 self 后，窗口销毁即随之销毁；closeEvent 里还会显式 stop()。
        self._startup_timers = []
        for _msec, _slot in (
            (50, self._lazy_load_modules),
            (RESTORE_SESSION_DELAY_MS, self._restore_session),
            (FIRST_RUN_CHECK_DELAY_MS, self._check_first_run),
            (3000, self._check_auto_sync),
        ):
            _timer = QTimer(self)
            _timer.setSingleShot(True)
            _timer.timeout.connect(_slot)
            _timer.start(_msec)
            self._startup_timers.append(_timer)

    # ==================================================================
    # 标签命名
    # ==================================================================
    def _make_tab_title(self, prefix: str) -> str:
        """
        生成不重复的标签标题：
          - 时间戳精确到秒
          - 若同名已存在，自动追加 (2) / (3) ...
        """
        base = f"{prefix}-{datetime.now().strftime('%H%M%S')}"
        existing = {
            self.tab_manager.tabText(i)
            for i in range(self.tab_manager.count())
        }
        if base not in existing:
            return base
        n = 2
        while f"{base}({n})" in existing:
            n += 1
        return f"{base}({n})"

    # ==================================================================
    # 自己保存通知（P0-6 修复）
    # ==================================================================
    def notify_self_save(self, path: str):
        """
        由 beewrite 保存成功后调用，标记"某文件是自己刚写的"。
        在 SELF_SAVE_IGNORE_SECONDS 秒内的 fileChanged 信号将被忽略。

        P0-6：用 dict 记录多个文件，避免多文件保存互相覆盖。

        :param path: 刚保存的文件路径
        """
        now = time.time()
        self._recent_self_saves[str(path)] = now
        # 顺手清理过期记录，避免 dict 无限增长
        self._recent_self_saves = {
            p: t for p, t in self._recent_self_saves.items()
            if now - t < SELF_SAVE_RECORD_TTL
        }

    def _is_self_save(self, path: str) -> bool:
        """判断 path 是否为自己刚保存的文件（在忽略窗口内）"""
        ts = self._recent_self_saves.get(str(path), 0)
        return (time.time() - ts) < SELF_SAVE_IGNORE_SECONDS

    def sync_tab_title(self, widget, path: str):
        """
        同步某标签的标题为文件名，并刷新窗口标题。

        :param widget: 标签内的 widget
        :param path: 文件路径
        """
        try:
            idx = self.tab_manager.indexOf(widget)
            if idx < 0:
                return
            name = Path(path).name
            # 保留文档类型前缀图标
            doc_kind = getattr(widget, "_doc_kind", "markdown")
            if doc_kind == "word":
                prefix = "📝 "
            elif doc_kind == "markdown":
                prefix = "📝 "
            else:
                prefix = ""
            self.tab_manager.setTabText(idx, f"{prefix}{name}")
            # 如果是当前标签，同步窗口标题
            if idx == self.tab_manager.currentIndex():
                self.setWindowTitle(f"{prefix}{name} - 🐝 蜜蜂办公")
        except Exception as e:
            logging.error(f"同步标签标题失败: {e}")

    # ==================================================================
    # 事件处理
    # ==================================================================
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Control:
            self._ctrl_pressed_time = time.time()
            if not self._ctrl_timer.isActive():
                self._ctrl_timer.start()
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Control:
            self._ctrl_timer.stop()
            if time.time() - self._ctrl_pressed_time > CTRL_LONG_PRESS_SECONDS:
                self._show_shortcuts_overlay()
        super().keyReleaseEvent(event)

    def _check_ctrl_press(self):
        if time.time() - self._ctrl_pressed_time > CTRL_LONG_PRESS_SECONDS:
            self._ctrl_timer.stop()
            self._show_shortcuts_overlay()

    def _show_shortcuts_overlay(self):
        try:
            from beeoffice.shortcuts import get_shortcut_help
        except Exception as e:
            logging.error(f"加载快捷键帮助失败: {e}")
            return

        if self._shortcuts_dlg is not None:
            try:
                self._shortcuts_dlg.close()
            except Exception:
                pass
            self._shortcuts_dlg = None

        dlg = QDialog(self)
        dlg.setWindowTitle(tr("dialog.shortcuts_title", "⌨️ 快捷键"))
        dlg.resize(400, 500)
        layout = QVBoxLayout(dlg)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(get_shortcut_help())
        layout.addWidget(text)
        dlg.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        dlg.show()

        self._shortcuts_dlg = dlg
        QTimer.singleShot(3000, self._close_shortcuts_overlay)

    def _close_shortcuts_overlay(self):
        if self._shortcuts_dlg is not None:
            try:
                self._shortcuts_dlg.close()
            except Exception:
                pass
            self._shortcuts_dlg = None

    # ==================================================================
    # 标签切换
    # ==================================================================
    def _next_tab(self):
        count = self.tab_manager.count()
        if count == 0:
            return
        current = self.tab_manager.currentIndex()
        self.tab_manager.setCurrentIndex((current + 1) % count)

    def _prev_tab(self):
        count = self.tab_manager.count()
        if count == 0:
            return
        current = self.tab_manager.currentIndex()
        self.tab_manager.setCurrentIndex((current - 1) % count)

    # ==================================================================
    # 文件监视
    # ==================================================================
    def _get_watched_paths(self):
        try:
            return set(self.tab_manager.get_open_file_paths())
        except Exception:
            return set(getattr(self.tab_manager, "_tab_file_paths", {}).values())

    def _on_file_changed(self, path):
        # 1. 只处理被监视的路径
        if path not in self._get_watched_paths():
            return

        # 2. 新增：忽略自己刚保存触发的 fileChanged
        if self._is_self_save(path):
            return

        # 3. 避免同一文件重复提示
        if self._last_file_change_prompt == path:
            return

        self._last_file_change_prompt = path
        QTimer.singleShot(
            2000, lambda: setattr(self, "_last_file_change_prompt", None)
        )

        reply = QMessageBox.question(
            self,
            tr("msg.file_changed_title", "文件已更改"),
            tr(
                "msg.file_changed",
                "{path}\n已在外部被修改，是否重新加载？",
            ).format(path=path),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply == QMessageBox.Yes:
            self._open_recent(path)

    def _add_file_watch(self, path):
        if path and path not in self.file_watcher.files():
            try:
                self.file_watcher.addPath(str(path))
            except Exception as e:
                logging.error(f"添加文件监视失败 {path}: {e}")

    # ==================================================================
    # 自动保存
    # ==================================================================
    def _autosave(self):
        widget = self.tab_manager.currentWidget()
        if widget is None:
            return
        if not (hasattr(widget, "save") and self._has_unsaved_changes(widget)):
            return

        try:
            if widget.save():
                self.set_global_status(tr("msg.autosave_done", "已自动保存"), 3000)
                try:
                    self.tab_manager._tab_initial_content[id(widget)] = (
                        self._get_widget_content(widget)
                    )
                    self.tab_manager._mark_saved(widget)
                except Exception as e:
                    logging.error(f"更新自动保存状态失败: {e}")
        except Exception as e:
            logging.error(f"自动保存失败: {e}")

    def _has_unsaved_changes(self, widget):
        try:
            initial = self.tab_manager._tab_initial_content.get(id(widget), "")
        except Exception:
            initial = ""
        return self._get_widget_content(widget) != initial

    def _get_widget_content(self, widget):
        if hasattr(widget, "content"):
            try:
                return widget.content()
            except Exception:
                pass
        if hasattr(widget, "toPlainText"):
            try:
                return widget.toPlainText()
            except Exception:
                pass
        return ""

    # ==================================================================
    # 延迟加载
    # ==================================================================
    def _lazy_load_modules(self):
        try:
            from beeoffice.plugin_manager import PluginManager
            self.plugin_manager = PluginManager(self)
            self.plugin_manager.discover_plugins()
            self.plugins = self.plugin_manager.plugins
            self.plugin_manager.load_plugins()

            self._register_plugin_menus()
        except Exception as e:
            logging.error(f"加载插件失败: {e}")

        self._modules_loaded = True
        self.status_label.setText(tr("app.ready"))

    def _register_plugin_menus(self):
        if not self.plugin_manager:
            return
        menu_bar = self.menuBar()
        for plugin in self.plugins:
            if hasattr(plugin, "register_menus"):
                try:
                    plugin.register_menus(menu_bar)
                except Exception as e:
                    logging.error(
                        f"插件 {getattr(plugin, 'name', '未知')} 注册菜单失败: {e}"
                    )

    # ==================================================================
    # 最近文件
    # ==================================================================
    def _update_recent_menu(self):
        if not hasattr(self, "recent_menu"):
            return
        self.recent_menu.clear()

        if not self.settings.recent_files:
            action = self.recent_menu.addAction(
                tr("menu.file.no_recent", "无最近文件")
            )
            action.setEnabled(False)
        else:
            for path in self.settings.recent_files:
                action = self.recent_menu.addAction(path)
                action.triggered.connect(
                    lambda checked=False, p=path: self._open_recent(p)
                )

        self.recent_menu.addSeparator()
        clear_action = self.recent_menu.addAction(
            tr("menu.file.clear_recent", "清除最近列表")
        )
        clear_action.triggered.connect(self._clear_recent)

    def _open_recent(self, path):
        if not Path(path).exists():
            QMessageBox.warning(
                self,
                tr("msg.file_not_found", "文件不存在"),
                tr("msg.file_not_found_detail", "无法找到文件：\n{path}").format(
                    path=path
                ),
            )
            if path in self.settings.recent_files:
                self.settings.recent_files.remove(path)
                self.settings.save()
                self._update_recent_menu()
            return

        ext = Path(path).suffix.lower()

        if ext in SHEET_EXTENSIONS:
            self._open_sheet_file(path)
        elif ext == ".docx":
            self._open_docx_file(path)
        elif ext in TEXT_EXTENSIONS:
            self._open_text_file(path)
        else:
            logging.warning(f"不支持的文件类型: {ext}")

        self.settings.add_recent_file(path)
        self._update_recent_menu()

    def _open_sheet_file(self, path):
        self._new_beesheet()
        widget = self.tab_manager.currentWidget()
        if not hasattr(widget, "_import_file_from_path"):
            return

        self.set_global_status(
            tr("msg.loading_sheet", "正在加载表格..."), 0
        )

        def on_result(_):
            self.tab_manager.set_tab_file_path(widget, path)
            self._add_file_watch(path)
            self.set_global_status(
                tr("msg.open_success", "已打开 {file}").format(
                    file=Path(path).name
                ),
                3000,
            )

        def on_error(err):
            QMessageBox.warning(
                self, tr("msg.open_failed", "打开失败"), str(err)
            )
            self.set_global_status(tr("msg.open_failed", "打开失败"), 3000)

        AsyncTaskManager.run(
            widget._import_file_from_path,
            path,
            on_result=on_result,
            on_error=on_error,
        )

    def _open_docx_file(self, path):
        """
        打开 .docx 文件（改用 _new_word_doc，直接是 Word 类型）

        v5.0.3 修复：调整调用顺序，确保 set_current_file_path 在
                      set_content / _switch_mode 之前被调用。

        原因：_switch_mode("rich_text") 内部会调 set_markdown()，
              解析 ![](相对路径) 时需要正确的 rich_editor._current_file_dir。
              若目录未同步，图片会被替换为 [图片缺失] 占位文字。
        """
        self._new_word_doc()
        widget = self.tab_manager.currentWidget()
        if not hasattr(widget, "set_content"):
            return

        self.set_global_status(
            tr("msg.loading_docx", "正在打开 Word 文档..."), 0
        )

        try:
            from beeoffice.plugins.bee_export import import_from_docx
        except Exception as e:
            logging.error(f"导入 bee_export 失败: {e}")
            QMessageBox.warning(
                self, tr("msg.open_failed", "打开失败"), str(e)
            )
            return

        def on_result(md_content):
            # ============================================================
            # v5.0.3：先同步文件目录，再加载内容
            # ============================================================
            # 1. 先设置文档类型和路径
            widget._doc_kind = "word"
            widget._current_file_path = path
            # 优化规划 §1.3：记住"这份文档是从哪个 .docx 打开的"。
            # _current_file_path 仍指向该文件（图片目录/文件监视/标签标题都
            # 依赖它），但保存时不得静默覆盖这个原文件——_save_as_docx() 会
            # 据此先询问用户并支持自动备份。
            widget._source_docx = path
            # 2. 再同步到 rich_editor._current_file_dir
            #    （这一步必须在 set_content / _switch_mode 之前！）
            if hasattr(widget, "set_current_file_path"):
                widget.set_current_file_path(path)

            # 3. 现在目录已同步，加载内容
            #    _switch_mode 内部 set_markdown 解析 ![](相对路径) 时
            #    rich_editor._current_file_dir 已是正确目录
            widget.set_content(md_content)
            if hasattr(widget, "_switch_mode"):
                try:
                    widget._switch_mode("rich_text")
                except Exception as e:
                    logging.error(f"切换到富文本模式失败: {e}")

            # 4. 收尾
            if hasattr(widget, "_update_save_btn_text"):
                widget._update_save_btn_text()
            self.tab_manager.set_tab_file_path(widget, path)
            self._add_file_watch(path)
            # 同步标签标题为文件名
            self.sync_tab_title(widget, path)
            self.set_global_status(
                tr("msg.open_success", "已打开 {file}").format(
                    file=Path(path).name
                ),
                3000,
            )

        def on_error(err):
            QMessageBox.warning(
                self, tr("msg.open_failed", "打开失败"), str(err)
            )
            self.set_global_status(tr("msg.open_failed", "打开失败"), 3000)

        AsyncTaskManager.run(
            import_from_docx,
            path,
            on_result=on_result,
            on_error=on_error,
        )

    def _open_text_file(self, path):
        """
        打开 .md / .txt 文件

        v5.0.3：与 _open_docx_file 一致，先同步路径再加载内容
                （防御性一致，避免未来改动引入 bug）
        """
        self._new_beewrite()
        widget = self.tab_manager.currentWidget()
        if not hasattr(widget, "set_content"):
            return

        content = None
        for enc in ("utf-8", "gbk", "gb2312", "latin-1"):
            try:
                with open(path, "r", encoding=enc) as f:
                    content = f.read()
                break
            except UnicodeDecodeError:
                continue
            except Exception as e:
                logging.error(f"读取文件失败 {path} ({enc}): {e}")
                continue

        if content is None:
            QMessageBox.warning(
                self,
                tr("msg.open_failed", "打开失败"),
                tr("msg.encoding_failed", "无法识别文件编码：\n{path}").format(
                    path=path
                ),
            )
            return

        # ============================================================
        # v5.0.3：先同步文件目录，再加载内容
        # ============================================================
        # 1. 先设置文档类型和路径
        widget._doc_kind = "markdown"
        widget._current_file_path = path
        # 2. 再同步到 rich_editor._current_file_dir
        if hasattr(widget, "set_current_file_path"):
            widget.set_current_file_path(path)

        # 3. 加载内容
        widget.set_content(content)

        # 3.5 载入批注 / 书签旁挂数据（优化规划 §2.6）
        #     保存时会写 <base>.comments.json / <base>.bookmarks.json，
        #     此前打开时从不读回，导致重开文档批注书签全丢。
        if hasattr(widget, "load_md_sidecars"):
            widget.load_md_sidecars(path)

        # 4. 收尾
        if hasattr(widget, "_update_save_btn_text"):
            widget._update_save_btn_text()
        self.tab_manager.set_tab_file_path(widget, path)
        self._add_file_watch(path)
        # 同步标签标题为文件名
        self.sync_tab_title(widget, path)

    def _clear_recent(self):
        self.settings.recent_files = []
        self.settings.save()
        self._update_recent_menu()

    # ==================================================================
    # 会话恢复
    # ==================================================================
    def _restore_session(self):
        if not self.settings.open_tabs:
            return

        existing = [p for p in self.settings.open_tabs if Path(p).exists()]
        if not existing:
            return

        preview = "\n".join(f"• {Path(p).name}" for p in existing[:5])
        if len(existing) > 5:
            preview += "\n..."

        reply = QMessageBox.question(
            self,
            tr("msg.restore_session_title", "恢复会话"),
            tr(
                "msg.restore_session",
                "上次有 {count} 个文件未关闭，是否恢复？",
            ).format(count=len(existing)) + "\n\n" + preview,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply == QMessageBox.Yes:
            for filepath in existing:
                self._open_recent(filepath)

    # ==================================================================
    # 命令面板
    # ==================================================================
    def show_command_palette(self):
        from beeoffice.commands import build_command_palette
        palette = build_command_palette(self)
        palette.exec()

    # ==================================================================
    # 新建文档
    # ==================================================================
    def _new_beewrite(self):
        """新建蜜写文档（保存为 .md）"""
        from beeoffice.plugins.beewrite import BeeWriteEditor
        editor = BeeWriteEditor()
        editor.set_doc_kind("markdown")
        self.tab_manager.addTab(editor, self._make_tab_title("📝 蜜写"))
        self.tab_manager.setCurrentWidget(editor)
        return editor

    def _new_word_doc(self):
        """新建 Word 文档（保存为 .docx）"""
        from beeoffice.plugins.beewrite import BeeWriteEditor
        editor = BeeWriteEditor()
        editor.set_doc_kind("word")
        if hasattr(editor, "set_content"):
            editor.set_content(
                tr("msg.new_doc_content", "# 新建文档\n\n在此输入内容...")
            )
        if hasattr(editor, "_switch_mode"):
            try:
                editor._switch_mode("rich_text")
            except Exception as e:
                logging.error(f"切换到富文本模式失败: {e}")

        self.tab_manager.addTab(editor, self._make_tab_title("📝 Word"))
        self.tab_manager.setCurrentWidget(editor)
        self.set_global_status(tr("msg.word_created", "Word 文档已创建"), 5000)
        return editor

    def _new_beesheet(self):
        """新建蜜算表格"""
        from beeoffice.plugins.beesheet import BeeSheetView
        sheet = BeeSheetView()
        self.tab_manager.addTab(sheet, self._make_tab_title("📊 蜜算"))
        self.tab_manager.setCurrentWidget(sheet)
        return sheet

    def _new_beeshow(self):
        """新建蜜演幻灯片"""
        from beeoffice.plugins.beeshow import BeeShowView
        show = BeeShowView()
        self.tab_manager.addTab(show, self._make_tab_title("🎥 蜜演"))
        self.tab_manager.setCurrentWidget(show)
        return show

    # ==================================================================
    # 保存
    # ==================================================================
    def _save_current(self):
        widget = self.tab_manager.currentWidget()
        if widget is None:
            return

        if hasattr(widget, "save"):
            try:
                if widget.save():
                    try:
                        self.tab_manager._mark_saved(widget)
                    except Exception:
                        pass
                    # 保存成功后同步标签标题
                    path = getattr(widget, "_current_file_path", None)
                    if path:
                        self.sync_tab_title(widget, path)
                    self.status_label.setText(tr("msg.saved", "已保存"))
                else:
                    self.status_label.setText(tr("msg.save_failed", "保存失败"))
            except Exception as e:
                logging.error(f"保存失败: {e}")
                self.status_label.setText(tr("msg.save_failed", "保存失败"))
        elif hasattr(widget, "_export_xlsx"):
            widget._export_xlsx()

    def _save_as_current(self):
        widget = self.tab_manager.currentWidget()
        if widget is not None and hasattr(widget, "save_as"):
            widget.save_as()
            # 保存后同步标题
            path = getattr(widget, "_current_file_path", None)
            if path:
                self.sync_tab_title(widget, path)

    def _save_as_template(self):
        widget = self.tab_manager.currentWidget()
        if widget is not None and hasattr(widget, "save_as_template"):
            widget.save_as_template()

    # ==================================================================
    # 导出
    # ==================================================================
    def _run_async_export(self, fn, *args, success_msg, failure_msg, status_text):
        self.set_global_status(status_text, 0)

        def on_result(success):
            if success:
                QMessageBox.information(self, tr("msg.success", "完成"), success_msg)
                self.set_global_status(tr("msg.export_complete", "导出完成"), 3000)
            else:
                QMessageBox.warning(self, tr("msg.failed", "失败"), failure_msg)
                self.set_global_status(tr("msg.export_failed", "导出失败"), 3000)

        def on_error(err):
            QMessageBox.warning(self, tr("msg.failed", "失败"), str(err))
            self.set_global_status(tr("msg.export_failed", "导出失败"), 3000)

        AsyncTaskManager.run(fn, *args, on_result=on_result, on_error=on_error)

    def _export_docx(self):
        widget = self.tab_manager.currentWidget()
        if not hasattr(widget, "get_rendered_content"):
            QMessageBox.warning(
                self,
                tr("msg.hint", "提示"),
                tr("msg.export_docx_unsupported", "当前文档不支持导出 DOCX"),
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("dialog.export_word", "导出 Word"),
            "document.docx",
            "Word (*.docx)",
        )
        if not path:
            return

        from beeoffice.plugins.bee_export import export_to_docx
        content = widget.get_rendered_content()

        self._run_async_export(
            export_to_docx,
            content,
            path,
            success_msg=tr("msg.export_saved", "已导出:\n{path}").format(path=path),
            failure_msg=tr("msg.export_failed", "导出失败"),
            status_text=tr("msg.exporting_docx", "正在导出 Word 文档..."),
        )

    def _export_pdf(self):
        widget = self.tab_manager.currentWidget()
        if not hasattr(widget, "get_rendered_content"):
            QMessageBox.warning(
                self,
                tr("msg.hint", "提示"),
                tr("msg.export_pdf_unsupported", "当前文档不支持导出 PDF"),
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("dialog.export_pdf", "导出 PDF"),
            "document.pdf",
            "PDF (*.pdf)",
        )
        if not path:
            return

        from beeoffice.plugins.bee_export import export_to_pdf
        content = widget.get_rendered_content()

        self._run_async_export(
            export_to_pdf,
            content,
            path,
            success_msg=tr("msg.export_saved", "已导出:\n{path}").format(path=path),
            failure_msg=tr(
                "msg.export_need_weasyprint", "导出失败，可能需要 WeasyPrint"
            ),
            status_text=tr("msg.exporting_pdf", "正在导出 PDF..."),
        )

    def _export_html(self):
        """
        导出当前文档为独立 HTML。

        优化规划 §2.6「补」：此入口原先取 `hasattr(widget, "export_html")`，
        而 `BeeWriteEditor` 当时并没有该方法，因此菜单点了静默无动作
        （阶段 1 按"先删后补"删掉了这个死入口）。现在蜜写侧实现了
        `export_html()`，入口随之重新接上。
        """
        widget = self.tab_manager.currentWidget()
        if widget is not None and hasattr(widget, "export_html"):
            widget.export_html()
        else:
            self.set_global_status(
                tr("msg.export_html_unsupported",
                   "当前文档类型不支持导出 HTML"), 4000
            )

    def _find_current(self):
        widget = self.tab_manager.currentWidget()
        if widget is None:
            return

        if hasattr(widget, "find_bar"):
            editor = widget.editor if hasattr(widget, "editor") else None
            try:
                widget.find_bar.show_for_editor(editor)
            except Exception as e:
                logging.error(f"打开查找栏失败: {e}")
        else:
            QMessageBox.information(
                self,
                tr("dialog.find_title", "查找"),
                tr("msg.find_not_supported", "当前文档不支持查找替换功能。"),
            )

    # ==================================================================
    # 模板
    # ==================================================================
    def _show_template_picker(self):
        from beeoffice.templates import show_template_picker
        show_template_picker(self)

    def _generate_report(self):
        widget = self.tab_manager.currentWidget()
        if not hasattr(widget, "get_rendered_content"):
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("dialog.export_report", "导出报告"),
            "报告.pdf",
            "PDF (*.pdf)",
        )
        if not path:
            return

        from beeoffice.plugins.bee_export import export_to_pdf
        if export_to_pdf(widget.get_rendered_content(), path):
            QMessageBox.information(
                self,
                tr("msg.success", "成功"),
                tr("msg.export_saved", "已保存:\n{path}").format(path=path),
            )
        else:
            QMessageBox.warning(
                self,
                tr("msg.failed", "失败"),
                tr("msg.export_need_weasyprint", "需要 WeasyPrint"),
            )

    def _link_sheet_to_write(self):
        sheet_widget, sheet_name = None, ""
        for i in range(self.tab_manager.count()):
            w = self.tab_manager.widget(i)
            if hasattr(w, "model") and hasattr(w.model, "df"):
                sheet_widget = w
                sheet_name = self.tab_manager.tabText(i).replace("📊 ", "")
                break

        if not sheet_widget:
            QMessageBox.information(
                self,
                tr("msg.hint", "提示"),
                tr("msg.no_sheet", "请先打开蜜算表格"),
            )
            return

        write_widget = None
        for i in range(self.tab_manager.count()):
            w = self.tab_manager.widget(i)
            if hasattr(w, "register_sheet_source"):
                write_widget = w
                break
        if not write_widget:
            write_widget = self._new_beewrite()

        if hasattr(write_widget, "register_sheet_source"):
            write_widget.register_sheet_source(sheet_name, sheet_widget.model.df)

        self.tab_manager.setCurrentWidget(write_widget)

    # ==================================================================
    # 帮助
    # ==================================================================
    def _show_shortcuts(self):
        from beeoffice.shortcuts import get_shortcut_help
        editor = self._new_beewrite()
        if hasattr(editor, "set_content"):
            editor.set_content(get_shortcut_help())

    def show_about(self):
        from beeoffice.__version__ import (
            __version__,
            __author__,
            __email__,
            __slogan__,
        )
        QMessageBox.about(
            self,
            tr("dialog.about_title", "关于蜜蜂办公"),
            f"<h2 style='color:#FFB300;'>🐝 蜜蜂办公 BeeOffice</h2>"
            f"<p><b>{tr('about.version', '版本')} {__version__}</b></p>"
            f"<p>{__slogan__}</p><br>"
            f"<p>{tr('about.author', '开发者')}：{__author__}</p>"
            f"<p>{tr('about.email', '联系邮箱')}：{__email__}</p>",
        )

    # ==================================================================
    # 主题
    # ==================================================================
    def _toggle_theme(self, checked):
        mode = "dark" if checked else "light"
        Theme.set_theme(mode)
        self.settings.theme = mode
        self.settings.save()
        self._apply_theme()

    def _set_accent(self, accent_name):
        Theme.set_accent(accent_name)
        self.settings.accent_color = accent_name
        self.settings.save()
        self._apply_theme()

    def _apply_theme(self):
        self.setStyleSheet(Theme.get_stylesheet())

    def _switch_language(self, lang_code):
        set_language(lang_code)
        self.settings.language = lang_code
        self.settings.save()
        QMessageBox.information(
            self,
            tr("dialog.language_switch", "语言切换"),
            tr("msg.language_switched", "语言已切换，请重启应用。"),
        )

    # ==================================================================
    # 状态栏
    # ==================================================================
    def _on_settings_save_error(self, message: str):
        """
        AppSettings 保存失败时的用户可见提示（优化规划 §1.2）。

        设置保存失败属于"用户以为已保存、实际没保存"的静默数据风险，
        因此除日志外必须让用户看见。同一会话只在首次弹模态框——add_recent_file()
        这类高频调用若每次都弹窗会变成骚扰。
        """
        logging.error(message)
        try:
            self.set_global_status(f"⚠ {message}", 8000)
        except Exception:
            pass

        if getattr(self, "_settings_error_shown", False):
            return
        self._settings_error_shown = True
        try:
            QMessageBox.warning(
                self,
                tr("dialog.settings_save_failed", "设置保存失败"),
                message,
            )
        except Exception:
            pass

    def set_global_status(self, message, timeout=0):
        """
        设置状态栏消息。

        timeout > 0 时，超时后自动恢复为 "就绪"。

        v5.0.5 修复：
          - 改用 self._status_timer（QTimer(self) 绑定生命周期），
            替代原来的 QTimer.singleShot(lambda: ...)
          - 原实现 singleShot 不绑定控件生命周期，
            窗口关闭后回调仍会执行，导致 status_label 已析构时抛
            RuntimeError: Internal C++ object already deleted
          - setText 也加 try/except 保护，防止关闭瞬间调用
        """
        try:
            self.status_label.setText(message)
        except RuntimeError:
            # 窗口已销毁，忽略
            return

        self._status_timer.stop()
        if timeout > 0:
            self._status_timer.start(timeout)

    def _reset_status_text(self):
        """
        状态栏超时恢复为"就绪"。

        v5.0.5 新增：由 self._status_timer 触发，
        带 RuntimeError 保护，防止控件已析构时崩溃。
        """
        try:
            self.status_label.setText(tr("app.ready"))
        except RuntimeError:
            pass

    # ==================================================================
    # 首次运行引导
    # ==================================================================
    def _check_first_run(self):
        if self.settings.has_completed_onboarding:
            return
        try:
            from beeoffice.plugins.onboarding import (
                OnboardingOverlay,
                get_default_steps,
            )
            steps = get_default_steps(self)
            if not steps:
                return
            overlay = OnboardingOverlay(self)
            overlay.finished.connect(self._on_onboarding_finished)
            overlay.set_steps(steps)
            overlay.show()
            self._onboarding_overlay = overlay
        except Exception as e:
            logging.error(f"加载引导失败: {e}")

    def _on_onboarding_finished(self):
        self.settings.has_completed_onboarding = True
        self.settings.save()
        self._onboarding_overlay = None

    # ==================================================================
    # PDF 批注
    # ==================================================================
    def _open_pdf_annotator(self, filepath=None):
        from beeoffice.plugins.pdf_annotator import PDFAnnotator

        if not filepath:
            path, _ = QFileDialog.getOpenFileName(
                self,
                tr("dialog.open_pdf", "打开 PDF"),
                "",
                "PDF (*.pdf)",
            )
            if not path:
                return
            filepath = path

        try:
            annotator = PDFAnnotator()
            annotator.setAttribute(Qt.WA_DeleteOnClose)
            annotator.open_pdf(filepath)
            annotator.show()
        except Exception as e:
            logging.error(f"打开 PDF 批注失败: {e}")
            QMessageBox.warning(
                self, tr("msg.failed", "失败"), str(e)
            )

    # ==================================================================
    # 蜜演
    # ==================================================================
    def _play_beeshow(self):
        widget = self.tab_manager.currentWidget()
        if widget is not None and hasattr(widget, "_start_play"):
            widget._start_play()

    def _export_beeshow_pptx(self):
        widget = self.tab_manager.currentWidget()
        if widget is not None and hasattr(widget, "_export_pptx"):
            widget._export_pptx()

    # ==================================================================
    # 云存储 / 同步
    # ==================================================================
    def _show_webdav_settings(self):
        from beeoffice.cloud_settings import show_cloud_settings
        show_cloud_settings(self)

    def _sync_now(self):
        from beeoffice.cloud import get_cloud_storage

        storage = get_cloud_storage()
        if not storage:
            QMessageBox.information(
                self,
                tr("msg.hint", "提示"),
                tr("msg.webdav_config_required", "请先配置云存储"),
            )
            return

        if self._sync_in_progress:
            QMessageBox.information(
                self,
                tr("msg.hint", "提示"),
                tr("msg.sync_in_progress", "同步正在进行中"),
            )
            return

        self._sync_in_progress = True
        self.set_global_status(tr("msg.syncing", "正在同步..."), 0)

        def sync_files():
            local_dir = Path.home() / ".beeoffice_data"
            remote_dir = "/beeoffice"
            local_dir.mkdir(parents=True, exist_ok=True)

            # 优化规划 §4.5：改为带**过滤**并**如实计数**。
            # 原实现是 `for file in rglob("*"): storage.upload(...)`：既没有
            # 白名单（该目录内任何内容都会明文上传到用户的云盘），也不管结果
            # 一律报"同步完成"（哪怕一个文件都没传）。
            from beeoffice.cloud_sync.policy import (
                upload_tree,
                describe_result,
            )

            counts = upload_tree(storage, local_dir, remote_dir)
            logging.info(f"云同步结果: {counts}")
            return counts, describe_result(counts)

        def on_result(result):
            self._sync_in_progress = False
            counts, msg = result
            failed = counts.get("failed", 0) if isinstance(counts, dict) else 0
            if failed:
                QMessageBox.warning(self, tr("msg.warning", "警告"), msg)
            else:
                QMessageBox.information(self, tr("msg.success", "完成"), msg)
            self.set_global_status(msg, 5000)

        def on_error(err):
            self._sync_in_progress = False
            logging.error(f"同步失败: {err}")
            QMessageBox.warning(
                self, tr("msg.error", "错误"), tr("msg.sync_failed", "同步失败")
            )
            self.set_global_status(tr("msg.sync_failed", "同步失败"), 3000)

        self._sync_worker = AsyncTaskManager.run(
            sync_files, on_result=on_result, on_error=on_error
        )

    def _check_auto_sync(self):
        try:
            from beeoffice.cloud import get_cloud_storage

            if not (self.settings.cloud_enabled and self.settings.cloud_auto_sync):
                return
            if get_cloud_storage():
                self._sync_now()
        except Exception as e:
            logging.error(f"自动同步检查失败: {e}")

    # ==================================================================
    # 内存监控
    # ==================================================================
    def _show_memory_monitor(self):
        from beeoffice.plugins.memory_monitor import MemoryMonitor
        try:
            monitor = MemoryMonitor(self)
            monitor.show()
        except Exception as e:
            logging.error(f"打开内存监控失败: {e}")

    # ==================================================================
    # 日志
    # ==================================================================
    def _open_log_directory(self):
        from beeoffice.crash_handler import CrashHandler

        log_dir = str(CrashHandler.LOG_DIR)
        if not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir)
            except Exception as e:
                logging.error(f"创建日志目录失败: {e}")
                return

        try:
            if os.name == "nt":
                subprocess.run(["explorer", log_dir])
            elif sys.platform == "darwin":
                subprocess.run(["open", log_dir])
            else:
                subprocess.run(["xdg-open", log_dir])
        except Exception as e:
            logging.error(f"打开日志目录失败: {e}")

    # ==================================================================
    # 移动端
    # ==================================================================
    def _open_mobile_download(self):
        import webbrowser
        webbrowser.open(
            "https://github.com/TomJerryGit/beeoffice/releases"
        )

    def _start_mobile_server(self):
        from beeoffice.mobile import MobileServer

        try:
            if self.mobile_server is None:
                self.mobile_server = MobileServer(self)
            self.mobile_server.start()
        except Exception as e:
            logging.error(f"启动移动端服务器失败: {e}")
            QMessageBox.warning(
                self, tr("msg.failed", "失败"), str(e)
            )

    # ==================================================================
    # 批量转换
    # ==================================================================
    def _run_batch_convert(self, fn, input_title, output_title, status_text):
        input_dir = QFileDialog.getExistingDirectory(self, input_title)
        if not input_dir:
            return
        output_dir = QFileDialog.getExistingDirectory(self, output_title)
        if not output_dir:
            return

        self.set_global_status(status_text, 0)

        def on_result(results):
            lines = "\n".join(
                f"{r.get('status', '?')} {r.get('file', '?')}" for r in results
            )
            QMessageBox.information(
                self, tr("msg.success", "完成"), lines or tr("msg.no_files", "无文件")
            )
            self.set_global_status(
                tr("msg.batch_done", "批量转换完成"), 3000
            )

        def on_error(err):
            logging.error(f"批量转换失败: {err}")
            QMessageBox.warning(self, tr("msg.failed", "失败"), str(err))
            self.set_global_status(tr("msg.batch_failed", "批量转换失败"), 3000)

        AsyncTaskManager.run(fn, input_dir, output_dir,
                             on_result=on_result, on_error=on_error)

    def _batch_docx_to_md(self):
        from beeoffice.plugins.bee_export import batch_convert_docx_to_md
        self._run_batch_convert(
            batch_convert_docx_to_md,
            tr("dialog.select_docx_dir", "选择 DOCX 文件夹"),
            tr("dialog.select_output_dir", "选择输出文件夹"),
            tr("msg.converting", "正在批量转换..."),
        )

    def _batch_md_to_docx(self):
        from beeoffice.plugins.bee_export import batch_convert_md_to_docx
        self._run_batch_convert(
            batch_convert_md_to_docx,
            tr("dialog.select_md_dir", "选择 MD 文件夹"),
            tr("dialog.select_output_dir", "选择输出文件夹"),
            tr("msg.converting", "正在批量转换..."),
        )

    # ==================================================================
    # 蜜算增强
    # ==================================================================
    def _analyze_current_sheet(self):
        widget = self.tab_manager.currentWidget()
        if widget is not None and hasattr(widget, "_analyze_data"):
            widget._analyze_data()

    def _nl_formula(self):
        widget = self.tab_manager.currentWidget()
        if widget is not None and hasattr(widget, "_nl_to_formula"):
            widget._nl_to_formula()

    # ==================================================================
    # 插件市场
    # ==================================================================
    def _show_plugin_market(self):
        from beeoffice.plugins.plugin_market import show_plugin_market
        show_plugin_market(self)

    # ==================================================================
    # AI 辅助
    # ==================================================================
    def _ai_continue(self):
        widget = self.tab_manager.currentWidget()
        if widget is not None and hasattr(widget, "_ai_continue"):
            widget._ai_continue()

    def _ai_polish(self):
        widget = self.tab_manager.currentWidget()
        if widget is not None and hasattr(widget, "_ai_polish"):
            widget._ai_polish()

    def _ai_summarize(self):
        widget = self.tab_manager.currentWidget()
        if widget is not None and hasattr(widget, "_ai_summarize"):
            widget._ai_summarize()

    # ==================================================================
    # 关闭
    # ==================================================================
    def closeEvent(self, event):
        try:
            self.autosave_timer.stop()
        except Exception:
            pass

        try:
            self._ctrl_timer.stop()
        except Exception:
            pass

        # v5.0.5：停止状态栏定时器
        try:
            self._status_timer.stop()
        except Exception:
            pass

        # 停止启动期延迟定时器（避免关闭后仍弹出"恢复上次会话"等模态框）
        for _t in getattr(self, "_startup_timers", ()):
            try:
                _t.stop()
            except Exception:
                pass

        if self.mobile_server is not None:
            try:
                self.mobile_server.stop()
            except Exception as e:
                logging.error(f"关闭移动端服务器失败: {e}")
            finally:
                self.mobile_server = None

        try:
            self.settings.open_tabs = self.tab_manager.get_open_file_paths()
            self.settings.window_size = (self.width(), self.height())
            self.settings.save()
        except Exception as e:
            logging.error(f"保存设置失败: {e}")

        if self.plugin_manager:
            try:
                self.plugin_manager.close_all()
            except Exception as e:
                logging.error(f"关闭插件管理器失败: {e}")
        else:
            for plugin in self.plugins:
                try:
                    plugin.on_close()
                except Exception as e:
                    logging.error(
                        f"关闭插件 {getattr(plugin, 'name', '未知')} 失败: {e}"
                    )

        try:
            AsyncTaskManager.wait_for_done(2000)
        except Exception:
            pass

        event.accept()