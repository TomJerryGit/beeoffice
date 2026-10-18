# beeoffice/tab_manager.py
"""
标签管理器：支持多标签、拖拽合并、未保存标记、右键菜单、分屏等

v5.0.1 修复：
  - P0-12：_close_other_tabs 用 widget 比较而非索引，
           避免倒序关闭过程中索引漂移导致保留标签被误关
  - P0-13：addTab 对无 content/toPlainText 的 QWidget（如分屏容器）
           标记 initial_content 为 None，_on_tab_close_request 遇到 None
           时跳过未保存检查，避免误弹关闭提示
"""
import os
from PySide6.QtWidgets import (QTabWidget, QPlainTextEdit, QFileDialog,
                                QSplitter, QWidget, QVBoxLayout, QMessageBox,
                                QMenu, QInputDialog, QApplication)
from PySide6.QtCore import Qt, QMimeData
from PySide6.QtGui import QDrag

from beeoffice.i18n import tr


class TabManager(QTabWidget):
    """标签管理器"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabsClosable(True)
        self.setMovable(True)
        self.setDocumentMode(True)
        self.tabCloseRequested.connect(self._on_tab_close_request)
        self.currentChanged.connect(self._on_tab_changed)

        # 内部状态
        self._tab_initial_content = {}   # {id(widget): 初始内容}
        self._tab_file_paths = {}        # {id(widget): 文件路径}
        self._drag_tab_index = -1        # 拖拽起点标签索引
        self._drag_start_pos = None      # 拖拽起点位置

        # 接受拖放（QWidget 的方法，合法）
        self.setAcceptDrops(True)
        # 标签栏可拖动（Qt 会接管跨窗口拖拽，无需 setDragEnabled）
        self.tabBar().setMovable(True)
        # QTabBar 继承自 QWidget，setAcceptDrops 合法
        self.tabBar().setAcceptDrops(True)

        # 右键菜单
        self.tabBar().setContextMenuPolicy(Qt.CustomContextMenu)
        self.tabBar().customContextMenuRequested.connect(self._show_tab_context_menu)

        # 添加欢迎页
        self._add_welcome_tab()

    # ---------- 欢迎页 ----------
    def _add_welcome_tab(self):
        welcome = QPlainTextEdit()
        welcome.setReadOnly(True)
        welcome.setPlainText(tr("tab.welcome_text", (
            "🐝 欢迎使用蜜蜂办公\n\n"
            "轻量、快速、实而不华。\n"
            "按 Ctrl+Shift+P 打开命令面板。\n"
            "新建文件或拖入文档即可开始。"
        )))
        self.addTab(welcome, tr("tab.welcome_title", "开始"))

    def new_empty_tab(self, title=None):
        """创建空白文本标签"""
        editor = QPlainTextEdit()
        self.addTab(editor, title or tr("tab.untitled", "未命名"))
        self.setCurrentWidget(editor)
        return editor

    # ---------- 打开文件 ----------
    def open_file(self):
        """弹出文件对话框打开文件"""
        path, _ = QFileDialog.getOpenFileName(
            self, "打开文件", "",
            "所有支持格式 (*.md *.docx *.csv *.xlsx *.txt);;"
            "Excel (*.xlsx *.xls);;CSV (*.csv);;Word (*.docx);;"
            "Markdown (*.md);;文本 (*.txt)"
        )
        if not path:
            return
        ext = path.split('.')[-1].lower() if '.' in path else ''
        if ext in ('xlsx', 'xls', 'csv', 'docx'):
            parent = self.parent()
            if parent and hasattr(parent, '_open_recent'):
                parent._open_recent(path)
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            title = os.path.basename(path)
            editor = self.new_empty_tab(title=title)
            editor.setPlainText(content)
            self._tab_file_paths[id(editor)] = path
            if hasattr(self.parent(), 'settings'):
                self.parent().settings.add_recent_file(path)
                self.parent()._update_recent_menu()
        except Exception as e:
            editor = self.new_empty_tab(title="错误")
            editor.setPlainText(f"无法打开文件: {path}\n{str(e)}")

    # ---------- 标签关闭 ----------
    def _on_tab_close_request(self, index):
        """
        关闭标签前检查未保存内容

        P0-13：initial_content 为 None 时跳过未保存检查
                （分屏容器等无 content/toPlainText 的 QWidget）
        """
        widget = self.widget(index)
        if widget is None:
            return

        current_content = ""
        if hasattr(widget, 'content'):
            current_content = widget.content()
        elif hasattr(widget, 'toPlainText'):
            current_content = widget.toPlainText()

        initial_content = self._tab_initial_content.get(id(widget), "")

        # P0-13：None 表示此标签不支持未保存检查（如分屏容器）
        if initial_content is None:
            self._close_tab(index)
            return

        title = self.tabText(index)
        if current_content.strip() and current_content != initial_content:
            reply = QMessageBox.question(
                self, tr("tab.close_title", "关闭标签"),
                tr("tab.close_confirm",
                   "「{title}」中的内容可能还未保存。\n确定要关闭吗？"
                   ).format(title=title),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
        self._close_tab(index)

    def _close_tab(self, index):
        """实际关闭标签并清理资源"""
        widget = self.widget(index)
        self.removeTab(index)
        if widget:
            self._tab_initial_content.pop(id(widget), None)
            self._tab_file_paths.pop(id(widget), None)
            widget.deleteLater()

    def close_current_tab(self):
        """关闭当前标签"""
        index = self.currentIndex()
        if index >= 0:
            self._close_tab(index)

    def _close_other_tabs(self, keep_index):
        """
        关闭除指定标签外的所有标签

        P0-12 修复：
          原实现用 `i != keep_index` 判断，但倒序关闭过程中，如果某个
          标签因用户点"否"未被关闭，keep_index 指向的 widget 会漂移。
          改为先取出 keep_widget，再用 `self.widget(i) is not keep_widget`
          判断，避免误关保留标签。
        """
        keep_widget = self.widget(keep_index)
        if keep_widget is None:
            return
        # 倒序关闭，避免删除后索引失效
        for i in range(self.count() - 1, -1, -1):
            if self.widget(i) is not keep_widget:
                self._on_tab_close_request(i)

    # ---------- 标签切换 ----------
    def _on_tab_changed(self, index):
        # 宏录制（阶段三 #8）：切到另一张蜜算表时记一个 sheet 动作
        try:
            from beeoffice.plugins.macro_recorder import RECORDER
            widget = self.widget(index)
            if widget is not None and hasattr(widget, "model"):
                title = (self.tabText(index)
                         .replace("📊 ", "").replace("● ", "").strip())
                RECORDER.record_sheet(title)
        except Exception:
            pass
        if index < 0:
            return
        title = self.tabText(index)
        parent = self.parent()
        if parent and hasattr(parent, 'setWindowTitle'):
            parent.setWindowTitle(f"{title} - 🐝 蜜蜂办公")

    # ---------- 未保存标记 ----------
    def _mark_unsaved(self, widget):
        """标记标签为未保存（前置 ●）"""
        index = self.indexOf(widget)
        if index >= 0:
            current_text = self.tabText(index)
            if not current_text.startswith("● "):
                self.setTabText(index, "● " + current_text)

    def _mark_saved(self, widget):
        """移除未保存标记"""
        index = self.indexOf(widget)
        if index >= 0:
            current_text = self.tabText(index)
            if current_text.startswith("● "):
                self.setTabText(index, current_text[2:])

    # ---------- 文件路径映射 ----------
    def get_open_file_paths(self):
        """返回所有打开的文件路径列表"""
        return list(self._tab_file_paths.values())

    def set_tab_file_path(self, widget, path):
        """设置标签对应的文件路径"""
        self._tab_file_paths[id(widget)] = str(path)

    # ---------- 重写 addTab ----------
    def addTab(self, widget, title):
        """
        重写 addTab，记录初始内容并连接内容变化信号

        P0-13：对无 content/toPlainText 的 QWidget（如分屏容器）
               标记为 None，表示无需检查未保存修改
        """
        super().addTab(widget, title)

        if hasattr(widget, 'content'):
            self._tab_initial_content[id(widget)] = widget.content()
        elif hasattr(widget, 'toPlainText'):
            self._tab_initial_content[id(widget)] = widget.toPlainText()
        else:
            # P0-13：None 表示不参与未保存检查
            self._tab_initial_content[id(widget)] = None

        # 连接内容变化信号（若控件支持）
        if hasattr(widget, 'contentChanged'):
            try:
                widget.contentChanged.connect(
                    lambda w=widget: self._mark_unsaved(w)
                )
            except Exception:
                pass

    # ---------- 分屏 ----------
    def split_with_current(self):
        """将当前标签拆分为分屏视图"""
        current = self.currentWidget()
        if current is None:
            return
        index = self.currentIndex()
        # 创建分屏容器
        splitter = QSplitter(Qt.Horizontal)
        # 将当前控件从标签移除（不删除）
        self.removeTab(index)
        # 重新设置父窗口为 splitter
        current.setParent(splitter)
        splitter.addWidget(current)
        # 创建新编辑器
        new_editor = QPlainTextEdit()
        new_editor.setParent(splitter)
        splitter.addWidget(new_editor)
        splitter.setSizes([300, 300])
        # 将 splitter 放入容器 widget，添加到 tab
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)
        self.addTab(container, tr("tab.split", "分屏"))
        self.setCurrentWidget(container)

    # ---------- 拖拽：标签合并 ----------
    def mousePressEvent(self, event):
        """记录拖拽起点"""
        if event.button() == Qt.LeftButton:
            tab_index = self.tabBar().tabAt(event.pos())
            if tab_index >= 0:
                self._drag_tab_index = tab_index
                self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """拖动标签时启动拖拽"""
        if self._drag_tab_index >= 0 and (event.buttons() & Qt.LeftButton):
            if self._drag_start_pos is not None:
                distance = (event.pos() - self._drag_start_pos).manhattanLength()
                if distance > 20:
                    self._start_drag()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """释放拖拽状态"""
        self._drag_tab_index = -1
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)

    def _start_drag(self):
        """开始拖拽标签"""
        if self._drag_tab_index < 0:
            return
        widget = self.widget(self._drag_tab_index)
        if not widget:
            return
        mime_data = QMimeData()
        payload = f"{id(self)}:{self._drag_tab_index}".encode()
        mime_data.setData("application/x-beeoffice-tab", payload)
        mime_data.setText(self.tabText(self._drag_tab_index))
        drag = QDrag(self)
        drag.setMimeData(mime_data)
        drag.exec(Qt.MoveAction)
        self._drag_tab_index = -1

    def dragEnterEvent(self, event):
        """接受拖拽事件"""
        if event.mimeData().hasFormat("application/x-beeoffice-tab"):
            event.acceptProposedAction()
        elif event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        """处理拖拽移动"""
        if event.mimeData().hasFormat("application/x-beeoffice-tab"):
            event.acceptProposedAction()
        elif event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        """处理拖拽释放：标签合并或文件拖入"""
        # 处理来自其他标签管理器的标签
        if event.mimeData().hasFormat("application/x-beeoffice-tab"):
            try:
                data = bytes(event.mimeData().data("application/x-beeoffice-tab")).decode()
                source_id, source_index = data.split(":")
                source_tab = self._find_tab_by_id(int(source_id))
                if source_tab and source_tab is not self:
                    source_index = int(source_index)
                    source_widget = source_tab.widget(source_index)
                    source_title = source_tab.tabText(source_index)
                    source_tab.removeTab(source_index)
                    if source_widget:
                        source_widget.setParent(self)
                        self.addTab(source_widget, source_title)
                        self.setCurrentWidget(source_widget)
                        file_path = source_tab._tab_file_paths.pop(id(source_widget), None)
                        if file_path:
                            self._tab_file_paths[id(source_widget)] = file_path
                        init_content = source_tab._tab_initial_content.pop(id(source_widget), None)
                        if init_content is not None:
                            self._tab_initial_content[id(source_widget)] = init_content
                    event.acceptProposedAction()
                    return
            except Exception:
                pass

        # 处理拖入文件
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            parent = self.parent()
            for url in urls:
                path = url.toLocalFile()
                if path and hasattr(parent, '_open_recent'):
                    parent._open_recent(path)
            event.acceptProposedAction()
            return

        super().dropEvent(event)

    def _find_tab_by_id(self, tab_id):
        """根据 id 查找标签管理器实例（用于跨窗口拖拽）"""
        if id(self) == tab_id:
            return self
        parent = self.parent()
        if parent and hasattr(parent, 'tab_manager'):
            if id(parent.tab_manager) == tab_id:
                return parent.tab_manager
        return None

    # ---------- 右键菜单 ----------
    def _show_tab_context_menu(self, pos):
        """显示标签的右键菜单"""
        tab_index = self.tabBar().tabAt(pos)
        if tab_index < 0:
            return
        menu = QMenu(self)

        close_action = menu.addAction(tr("tab.close", "关闭标签"))
        close_action.triggered.connect(lambda: self._on_tab_close_request(tab_index))

        close_others_action = menu.addAction(
            tr("tab.close_others", "关闭其他标签")
        )
        close_others_action.triggered.connect(lambda: self._close_other_tabs(tab_index))

        menu.addSeparator()

        rename_action = menu.addAction(tr("tab.rename", "重命名标签"))
        rename_action.triggered.connect(lambda: self._rename_tab(tab_index))

        copy_path_action = menu.addAction(
            tr("tab.copy_path", "复制文件路径")
        )
        copy_path_action.triggered.connect(lambda: self._copy_file_path(tab_index))

        menu.exec(self.tabBar().mapToGlobal(pos))

    def _rename_tab(self, index):
        """重命名标签"""
        current_text = self.tabText(index)
        base_text = current_text[2:] if current_text.startswith("● ") else current_text
        text, ok = QInputDialog.getText(
            self, tr("tab.rename", "重命名标签"),
            tr("tab.rename_prompt", "输入新名称:"), text=base_text
        )
        if ok and text:
            prefix = "● " if current_text.startswith("● ") else ""
            self.setTabText(index, prefix + text)

    def _copy_file_path(self, index):
        """复制标签对应的文件路径到剪贴板"""
        widget = self.widget(index)
        if widget is None:
            return
        path = self._tab_file_paths.get(id(widget))
        if path:
            QApplication.clipboard().setText(path)