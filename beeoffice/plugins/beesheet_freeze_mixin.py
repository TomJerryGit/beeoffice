# beeoffice/plugins/beesheet_freeze_mixin.py
"""
蜜算 WPS 式冻结窗格（2026-10-22，路线图 4.1）。

## 为什么不是"假冻结"
旧版只在状态栏显示"冻结"、并保留文件里的 `freeze_panes`，界面明确禁用——
用户滚动时表头并不会固定。这里用 **叠加视图** 实现真冻结：

- 顶部冻结行：`_frozen_top_view` 覆盖在主表格视口上方，只显示前 top 行；
- 左侧冻结列：`_frozen_left_view` 覆盖在左侧，只显示前 left 列；
- 交叉角：`_frozen_corner_view` 覆盖左上角（行列都冻结时）；
- 主表格的横向/纵向滚动条同步给叠加视图（顶部横向、左侧纵向）；
- 列宽/行高跟随主表格变化，叠加视图可编辑，编辑写同一个 model。

因此滚动主表时，冻结行列保持可见、内容与主表始终对齐；`A2`=冻结首行、
`B1`=冻结首列、`B2`=行列都冻结；`_freeze_panes` 仍由既有 xlsx 写回链持久化。

## 边界
- 只支持"左上冻结"（WPS/Excel 的 freeze_panes 同语义），不支持拆分窗格；
- 叠加视图是只读外观的完整 QTableView（可编辑），不复制数据、不重复导出；
- 大表下只同步列宽/行高，不复制数据。
"""
import re

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QTableView,
)


