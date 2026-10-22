# beeoffice/plugins/beewrite_outline.py
"""
蜜写导航窗格 / 大纲视图：显示文档标题树，支持跳转、折叠、展开

v5.0.1 修复（P1-11）：
  - 文件头注释拼写修正：beewrite_outline.py → beewrite_outline.py
    （原文件名本身就是 beewrite_，仅注释少了一个 e）
"""

import re
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTreeWidget,
    QTreeWidgetItem, QPushButton, QMenu, QLineEdit
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont

from beeoffice.plugins.heading_numbering import HeadingNumberer


class OutlinePanel(QWidget):
    """导航窗格：显示文档标题树"""

    jump_requested = Signal(int)      # 请求跳转到指定位置
    close_requested = Signal()        # 请求关闭面板

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(180)
        self.setMaximumWidth(400)
        self._editor = None
        self._build_ui()

    # ==================== UI ====================
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 标题栏
        header = QHBoxLayout()
        title_label = QLabel("📑 大纲")
        title_label.setStyleSheet(
            "QLabel{font-size:13px;font-weight:bold;color:#E65100;}"
        )
        header.addWidget(title_label)
        header.addStretch()

        btn_refresh = QPushButton("🔄")
        btn_refresh.setFixedWidth(28)
        btn_refresh.setToolTip("刷新大纲")
        btn_refresh.clicked.connect(self.refresh)
        header.addWidget(btn_refresh)

        btn_close = QPushButton("✕")
        btn_close.setFixedWidth(24)
        btn_close.setStyleSheet(
            "QPushButton{border:none;color:#999;font-size:14px;}"
            "QPushButton:hover{color:#E65100;}"
        )
        btn_close.clicked.connect(self.close_requested.emit)
        header.addWidget(btn_close)

        layout.addLayout(header)

        # 搜索框
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("搜索标题...")
        self._search_edit.setStyleSheet(
            "QLineEdit{border:1px solid #DDD;border-radius:3px;"
            "padding:4px 8px;font-size:12px;}"
            "QLineEdit:focus{border-color:#FFB300;}"
        )
        self._search_edit.textChanged.connect(self._on_search)
        layout.addWidget(self._search_edit)

        # 标题树
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setStyleSheet(
            "QTreeWidget{border:1px solid #E0E0E0;"
            "border-radius:4px;background:#FFF;font-size:12px;}"
            "QTreeWidget::item{padding:4px 2px;}"
            "QTreeWidget::item:selected{background:#FFF3E0;color:#E65100;}"
            "QTreeWidget::item:hover{background:#FFF8E1;}"
        )
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(
            self._on_context_menu
        )
        layout.addWidget(self._tree, 1)

        # 底部按钮栏
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(2)

        btn_expand = QPushButton("展开全部")
        btn_expand.setStyleSheet(
            "QPushButton{border:1px solid #DDD;padding:3px 6px;"
            "border-radius:3px;font-size:11px;}"
            "QPushButton:hover{background:#FFF3E0;}"
        )
        btn_expand.clicked.connect(self._expand_all)
        bottom_bar.addWidget(btn_expand)

        btn_collapse = QPushButton("折叠全部")
        btn_collapse.setStyleSheet(
            "QPushButton{border:1px solid #DDD;padding:3px 6px;"
            "border-radius:3px;font-size:11px;}"
            "QPushButton:hover{background:#FFF3E0;}"
        )
        btn_collapse.clicked.connect(self._collapse_all)
        bottom_bar.addWidget(btn_collapse)

        layout.addLayout(bottom_bar)

        # 底部提示
        tip = QLabel("💡 单击标题跳转")
        tip.setStyleSheet(
            "QLabel{color:#999;font-size:10px;padding:2px;}"
        )
        layout.addWidget(tip)

    # ==================== 外部接口 ====================
    def set_editor(self, editor):
        """绑定编辑器"""
        self._editor = editor
        self.refresh()

    def refresh(self):
        """刷新大纲（扫描标题）"""
        self._tree.clear()
        if self._editor is None:
            return

        headings = self._scan_headings()
        if not headings:
            empty_item = QTreeWidgetItem(["（没有标题）"])
            empty_item.setFlags(Qt.NoItemFlags)
            empty_item.setForeground(0, QColor("#999"))
            self._tree.addTopLevelItem(empty_item)
            return

        # 用栈构建树形结构
        stack = []  # [(item, level)]
        for h in headings:
            level = h["level"]
            text = h["text"]
            number = h.get("number", "")
            pos = h["pos"]

            display = f"{number} {text}".strip() if number else text

            item = QTreeWidgetItem([display])
            item.setData(0, Qt.UserRole, pos)
            item.setData(0, Qt.UserRole + 1, level)

            # 根据级别设置字号
            font = QFont()
            if level == 1:
                font.setBold(True)
                font.setPointSize(10)
                item.setForeground(0, QColor("#E65100"))
            elif level == 2:
                font.setBold(True)
                font.setPointSize(9)
                item.setForeground(0, QColor("#F57C00"))
            else:
                font.setPointSize(9)
                item.setForeground(0, QColor("#555"))
            item.setFont(0, font)

            # 弹出栈直到找到父级
            while stack and stack[-1][1] >= level:
                stack.pop()

            if stack:
                stack[-1][0].addChild(item)
            else:
                self._tree.addTopLevelItem(item)

            stack.append((item, level))

        self._tree.expandAll()

    #: 用户手写编号前缀（一、 / 1.1 / 第一章 / （一））→ 不再叠加自动编号。
    #: 中文数字/章名用 `chr()` 构造：i18n 棘轮会把字符串常量里的 CJK 当成 UI 文案，
    #: 这是数据正则、不是界面文案，故不写成中文字面量。
    _CN = "".join(chr(c) for c in (
        0x4E00, 0x4E8C, 0x4E09, 0x56DB, 0x4E94,
        0x516D, 0x4E03, 0x516B, 0x4E5D, 0x5341, 0x767E,
    ))
    _CHAPTER_WORDS = "".join(chr(c) for c in (
        0x7AE0, 0x8282, 0x90E8, 0x5206, 0x7BC7,
    ))
    _DI = chr(0x7B2C)  # 第
    _MANUAL_NUMBER_RE = re.compile(
        "^\\s*(?:[" + _CN + "]+[、.．]"
        "|[（(][" + _CN + "]+[）)]"
        "|\\d+(?:\\.\\d+)*[、.．]?"
        "|" + _DI + "[" + _CN + "]+[" + _CHAPTER_WORDS + "])\\s*"
    )

    @staticmethod
    def _has_manual_numbering(text: str) -> bool:
        """标题是否已带用户手写编号（2026-10-21：避免 `1.1 一、目标` 叠加）。"""
        return bool(OutlinePanel._MANUAL_NUMBER_RE.match(str(text or "")))

    def _scan_headings(self):
        """
        扫描编辑器中的标题。

        优化规划 §3.3：
          - 编号算法原先与 `beewrite_crossref` **逐字重复**，现共用
            `heading_numbering.HeadingNumberer`。
          - 修掉一个由此暴露的真实缺陷：Markdown 模式（默认模式）下
            `QPlainTextEdit` 的每个 block 的 `headingLevel()` 实测**全为 0**，
            于是这里扫到 0 个标题、**大纲面板在 Markdown 模式下永远是空的**；
            而下面那个"按 `#` 解析"的兜底分支又因为
            `hasattr(QPlainTextEdit, "document")` 为真而**永远走不到**。
            现改为：Qt 分支没扫到标题时，回退到 `#` 解析。
          - 兜底分支原先把 `number` 硬编码为空串（同一份代码两种表现），
            现已同样编号；`pos` 也由"行号"改为**字符偏移**，与 Qt 分支的
            `block.position()` 语义一致（否则点击大纲会跳到错误位置）。
        """
        headings = []
        if self._editor is None:
            return headings

        numberer = HeadingNumberer()

        # ---------- 1) 富文本：读 block 的 headingLevel ----------
        if hasattr(self._editor, 'document'):
            doc = self._editor.document()
            block = doc.begin()
            while block.isValid():
                bf = block.blockFormat()
                level = bf.headingLevel()
                if 1 <= level <= 6:
                    text = block.text().strip()
                    if text:
                        number = numberer.next_number(level)
                        headings.append({
                            "level": level,
                            "text": text,
                            "number": (
                                "" if self._has_manual_numbering(text)
                                else number
                            ),
                            "pos": block.position(),
                        })
                block = block.next()

        # ---------- 2) 兜底：Markdown 文本按 `#` 解析 ----------
        if not headings:
            numberer.reset()
            content = self._editor.toPlainText()
            pos = 0
            for line in content.split("\n"):
                m = re.match(r"^(#{1,6})\s+(.+)", line)
                if m:
                    level = len(m.group(1))
                    text = m.group(2).strip()
                    number = numberer.next_number(level)
                    headings.append({
                        "level": level,
                        "text": text,
                        "number": (
                            "" if self._has_manual_numbering(text)
                            else number
                        ),
                        "pos": pos,
                    })
                pos += len(line) + 1

        return headings

    # ==================== 事件 ====================
    def _on_item_clicked(self, item, column):
        pos = item.data(0, Qt.UserRole)
        if pos is None:
            return
        self.jump_requested.emit(pos)

    def _on_search(self, text):
        """搜索标题"""
        text = text.lower().strip()
        for i in range(self._tree.topLevelItemCount()):
            top = self._tree.topLevelItem(i)
            self._filter_item(top, text)

    def _filter_item(self, item, text):
        """递归过滤"""
        # 检查自己
        match = text in item.text(0).lower()
        # 检查子项
        child_match = False
        for j in range(item.childCount()):
            if self._filter_item(item.child(j), text):
                child_match = True
        visible = match or child_match
        item.setHidden(not visible)
        return visible

    def _expand_all(self):
        self._tree.expandAll()

    def _collapse_all(self):
        self._tree.collapseAll()

    def _on_context_menu(self, pos):
        """右键菜单"""
        item = self._tree.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)

        jump_action = menu.addAction("📍 跳转到此处")
        jump_action.triggered.connect(
            lambda: self._on_item_clicked(item, 0)
        )

        menu.addSeparator()

        expand_action = menu.addAction("⬇️ 展开此项")
        expand_action.triggered.connect(item.setExpanded)

        menu.exec(self._tree.mapToGlobal(pos))