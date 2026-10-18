# -*- coding: utf-8 -*-
"""
同步冲突处理对话框（阶段三 #7，最小可用版）

背景：
    同步遇到"本地和远端都改过"时，只会在本地留一个
    `xxx.remote-<时间戳>.md` 副本，然后让用户自己去文件管理器里比对。
    这对普通用户等于"没处理"。

本对话框给出最小可用的处理路径：
    冲突列表 + 三个动作
      · 保留本地 —— 把本地版本上传覆盖远端
      · 采用远端 —— 用冲突副本覆盖本地
      · 两个都留 —— 保持现状（本地 + 副本），只把这条标记为已处理

刻意不做 diff 视图：
    文档类型混杂（Markdown / DOCX / XLSX），真正能逐行对比的只有 Markdown；
    先给用户一个明确的决策入口，比做一个只能对一半格式生效的 diff 更务实。
"""
import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout,
)
from beeoffice.i18n import tr

ACTION_LABELS = {
    "local": "保留本地",
    "remote": "采用远端",
    "both": "两个都留",
}


class SyncConflictDialog(QDialog):
    """逐项处理同步冲突。"""

    def __init__(self, sync, details, parent=None):
        super().__init__(parent)
        self.sync = sync
        self._details = list(details or [])
        self._resolved = 0

        self.setWindowTitle(tr("auto.sync_conflict_dialog.16b6d04e", "同步冲突"))
        self.resize(560, 340)

        layout = QVBoxLayout(self)

        self._hint = QLabel(
            tr("auto.sync_conflict_dialog.4b4e047e", "发现 {0} 个冲突：本地和远端都被修改过。\n请选择每一项的处理方式；未处理的冲突会保持现状（两份都保留）。").format(len(self._details))
        )
        self._hint.setWordWrap(True)
        layout.addWidget(self._hint)

        self._list = QListWidget()
        for d in self._details:
            item = QListWidgetItem(self._format(d))
            item.setData(Qt.UserRole, d)
            self._list.addItem(item)
        layout.addWidget(self._list, 1)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        buttons = QHBoxLayout()
        for action in ("local", "remote", "both"):
            btn = QPushButton(ACTION_LABELS[action])
            btn.clicked.connect(lambda _=False, a=action: self._apply(a))
            buttons.addWidget(btn)
        buttons.addStretch()
        close_btn = QPushButton(tr("auto.sync_conflict_dialog.6c14bd7f", "关闭"))
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

    # ---------- 内部 ----------
    @staticmethod
    def _format(detail) -> str:
        import os
        name = os.path.basename(detail["local"])
        copy = os.path.basename(detail.get("remote_copy", ""))
        return f"{name}    ← 副本：{copy}"

    def _apply(self, action):
        item = self._list.currentItem()
        if item is None:
            self._status.setText(tr("auto.sync_conflict_dialog.c026649d", "请先在列表里选中一个冲突"))
            return

        detail = item.data(Qt.UserRole)
        ok = self.sync.resolve_conflict(detail, action)
        if ok:
            self._resolved += 1
            self._list.takeItem(self._list.row(item))
            self._status.setText(
                tr("auto.sync_conflict_dialog.00405937", "已处理：{0}（剩余 {1} 项）").format(ACTION_LABELS[action], self._list.count())
            )
            if self._list.count() == 0:
                self._hint.setText(
                    tr("auto.sync_conflict_dialog.cd908478", "全部 {0} 个冲突已处理完毕，可以关闭了。").format(self._resolved)
                )
        else:
            self._status.setText(
                tr("auto.sync_conflict_dialog.f6bff7b5", "处理失败：{0} 未生效，详见日志").format(ACTION_LABELS[action])
            )
            logging.error(f"冲突处理失败: {detail.get('local')}")


def show_conflicts(sync, details, parent=None):
    """便捷入口：有冲突就弹窗，返回对话框（便于测试与调用方持有引用）。"""
    if not details:
        return None
    dlg = SyncConflictDialog(sync, details, parent)
    dlg.exec()
    return dlg