class FreezeMixin:
    """冻结窗格：状态解析 + 叠加视图 + 工具栏/右键菜单动作。"""

    # ==================== 初始化 / 状态解析 ====================
    def _init_frozen_views(self):
        """在主表格视口里创建三个叠加视图（默认隐藏）。"""
        # 注意：必须挂在 table_view 上，不能挂 viewport()——
        # QAbstractItemView 滚动时会 viewport()->scroll()，那会把 viewport 的
        # 子控件一起移走，冻结叠加层就"消失"了。挂 table_view 并加视口偏移。
        parent = self.table_view

        def _make_view():
            view = QTableView(parent)
            view.setModel(self.model)
            view.setItemDelegate(self._delegate)
            view.setFrameShape(QFrame.NoFrame)
            view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            view.setHorizontalScrollMode(QAbstractItemView.ScrollPerItem)
            view.setVerticalScrollMode(QAbstractItemView.ScrollPerItem)
            view.setSelectionMode(QAbstractItemView.SingleSelection)
            view.setSelectionBehavior(QAbstractItemView.SelectItems)
            view.setEditTriggers(
                QAbstractItemView.DoubleClicked
                | QAbstractItemView.EditKeyPressed
            )
            view.horizontalHeader().hide()
            view.verticalHeader().hide()
            view.setStyleSheet("QTableView{background:#FFFFFF;}")
            view.clicked.connect(self._on_frozen_clicked)
            view.hide()
            return view

        self._frozen_top_view = _make_view()
        self._frozen_left_view = _make_view()
        self._frozen_corner_view = _make_view()
        self._syncing_frozen_scroll = False
        self._frozen_top = int(getattr(self, "_frozen_top", 0) or 0)
        self._frozen_left = int(getattr(self, "_frozen_left", 0) or 0)

        self.table_view.horizontalScrollBar().valueChanged.connect(
            self._sync_frozen_scroll
        )
        self.table_view.verticalScrollBar().valueChanged.connect(
            self._sync_frozen_scroll
        )
        self.table_view.horizontalHeader().sectionResized.connect(
            lambda *_: self._update_frozen_geometry()
        )
        self.table_view.verticalHeader().sectionResized.connect(
            lambda *_: self._update_frozen_geometry()
        )
        self.table_view.viewport().installEventFilter(self)

    def _parse_freeze_ref(self, ref):
        """`A1`/`A2`/`B1`/`B2` → (冻结行数, 冻结列数)；A1=(0,0)。"""
        if not ref:
            return (0, 0)
        match = re.match(r"^([A-Z]{1,3})(\d+)$", str(ref).upper().strip())
        if not match:
            return (0, 0)
        letters, row_text = match.group(1), match.group(2)
        col = 0
        for char in letters:
            col = col * 26 + (ord(char) - 64)
        return (max(0, int(row_text) - 1), max(0, col - 1))

    @staticmethod
    def _column_letter(index):
        index = int(index)
        letters = ""
        while index > 0:
            index, rem = divmod(index - 1, 26)
            letters = chr(65 + rem) + letters
        return letters or "A"

    def _freeze_ref_for(self, top, left):
        """(冻结行数, 冻结列数) → xlsx freeze_panes 引用；无冻结返回 None。"""
        top = max(0, int(top))
        left = max(0, int(left))
        if top == 0 and left == 0:
            return None
        return f"{self._column_letter(left + 1)}{top + 1}"

    def _freeze_parts(self):
        ref = getattr(self, "_freeze_panes", None)
        return self._parse_freeze_ref(ref)

    # ==================== 应用 / 叠加几何 ====================
    def _apply_freeze_from_state(self):
        """打开文件/切换工作表后，按 `_freeze_panes` 恢复叠加视图。"""
        self._apply_freeze_state()

    def _apply_freeze_state(self):
        """按当前 `_freeze_panes` 显示/隐藏并定位叠加视图。"""
        if not hasattr(self, "_frozen_top_view"):
            return
        top, left = getattr(self, "_frozen_top", 0), getattr(
            self, "_frozen_left", 0
        )
        if top <= 0 and left <= 0:
            top, left = self._freeze_parts()
            self._frozen_top, self._frozen_left = top, left
        if top <= 0 and left <= 0:
            for view in (
                self._frozen_top_view,
                self._frozen_left_view,
                self._frozen_corner_view,
            ):
                view.hide()
            return

        rows = self.model.rowCount()
        cols = self.model.columnCount()
        top = min(top, max(0, rows - 1)) if rows else 0
        left = min(left, max(0, cols - 1)) if cols else 0
        for view in (
            self._frozen_top_view,
            self._frozen_left_view,
            self._frozen_corner_view,
        ):
            view.setModel(self.model)
            view.setItemDelegate(self._delegate)
        # 先把隐藏状态清空（工作表切换后行列数可能变化）
        for row in range(rows):
            self._frozen_top_view.setRowHidden(row, row >= top)
            self._frozen_corner_view.setRowHidden(row, row >= top)
        for col in range(cols):
            self._frozen_left_view.setColumnHidden(col, col >= left)
            self._frozen_corner_view.setColumnHidden(col, col >= left)
        for row in range(top, rows):
            self._frozen_left_view.setRowHidden(row, False)
        for col in range(left, cols):
            self._frozen_top_view.setColumnHidden(col, False)
        self._frozen_top_view.setVisible(top > 0)
        self._frozen_left_view.setVisible(left > 0)
        self._frozen_corner_view.setVisible(top > 0 and left > 0)
        self._sync_frozen_sizes()
        self._update_frozen_geometry()
        self._sync_frozen_scroll()

    def _sync_frozen_sizes(self):
        """列宽/行高从主表格复制到叠加视图，保证像素对齐。"""
        if not hasattr(self, "_frozen_top_view"):
            return
        main = self.table_view
        rows = self.model.rowCount()
        cols = self.model.columnCount()
        top, left = self._frozen_top, self._frozen_left
        for col in range(cols):
            width = main.columnWidth(col)
            self._frozen_top_view.setColumnWidth(col, width)
            if left:
                self._frozen_left_view.setColumnWidth(col, width)
                self._frozen_corner_view.setColumnWidth(col, width)
        for row in range(rows):
            height = main.rowHeight(row)
            if top:
                self._frozen_top_view.setRowHeight(row, height)
                self._frozen_corner_view.setRowHeight(row, height)
            if left:
                self._frozen_left_view.setRowHeight(row, height)

    def _update_frozen_geometry(self):
        """叠加视图的位置/尺寸跟随主表格视口（冻结行/列宽高）。"""
        if not hasattr(self, "_frozen_top_view"):
            return
        top, left = self._frozen_top, self._frozen_left
        viewport = self.table_view.viewport()
        origin = viewport.mapTo(self.table_view, viewport.rect().topLeft())
        width, height = viewport.width(), viewport.height()
        top_height = (
            sum(self.table_view.rowHeight(r) for r in range(top))
            if top > 0 else 0
        )
        left_width = (
            sum(self.table_view.columnWidth(c) for c in range(left))
            if left > 0 else 0
        )
        if top > 0:
            self._frozen_top_view.setGeometry(
                origin.x(), origin.y(), width, top_height
            )
            if left > 0:
                self._frozen_corner_view.setGeometry(
                    origin.x(), origin.y(), left_width, top_height
                )
                self._frozen_left_view.setGeometry(
                    origin.x(), origin.y() + top_height,
                    left_width, max(0, height - top_height)
                )
                self._frozen_corner_view.show()
                self._frozen_corner_view.raise_()
                self._frozen_left_view.show()
                self._frozen_left_view.raise_()
            else:
                self._frozen_corner_view.hide()
            self._frozen_top_view.show()
            self._frozen_top_view.raise_()
        else:
            self._frozen_top_view.hide()
            self._frozen_corner_view.hide()
            if left > 0:
                self._frozen_left_view.setGeometry(
                    origin.x(), origin.y(), left_width, height
                )
                self._frozen_left_view.show()
                self._frozen_left_view.raise_()
            else:
                self._frozen_left_view.hide()
        self._sync_frozen_scroll()

    def _sync_frozen_scroll(self, *_args):
        """主表滚动 → 叠加视图滚动（顶部横向、左侧纵向 + 冻结行偏移）。"""
        if getattr(self, "_syncing_frozen_scroll", False):
            return
        if not hasattr(self, "_frozen_top_view"):
            return
        top, left = self._frozen_top, self._frozen_left
        self._syncing_frozen_scroll = True
        try:
            hvalue = self.table_view.horizontalScrollBar().value()
            if top > 0:
                self._frozen_top_view.horizontalScrollBar().setValue(hvalue)
            vvalue = self.table_view.verticalScrollBar().value()
            if left > 0:
                self._frozen_left_view.verticalScrollBar().setValue(
                    max(0, vvalue + top)
                )
        finally:
            self._syncing_frozen_scroll = False

    def _on_frozen_clicked(self, index):
        """点叠加视图单元格 → 主表同步当前单元格（公式栏/状态栏联动）。"""
        if index.isValid():
            self.table_view.setCurrentIndex(index)
            self.table_view.setFocus()

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Resize, QEvent.Show):
            if hasattr(self, "table_view") and obj in (
                self.table_view, self.table_view.viewport()
            ):
                self._update_frozen_geometry()
        return False

    # ==================== UI 动作 ====================
    def _set_freeze_panes(self, ref):
        top, left = self._parse_freeze_ref(ref)
        self._freeze_panes = ref if (top or left) else None
        self._frozen_top, self._frozen_left = top, left
        self._apply_freeze_state()
        if top or left:
            self._set_status(f"❄️ 已冻结：{top} 行 / {left} 列", 3000)
        else:
            self._set_status("已取消冻结", 3000)
        try:
            self.contentChanged.emit()
        except Exception:  # noqa: BLE001
            pass

    def _freeze_first_row(self):
        self._set_freeze_panes("A2")

    def _freeze_first_col(self):
        self._set_freeze_panes("B1")

    def _freeze_first_row_col(self):
        self._set_freeze_panes("B2")

    def _freeze_at_current(self):
        index = self.table_view.currentIndex()
        if not index.isValid():
            return
        self._set_freeze_panes(
            self._freeze_ref_for(index.row(), index.column())
        )

    def _unfreeze_panes(self):
        self._set_freeze_panes(None)

    def _make_freeze_menu(self, menu):
        """把冻结子菜单挂到已有 QMenu（工具栏/右键共用）。"""
        sub = menu.addMenu("❄️ 冻结窗格")
        sub.addAction("冻结首行", self._freeze_first_row)
        sub.addAction("冻结首列", self._freeze_first_col)
        sub.addAction("冻结首行+首列", self._freeze_first_row_col)
        sub.addAction("冻结到当前单元格", self._freeze_at_current)
        sub.addSeparator()
        sub.addAction("取消冻结", self._unfreeze_panes)
        return sub
