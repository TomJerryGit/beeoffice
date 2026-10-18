# beeoffice/command_palette.py
"""
命令面板：支持上下文推荐、最近命令、上下键导航

v5.0.1 修复（P1-18）：
  - _detect_context 蜜演识别由单特征（_start_play）改为双特征
    （_slides_html + _start_play），避免通用方法名误判
  - 同时为蜜写识别加注释说明判断依据（editor + preview）

v5.0.5 修复：
  - __init__ 增加 parent 类型检查：只有 QWidget 才能作为 QDialog 的 parent
    原因：测试或某些调用方传入的是 mock 对象 / 自定义对象（非 QWidget），
          PySide6 会抛 TypeError:
          "QDialog.__init__ called with wrong argument types"
  - 业务 parent 引用保留为 self._parent，
    通过 _detect_context / _execute 读取 tab_manager 等业务属性
"""
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
                                QListWidget, QListWidgetItem, QLabel, QWidget)
from PySide6.QtCore import Qt, Signal, QEvent, QTimer
from PySide6.QtGui import QColor
from beeoffice.i18n import tr


class CommandPalette(QDialog):
    command_executed = Signal(str)

    def __init__(self, parent=None):
        # v5.0.5：只有 QWidget 才能作为 QDialog 的 parent
        # 若传入的是 mock / 业务对象，则不传给 QDialog
        qt_parent = parent if isinstance(parent, QWidget) else None
        super().__init__(qt_parent)

        # 业务 parent 引用（保留原始传入对象，
        # 可能为非 QWidget，如测试用的 _FakeParent）
        self._parent = parent

        self.setWindowTitle(tr("auto.command_palette.5c28d848", "命令面板"))
        self.setWindowFlags(Qt.Dialog | Qt.Popup)
        self.resize(450, 60)

        # 内部焦点切换标志，防止误关闭
        self._internal_focus_change = False
        # 关闭延迟标志
        self._closing = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # 输入框
        header_layout = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText(tr("auto.command_palette.2d7652e2", "输入命令搜索..."))
        self.input.setStyleSheet(
            "QLineEdit { border: none; font-size: 15px; padding: 6px; background: transparent; }"
        )
        header_layout.addWidget(self.input)

        # 上下文标签
        self.context_label = QLabel("")
        self.context_label.setStyleSheet(
            "QLabel { color: #FF8F00; font-size: 11px; font-weight: bold; "
            "padding: 4px 8px; background: #FFF3E0; border-radius: 4px; }"
        )
        self.context_label.hide()
        header_layout.addWidget(self.context_label)
        layout.addLayout(header_layout)

        # 命令列表
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(
            "QListWidget { border: none; font-size: 13px; background: #FFF; } "
            "QListWidget::item { padding: 8px 10px; } "
            "QListWidget::item:selected { background-color: #FFB300; color: #000; }"
        )
        self.list_widget.hide()
        layout.addWidget(self.list_widget)

        # 命令注册表
        self.all_commands = {}
        self.context_commands = []
        self.recent_commands = []
        if parent and hasattr(parent, 'settings'):
            self.recent_commands = getattr(parent.settings, 'recent_commands', []) or []

        # 信号连接
        self.input.textChanged.connect(self.filter_commands)
        self.input.returnPressed.connect(self.execute_current)
        self.list_widget.itemClicked.connect(self.execute_from_click)
        self.input.setFocus()

        # 安装事件过滤器，防止内部焦点变化导致关闭
        self.input.installEventFilter(self)
        self.list_widget.installEventFilter(self)

    # ---------- 事件处理 ----------
    def eventFilter(self, obj, event):
        """事件过滤器：处理内部控件焦点变化"""
        if event.type() == QEvent.FocusOut:
            # 如果焦点转移到内部另一个控件，不关闭
            if self._focus_inside():
                return True
            # 否则延迟关闭，给用户切换焦点的时间
            QTimer.singleShot(100, self._delayed_close)
        return super().eventFilter(obj, event)

    def _focus_inside(self):
        """判断焦点是否还在面板内部"""
        return self.input.hasFocus() or self.list_widget.hasFocus()

    def _delayed_close(self):
        """延迟关闭，检查焦点是否已离开面板"""
        if self._closing:
            return
        if not self.isActiveWindow() and not self._focus_inside():
            self._closing = True
            self.close()

    def changeEvent(self, event):
        """窗口失去激活时延迟关闭"""
        if event.type() == QEvent.WindowDeactivate:
            QTimer.singleShot(100, self._delayed_close)
        super().changeEvent(event)

    def keyPressEvent(self, event):
        """按 ESC 关闭"""
        if event.key() == Qt.Key_Escape:
            self.close()
        elif event.key() in (Qt.Key_Down, Qt.Key_Up):
            # 上下键切换列表选中项
            if self.list_widget.isVisible() and self.list_widget.count() > 0:
                current_row = self.list_widget.currentRow()
                if event.key() == Qt.Key_Down:
                    new_row = min(current_row + 1, self.list_widget.count() - 1)
                else:
                    new_row = max(current_row - 1, 0)
                self.list_widget.setCurrentRow(new_row)
                return
            super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self._detect_context()
        if not self.input.text():
            self._show_context_recommendations()
        self.input.setFocus()
        self.input.selectAll()

    # ---------- 上下文识别 ----------
    def _detect_context(self):
        """
        检测当前活动标签页的类型，显示对应的上下文命令

        v5.0.1（P1-18）：
          - 蜜演识别改为 _slides_html + _start_play 双特征
          - 蜜写识别补充 editor + preview 注释
        """
        self.context_commands = []
        self.context_label.hide()
        if not self._parent:
            return
        widget = None
        if hasattr(self._parent, 'tab_manager'):
            widget = self._parent.tab_manager.currentWidget()
        if not widget:
            return

        # ---------- 蜜写编辑器识别 ----------
        # 依据：BeeWriteEditor 有 editor 属性 + preview 属性
        if hasattr(widget, 'editor') and hasattr(widget, 'preview'):
            self.context_label.setText(tr("auto.command_palette.41c3d07a", "📝 蜜写"))
            self.context_label.show()
            self.context_commands = [
                "导出 PDF", "导出 DOCX", "导出 HTML", "保存文件", "查找替换",
                "AI 续写", "AI 润色", "AI 总结"
            ]
        # ---------- 蜜算表格识别 ----------
        # 依据：BeeSheetView 有 table_view + model
        elif hasattr(widget, 'table_view') and hasattr(widget, 'model'):
            self.context_label.setText(tr("auto.command_palette.06bf9dd7", "📊 蜜算"))
            self.context_label.show()
            self.context_commands = [
                "导入数据", "导出表格", "排序与筛选", "数据清洗", "生成图表",
                "自然语言生成公式"
            ]
        # ---------- 蜜演识别 ----------
        # P1-18：依据改为 _slides_html + _start_play 双特征，
        # 语义更明确，避免同名方法误判
        elif (hasattr(widget, '_slides_html')
              and hasattr(widget, '_start_play')):
            self.context_label.setText(tr("auto.command_palette.268a7dbb", "🎥 蜜演"))
            self.context_label.show()
            self.context_commands = [
                "播放幻灯片", "导出 PPTX", "演讲备注", "排练计时"
            ]

    def _show_context_recommendations(self):
        """显示上下文推荐和最近命令"""
        self.list_widget.clear()
        shown = set()

        # 上下文命令优先
        for name in self.context_commands:
            if name in self.all_commands:
                desc, _ = self.all_commands[name]
                item = QListWidgetItem(f"📌 {name}  —  {desc}")
                item.setData(Qt.UserRole, name)
                self.list_widget.addItem(item)
                shown.add(name)

        # 最近命令
        if self.recent_commands:
            for name in self.recent_commands[:3]:
                if name not in shown and name in self.all_commands:
                    desc, _ = self.all_commands[name]
                    item = QListWidgetItem(f"🕐 {name}  —  {desc}")
                    item.setData(Qt.UserRole, name)
                    self.list_widget.addItem(item)
                    shown.add(name)

        # 若都为空，显示全部命令的前8条
        if self.list_widget.count() == 0 and self.all_commands:
            for name, (desc, _) in list(self.all_commands.items())[:8]:
                item = QListWidgetItem(f"{name}  —  {desc}")
                item.setData(Qt.UserRole, name)
                self.list_widget.addItem(item)

        if self.list_widget.count() > 0:
            self.list_widget.show()
            self.list_widget.setCurrentRow(0)
            self.resize(450, min(self.list_widget.count() * 36 + 60, 280))
        else:
            self.list_widget.hide()
            self.resize(450, 60)

    # ---------- 搜索 ----------
    def filter_commands(self, text):
        """根据输入过滤命令"""
        self.list_widget.clear()
        if not text.strip():
            self._show_context_recommendations()
            return

        keywords = text.lower().split()
        matched = []
        for name, (desc, _) in self.all_commands.items():
            searchable = f"{name} {desc}".lower()
            if all(kw in searchable for kw in keywords):
                matched.append(name)

        if matched:
            for name in matched:
                desc, _ = self.all_commands[name]
                item = QListWidgetItem(f"{name}  —  {desc}")
                item.setData(Qt.UserRole, name)
                self.list_widget.addItem(item)
            self.list_widget.show()
            self.list_widget.setCurrentRow(0)
            self.resize(450, min(len(matched) * 36 + 60, 350))
        else:
            item = QListWidgetItem(tr("auto.command_palette.fcbf7a6c", "未找到匹配的命令"))
            item.setFlags(Qt.NoItemFlags)
            item.setForeground(QColor("#999"))
            self.list_widget.addItem(item)
            self.list_widget.show()
            self.resize(450, 100)

    # ---------- 命令注册 ----------
    def register_command(self, name, desc, func):
        """注册命令"""
        self.all_commands[name] = (desc, func)

    # ---------- 执行命令 ----------
    def _execute(self, name):
        """执行指定命令"""
        entry = self.all_commands.get(name)
        if not entry:
            return
        _, func = entry
        if func:
            # 记录最近命令
            if name in self.recent_commands:
                self.recent_commands.remove(name)
            self.recent_commands.insert(0, name)
            self.recent_commands = self.recent_commands[:5]
            if self._parent and hasattr(self._parent, 'settings'):
                self._parent.settings.recent_commands = self.recent_commands
                try:
                    self._parent.settings.save()
                except Exception:
                    pass
            # 关闭面板后执行，避免阻塞
            self.close()
            try:
                func()
            except Exception as e:
                import logging
                logging.error(f"执行命令 [{name}] 失败: {e}")
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self._parent, tr("auto.command_palette.b852bcda", "命令执行失败"), str(e))
        else:
            self.close()

    def execute_current(self):
        """执行当前选中项"""
        if self.list_widget.currentItem():
            name = self.list_widget.currentItem().data(Qt.UserRole)
            if name:
                self._execute(name)

    def execute_from_click(self, item):
        """点击执行"""
        name = item.data(Qt.UserRole)
        if name:
            self._execute(name)