# -*- coding: utf-8 -*-
"""
蜜算冻结首行：真正的视图级冻结（P1-18 第一步）

原实现：
    `_freeze_row` 只是把行的 resizeMode 设成 Fixed。
    那只是"锁住行高"，滚动时表头照样会被顶走——
    注释里也自认"已禁用"，实际上用户点"冻结首行"看不到任何冻结效果。

本实现（v1，只做行冻结）：
    在主视图 viewport 顶部浮一个独立 QTableView，
    通过一个只暴露第 0 行的代理模型显示冻结行；
    它与主表共用列宽、横向滚动同步，纵向不滚动——
    所以内容上下滚动时，首行始终贴在表头下方。

为什么不做列冻结：
    列冻结需要同样的横向视图 + 宽度联动，边界情况（缩放、编辑态、
    行号列）更多，先验证行冻结稳定后再扩。
"""
import logging

from PySide6.QtCore import QAbstractProxyModel, QEvent, QModelIndex, QObject, Qt
from PySide6.QtWidgets import QTableView

FROZEN_ROWS = 1


class _SingleRowProxy(QAbstractProxyModel):
    """只暴露源模型第 row 行的代理模型（O(1)，不依赖 setRowHidden）。"""

    def __init__(self, source=None, row=0, parent=None):
        super().__init__(parent)
        self._row = row
        if source is not None:
            self.setSourceModel(source)

    def rowCount(self, parent=QModelIndex()):
        if self.sourceModel() is None:
            return 0
        return 1 if self.sourceModel().rowCount() > self._row else 0

    def columnCount(self, parent=QModelIndex()):
        if self.sourceModel() is None:
            return 0
        return self.sourceModel().columnCount()

    def index(self, row, column, parent=QModelIndex()):
        if row != 0 or self.sourceModel() is None:
            return QModelIndex()
        return self.createIndex(row, column)

    def parent(self, index):
        return QModelIndex()

    def mapToSource(self, proxy_index):
        if not proxy_index.isValid() or self.sourceModel() is None:
            return QModelIndex()
        return self.sourceModel().index(
            self._row, proxy_index.column()
        )

    def mapFromSource(self, source_index):
        if not source_index.isValid():
            return QModelIndex()
        return self.createIndex(0, source_index.column())


class _ViewportWatcher(QObject):
    """viewport 尺寸变化时重新贴合冻结行视图。"""

    def __init__(self, view):
        super().__init__(view)
        self._view = view

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Resize:
            self._view._sync_frozen_geometry()
        return False


class FrozenRowMixin:
    """提供冻结首行 / 解除冻结的能力。"""

    # ---------- 安装 ----------
    def _install_frozen_row(self):
        """创建并显示冻结行视图（幂等）。"""
        try:
            if getattr(self, "_frozen_row_view", None) is not None:
                self._sync_frozen_geometry()
                self._sync_frozen_columns()
                self._frozen_row_view.show()
                return

            table = self.table_view
            proxy = _SingleRowProxy(self.model, row=0, parent=self)
            self._frozen_proxy = proxy

            view = QTableView(table.viewport())
            view.setModel(proxy)
            view.setFocusPolicy(Qt.NoFocus)
            view.setSelectionMode(QTableView.NoSelection)
            view.setEditTriggers(QTableView.NoEditTriggers)
            view.verticalHeader().hide()
            view.horizontalHeader().hide()
            view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            view.setFrameShape(QTableView.NoFrame)
            view.setStyleSheet(
                "QTableView { border-bottom: 2px solid #FFB300;"
                " background: palette(base); }"
            )
            self._frozen_row_view = view

            # 横向滚动同步（主表动，冻结行跟着动）
            table.horizontalScrollBar().valueChanged.connect(
                view.horizontalScrollBar().setValue
            )
            # 列宽同步
            table.horizontalHeader().sectionResized.connect(
                self._on_main_column_resized
            )
            # 尺寸变化时重新贴合
            self._frozen_watcher = _ViewportWatcher(self)
            table.viewport().installEventFilter(self._frozen_watcher)

            # 数据变化时重绘
            self.model.dataChanged.connect(
                lambda *a: view.viewport().update()
            )
            self.model.modelReset.connect(
                lambda *a: view.viewport().update()
            )

            self._sync_frozen_columns()
            self._sync_frozen_geometry()
            view.show()
        except Exception as e:
            logging.error(f"冻结首行失败: {e}")

    # ---------- 卸载 ----------
    def _remove_frozen_row(self):
        view = getattr(self, "_frozen_row_view", None)
        if view is None:
            return
        try:
            view.hide()
            view.setParent(None)
            view.deleteLater()
        except Exception:
            pass
        self._frozen_row_view = None

    # ---------- 同步 ----------
    def _sync_frozen_geometry(self):
        view = getattr(self, "_frozen_row_view", None)
        if view is None:
            return
        try:
            table = self.table_view
            vp = table.viewport()
            row_h = table.rowHeight(0) if table.model() else 24
            view.setGeometry(0, 0, vp.width(), max(row_h, 20))
            view.raise_()
        except Exception:
            pass

    def _sync_frozen_columns(self):
        view = getattr(self, "_frozen_row_view", None)
        if view is None:
            return
        try:
            header = self.table_view.horizontalHeader()
            frozen_header = view.horizontalHeader()
            for c in range(self.model.columnCount()):
                frozen_header.resizeSection(c, header.sectionSize(c))
        except Exception:
            pass

    def _on_main_column_resized(self, index, old, new):
        view = getattr(self, "_frozen_row_view", None)
        if view is None:
            return
        try:
            view.horizontalHeader().resizeSection(index, new)
        except Exception:
            pass
